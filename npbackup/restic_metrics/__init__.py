#! /usr/bin/env python3
#  -*- coding: utf-8 -*-


__intname__ = "restic_metrics"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "BSD-3-Clause"
__version__ = "2.0.1"
__build__ = "2024103001"
__description__ = (
    "Converts restic command line output to a text file node_exporter can scrape"
)
__compat__ = "python3.6+"


import os
import sys
import re
import json
from typing import Union, List, Tuple
import logging
import platform
import requests
from datetime import datetime, timezone
from argparse import ArgumentParser
from ofunctions.misc import BytesConverter, convert_time_to_seconds


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def restic_str_output_to_json(
    restic_exit_status: Union[bool, int], output: str
) -> dict:
    """
    Parse restic output when used without `--json` parameter
    """
    if restic_exit_status is False or (
        restic_exit_status is not True and restic_exit_status != 0
    ):
        errors = True
    else:
        errors = False
    metrics = {
        "files_new": None,
        "files_changed": None,
        "files_unmodified": None,
        "dirs_new": None,
        "dirs_changed": None,
        "dirs_unmodified": None,
        "data_blobs": None,  # Not present in standard output
        "tree_blobs": None,  # Not present in standard output
        "data_added": None,  # Is "4.425" in  Added to the repository: 4.425 MiB (1.431 MiB stored)
        "data_stored": None,  # Not present in json output, is "1.431" in Added to the repository: 4.425 MiB (1.431 MiB stored)
        "total_files_processed": None,
        "total_bytes_processed": None,
        "total_duration": None,
        # type bool:
        "errors": None,
    }
    for line in output.splitlines():
        # for line in output:
        matches = re.match(
            r"Files:\s+(\d+)\snew,\s+(\d+)\schanged,\s+(\d+)\sunmodified",
            line,
            re.IGNORECASE,
        )
        if matches:
            try:
                metrics["files_new"] = matches.group(1)
                metrics["files_changed"] = matches.group(2)
                metrics["files_unmodified"] = matches.group(3)
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
                metrics["dirs_new"] = matches.group(1)
                metrics["dirs_changed"] = matches.group(2)
                metrics["dirs_unmodified"] = matches.group(3)
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
                    metrics["data_added"] = value
                except TypeError:
                    logger.warning(
                        "Cannot parse restic values from added to repo size log line"
                    )
                    errors = True
                stored_size = matches.group(3)  # TODO: add unit detection in regex
                try:
                    stored_size = int(BytesConverter(stored_size))
                    metrics["data_stored"] = stored_size
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
                metrics["total_files_processed"] = matches.group(1)
                size = matches.group(2)
                unit = matches.group(3)
                try:
                    value = int(BytesConverter("{} {}".format(size, unit)))
                    metrics["total_bytes_processed"] = value
                except TypeError:
                    logger.warning("Cannot parse restic values for total repo size")
                    errors = True

                seconds_elapsed = convert_time_to_seconds(matches.group(4))
                try:
                    metrics["total_duration"] = int(seconds_elapsed)
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

    metrics["errors"] = 1 if errors else 0
    return metrics


