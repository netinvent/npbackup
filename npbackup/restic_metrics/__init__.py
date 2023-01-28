#! /usr/bin/env python3
#  -*- coding: utf-8 -*-


__intname__ = "restic_metrics"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 Orsiris de Jong - NetInvent"
__licence__ = "BSD-3-Clause"
__version__ = "1.4.2"
__build__ = "2023012801"
__description__ = (
    "Converts restic command line output to a text file node_exporter can scrape"
)
__compat__ = "python2.7+"


import os
import sys
import re
from typing import Union, List, Tuple
import logging
import platform
import requests
from datetime import datetime
from argparse import ArgumentParser
from ofunctions.misc import BytesConverter, convert_time_to_seconds


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


if sys.version_info[0] < 3 or (sys.version_info[0] == 3 and sys.version_info[1] < 4):
    import time

    def timestamp_get():
        """
        Get UTC timestamp
        """
        return time.mktime(datetime.utcnow().timetuple())

else:

    def timestamp_get():
        """
        Get UTC timestamp
        """
        return datetime.utcnow().timestamp()


def restic_output_2_metrics(restic_result, output, labels=None):
    # type: (Union[bool, int], str, str) -> Tuple[bool, List[str]]
    """
    Logfile format with restic 0.14:

    using parent snapshot df60db01

    Files:        1584 new,   269 changed, 235933 unmodified
    Dirs:          258 new,   714 changed, 37066 unmodified
    Added to the repo: 493.649 MiB
    processed 237786 files, 85.487 GiB in 11:12
    """

    metrics = []
    if restic_result is False or (restic_result is not True and restic_result != 0):
        errors = True
    else:
        errors = False

    for line in output.splitlines():
        # for line in output:
        matches = re.match(
            r"Files:\s+(\d+)\snew,\s+(\d+)\schanged,\s+(\d+)\sunmodified",
            line,
            re.IGNORECASE,
        )
        if matches:
            try:
                metrics.append(
                    'restic_repo_files{{{},state="new"}} {}'.format(
                        labels, matches.group(1)
                    )
                )
                metrics.append(
                    'restic_repo_files{{{},state="changed"}} {}'.format(
                        labels, matches.group(2)
                    )
                )
                metrics.append(
                    'restic_repo_files{{{},state="unmodified"}} {}'.format(
                        labels, matches.group(3)
                    )
                )
            except IndexError:
                logger.warning("Cannot parse restic log for files")
                errors = True

        matches = re.match(
            r"Dirs:\s+(\d+)\snew,\s+(\d+)\schanged,\s+(\d+)\sunmodified",
            line,
            re.IGNORECASE,
        )
        if matches:
            try:
                metrics.append(
                    'restic_repo_dirs{{{},state="new"}} {}'.format(
                        labels, matches.group(1)
                    )
                )
                metrics.append(
                    'restic_repo_dirs{{{},state="changed"}} {}'.format(
                        labels, matches.group(2)
                    )
                )
                metrics.append(
                    'restic_repo_dirs{{{},state="unmodified"}} {}'.format(
                        labels, matches.group(3)
                    )
                )
            except IndexError:
                logger.warning("Cannot parse restic log for dirs")
                errors = True

        matches = re.match(
            r"Added to the repo.*:\s([-+]?(?:\d*\.\d+|\d+))\s(\w+)\s+\((.*)\sstored\)",
            line,
            re.IGNORECASE,
        )
        if matches:
            try:
                size = matches.group(1)
                unit = matches.group(2)
                try:
                    value = int(BytesConverter("{} {}".format(size, unit)))
                    metrics.append(
                        'restic_repo_size_bytes{{{},state="new"}} {}'.format(
                            labels, value
                        )
                    )
                except TypeError:
                    logger.warning(
                        "Cannot parse restic values from added to repo size log line"
                    )
                    errors = True
                stored_size = matches.group(3)
                try:
                    stored_size = int(BytesConverter(stored_size))
                    metrics.append(
                        'restic_repo_size_files_stored_bytes{{{},state="new"}} {}'.format(
                            labels, stored_size
                        )
                    )
                except TypeError:
                    logger.warning(
                        "Cannot parse restic values from added to repo stored_size log line"
                    )
                    errors = True
            except IndexError as exc:
                logger.warning("Cannot parse restic log for added data: {}".format(exc))
                errors = True

        matches = re.match(
            r"processed\s(\d+)\sfiles,\s([-+]?(?:\d*\.\d+|\d+))\s(\w+)\sin\s((\d+:\d+:\d+)|(\d+:\d+)|(\d+))",
            line,
            re.IGNORECASE,
        )
        if matches:
            try:
                metrics.append(
                    'restic_repo_files{{{},state="total"}} {}'.format(
                        labels, matches.group(1)
                    )
                )
                size = matches.group(2)
                unit = matches.group(3)
                try:
                    value = int(BytesConverter("{} {}".format(size, unit)))
                    metrics.append(
                        'restic_repo_size_bytes{{{},state="total"}} {}'.format(
                            labels, value
                        )
                    )
                except TypeError:
                    logger.warning("Cannot parse restic values for total repo size")
                    errors = True

                seconds_elapsed = convert_time_to_seconds(matches.group(4))
                try:
                    metrics.append(
                        'restic_backup_duration_seconds{{{},action="backup"}} {}'.format(
                            labels, int(seconds_elapsed)
                        )
                    )
                except ValueError:
                    logger.warning("Cannot parse restic elapsed time")
                    errors = True
            except IndexError as exc:
                logger.error("Trace:", exc_info=True)
                logger.warning("Cannot parse restic log for repo size: {}".format(exc))
                errors = True
        matches = re.match(
            r"Failure|Fatal|Unauthorized|no such host|s there a repository at the following location\?",
            line,
            re.IGNORECASE,
        )
        if matches:
            try:
                logger.debug(
                    'Matcher found error: "{}" in line "{}".'.format(
                        matches.group(), line
                    )
                )
            except IndexError as exc:
                logger.error("Trace:", exc_info=True)
            errors = True

    metrics.append(
        'restic_backup_failure{{{},timestamp="{}"}} {}'.format(
            labels, int(timestamp_get()), 1 if errors else 0
        )
    )
    return errors, metrics


