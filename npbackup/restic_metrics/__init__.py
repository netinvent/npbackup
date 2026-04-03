#! /usr/bin/env python3
#  -*- coding: utf-8 -*-


__intname__ = "restic_metrics"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "BSD-3-Clause"
__version__ = "3.0.0"
__build__ = "2026031301"
__description__ = (
    "Converts restic command line output to a text file node_exporter can scrape"
)
__compat__ = "python3.6+"


import re
import json
from typing import Union
import logging
from ofunctions.misc import BytesConverter, convert_time_to_seconds

logger = logging.getLogger()


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
        "files_total": None,
        "dirs_new": None,
        "dirs_changed": None,
        "dirs_unmodified": None,
        "data_blobs": None,  # Not present in standard output
        "tree_blobs": None,  # Not present in standard output
        "data_added": None,  # Is "4.425" in  Added to the repository: 4.425 MiB (1.431 MiB stored)
        "data_stored": None,  # Not present in json output, is "1.431" in Added to the repository: 4.425 MiB (1.431 MiB stored)
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
                    value = int(BytesConverter("{} {}".format(size, unit)).bytes)
                    metrics["data_added"] = value
                except TypeError:
                    logger.warning(
                        "Cannot parse restic values from added to repo size log line"
                    )
                    errors = True
                stored_size = matches.group(3)
                try:
                    stored_size = int(BytesConverter(stored_size).bytes)
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
                metrics["files_total"] = matches.group(1)
                size = matches.group(2)
                unit = matches.group(3)
                try:
                    value = int(BytesConverter("{} {}".format(size, unit)).bytes)
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
            r"Failure|Fatal|Unauthorized|no such host|i?s there a repository at the following location\?",
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
            except IndexError:
                logger.error("Trace:", exc_info=True)
            errors = True

    metrics["errors"] = 1 if errors else 0
    return metrics