def restic_json_to_prometheus(
    restic_result: bool,
    restic_json: dict,
    labels: dict = None,
    minimum_backup_size_error: str = None,
) -> Tuple[bool, List[str], bool]:
    """
    Transform a restic JSON result into prometheus metrics
    """
    _labels = []
    for key, value in labels.items():
        if value:
            _labels.append(f'{key.strip()}="{value.strip()}"')
    labels = ",".join(_labels)

    # Take last line of restic output
    if isinstance(restic_json, str):
        found = False
        for line in reversed(restic_json.split("\n")):
            if '"message_type":"summary"' in line:
                restic_json = line
                found = True
                break
        if not found:
            logger.critical("Bogus data given. No message_type: summmary found")
            return False, [], True

    if not isinstance(restic_json, dict):
        try:
            restic_json = json.loads(restic_json)
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Cannot decode JSON from restic data")
            logger.debug(f"Data is: {restic_json}, Trace:", exc_info=True)
            restic_json = {}

    prom_metrics = []
    for key, value in restic_json.items():
        skip = False
        for starters in ("files", "dirs"):
            if key.startswith(starters):
                for enders in ("new", "changed", "unmodified"):
                    if key.endswith(enders):
                        if value is not None:
                            prom_metrics.append(
                                f'restic_{starters}{{{labels},state="{enders}",action="backup"}} {value}'
                            )
                            skip = True
        if skip:
            continue
        if key == "total_files_processed":
            if value is not None:
                prom_metrics.append(
                    f'restic_files{{{labels},state="total",action="backup"}} {value}'
                )
                continue
        if key == "total_bytes_processed":
            if value is not None:
                prom_metrics.append(
                    f'restic_snasphot_size_bytes{{{labels},action="backup",type="processed"}} {value}'
                )
                continue
        if "duration" in key:
            key += "_seconds"
        if value is not None:
            prom_metrics.append(f'restic_{key}{{{labels},action="backup"}} {value}')

    try:
        processed_bytes = BytesConverter(
            str(restic_json["total_bytes_processed"])
        ).human
        logger.info(f"Processed {processed_bytes} of data")
    except Exception as exc:
        logger.error(f"Cannot find processed bytes: {exc}")
    backup_too_small = False
    if minimum_backup_size_error:
        try:
            if not restic_json["total_bytes_processed"] or restic_json[
                "total_bytes_processed"
            ] < int(
                BytesConverter(str(minimum_backup_size_error).replace(" ", "")).bytes
            ):
                backup_too_small = True
        except KeyError:
            backup_too_small = True
    good_backup = restic_result and not backup_too_small

    prom_metrics.append(
        'restic_backup_failure{{{},timestamp="{}"}} {}'.format(
            labels,
            int(datetime.now(timezone.utc).timestamp()),
            1 if not good_backup else 0,
        )
    )

    return restic_result, prom_metrics, backup_too_small


def restic_output_2_metrics(restic_result, output, labels=None):
    # type: (Union[bool, int], str, str) -> Tuple[bool, List[str]]
    """
    Logfile format with restic 0.14:

    using parent snapshot df60db01

    Files:        1584 new,   269 changed, 235933 unmodified
    Dirs:          258 new,   714 changed, 37066 unmodified
    Added to the repo: 493.649 MiB
    processed 237786 files, 85.487 GiB in 11:12

    Logfile format with restic 0.16 (adds actual stored data size):

    repository 962d5924 opened (version 2, compression level auto)
    using parent snapshot 8cb0c82d
    [0:00] 100.00%  2 / 2 index files loaded

    Files:           0 new,     1 changed,  5856 unmodified
    Dirs:            0 new,     5 changed,   859 unmodified
    Added to the repository: 27.406 KiB (7.909 KiB stored)

    processed 5857 files, 113.659 MiB in 0:00
    snapshot 6881b995 saved
    """

    metrics = []
    if restic_result is False or (restic_result is not True and restic_result != 0):
        errors = True
    else:
        errors = False

    if not output:
        errors = True
    else:
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
                    logger.warning(
                        "Cannot parse restic log for added data: {}".format(exc)
                    )
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
                    logger.warning(
                        "Cannot parse restic log for repo size: {}".format(exc)
                    )
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
            labels, int(datetime.now(timezone.utc).timestamp()), 1 if errors else 0
        )
    )
    return errors, metrics


def upload_metrics(destination: str, authentication, no_cert_verify: bool, metrics):
    """
    Optional upload of metrics to a pushgateway, when no node_exporter with text_collector is available
    """
    try:
        headers = {
            "X-Requested-With": f"{__intname__} {__version__}",
            "Content-type": "text/html",
        }

        data = ""
        for metric in metrics:
            data += f"{metric}\n"
        result = requests.post(
            destination,
            headers=headers,
            data=data,
            auth=authentication,
            timeout=4,
            verify=not no_cert_verify,
        )
        if result.status_code == 200:
            logger.info("Metrics pushed successfully.")
        else:
            logger.warning(
                f"Could not push metrics: {result.status_code}: {result.text}"
            )
    except Exception as exc:
        logger.error(f"Cannot upload metrics: {exc}")
        logger.debug("Trace:", exc_info=True)


def write_metrics_file(metrics: List[str], filename: str):
    try:
        with open(filename, "w", encoding="utf-8") as file_handle:
            for metric in metrics:
                file_handle.write(metric + "\n")
    except OSError as exc:
        logger.error(f"Cannot write metrics file {filename}: {exc}")


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
        with open(log_file, "r", encoding="utf-8") as file_handle:
            errors, metrics = restic_output_2_metrics(
                True, output=file_handle.readlines(), labels=labels
            )
        if errors:
            logger.error("Script finished with errors.")
        try:
            write_metrics_file(metrics, destination_file)
            logger.info("File {} written successfully.".format(destination_file))
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