def upload_metrics(destination, authentication, metrics):
    try:
        headers = {
            "X-Requested-With": "{} {}".format(__intname__, __version__),
            "Content-type": "text/html",
        }

        data = ""
        for metric in metrics:
            data += "{}\n".format(metric)
        logger.debug("metrics:\n{}".format(data))
        result = requests.post(
            destination, headers=headers, data=data, auth=authentication, timeout=4
        )
        if result.status_code == 200:
            logger.info("Metrics pushed succesfully.")
        else:
            logger.warning(
                "Could not push metrics: {}: {}".format(result.reason, result.text)
            )
    except Exception as exc:
        logger.error("Cannot upload metrics: {}".format(exc))
        logger.debug("Trace:", exc_info=True)


def write_metrics_file(metrics, filename):
    with open(filename, "w", encoding='utf-8') as file_handle:
        for metric in metrics:
            file_handle.write(metric + "\n")


if __name__ == "__main__":
    parser = ArgumentParser(
        prog="restic_log_exporter.py", description="Restic instance prometheus exporter"
    )

    parser.add_argument(
        "-l",
        "--log-file",
        type=str,
        dest="log_file",
        default=None,
        required=True,
        help="Path to restic output (obtained via restic [opts] > /path/to/restic/output 2>&1",
    )

    parser.add_argument(
        "-d",
        "--destination-dir",
        type=str,
        default="/var/lib/node_exporter",
        help="Path to directory where to store metrics text file. Defaults to /var/lib/node_exporter",
    )

    parser.add_argument(
        "-i",
        "--instance",
        type=str,
        default=platform.node(),
        help="Instance name, defaults to hostname",
    )

    parser.add_argument(
        "--labels",
        type=str,
        default=None,
        help='Additional labels, --labels tenant="mytenant",other_label="other_value"',
    )

    parser.add_argument(
        "-b",
        "--backup-job",
        type=str,
        default="restic_bk",
        help="Backup job name, defaults to restic_bk",
    )

    args = parser.parse_args()

    log_file = args.log_file
    destination_dir = args.destination_dir
    instance = args.instance
    backup_job = args.backup_job

    if not os.path.isfile(log_file):
        logger.error(
            "Restic log file (restic command output) {} does not exist.".format(
                log_file
            )
        )
        sys.exit(1)
    output_filename = "{}.restic.{}.txt".format(instance, backup_job)
    if not os.path.isdir(destination_dir):
        logger.error("Output directory {} does not exist.".format(destination_dir))
        sys.exit(2)

    labels = 'instance="{}",backup_job="{}"'.format(instance, backup_job)
    if args.labels:
        labels += ",{}".format(labels)
    destination_file = os.path.join(destination_dir, output_filename)
    try:
        with open(log_file, "r", encoding='utf-8') as file_handle:
            errors, metrics = restic_output_2_metrics(
                True, output=file_handle.readlines(), labels=labels
            )
        if errors:
            logger.error("Script finished with errors.")
        try:
            write_metrics_file(metrics, destination_file)
            logger.info("File {} written succesfully.".format(destination_file))
            sys.exit(0)
        except OSError as exc:
            logger.error(
                "Cannot write restic metrics file {}: {}".format(destination_file, exc)
            )
            sys.exit(3)
    except KeyboardInterrupt:
        logger.info("Program interrupted by CTRL+C")
        sys.exit(4)
    except Exception as exc:
        logger.error("Program failed with error %s" % exc)
        logger.error("Trace:", exc_info=True)
        sys.exit(200)
