#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.jobs"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025030701"

# This module helps scheduling jobs without using a daemon
# We can schedule on a random percentage or a fixed interval


import os
from typing import Optional
import tempfile
from logging import getLogger
from random import randint
from npbackup.path_helper import CURRENT_DIR


logger = getLogger()


def schedule_on_interval(job_name: str, interval: int) -> bool:
    """
    Basic counter that returns true only every X times this is called

    We need to make to select a write counter file that is writable
    So we actually test a local file and a temp file (less secure for obvious reasons, ie tmp file deletions)
    We just have to make sure that once we can write to one file, we stick to it unless proven otherwise

    The for loop logic isn't straight simple, but allows file fallback
    """
    if not interval:
        logger.debug(f"No interval given for schedule: {interval}")
        return False

    try:
        interval = int(interval)
    except ValueError:
        logger.error(f"No valid interval given for schedule: {interval}")
        return False

    # file counter, local, home, or temp if not available
    counter_file = f"{__intname__}.{job_name}.log"

    def _write_count(file: str, count: int) -> bool:
        try:
            with open(file, "w", encoding="utf-8") as fpw:
                fpw.write(str(count))
                return True
        except OSError:
            # We may not have write privileges, hence we need a backup plan
            return False

    def _get_count(file: str) -> Optional[int]:
        try:
            with open(file, "r", encoding="utf-8") as fp:
                count = int(fp.read())
                return count
        except OSError as exc:
            # We may not have read privileges
            logger.error(f"Cannot read {job_name} counter file {file}: {exc}")
        except ValueError as exc:
            logger.error(f"Bogus {job_name} counter in {file}: {exc}")
        return None

    path_list = [
        os.path.join(tempfile.gettempdir(), counter_file),
        os.path.join(CURRENT_DIR, counter_file),
    ]
    if os.name != "nt":
        path_list = [os.path.join("/var/log", counter_file)] + path_list
    else:
        path_list = [os.path.join(r"C:\Windows\Temp", counter_file)] + path_list

    for file in path_list:
        if not os.path.isfile(file):
            if _write_count(file, 1):
                logger.debug(f"Initial job {job_name} counter written to {file}")
            else:
                logger.debug(f"Cannot write {job_name} counter file {file}")
                continue
        count = _get_count(file)
        # Make sure we can write to the file before we make any assumptions
        result = _write_count(file, count + 1)
        if result:
            if count >= interval:
                # Reinitialize counter before we actually approve job run
                if _write_count(file, 1):
                    logger.info(
                        f"schedule on interval has decided {job_name} is required"
                    )
                    return True
            break
        else:
            logger.debug(f"Cannot write {job_name} counter to {file}")
            continue
    return False


def schedule_on_chance(job_name: str, chance_percent: int) -> bool:
    """
    Randomly decide if we need to run a job according to chance_percent
    """
    if not chance_percent:
        return False
    try:
        chance_percent = int(chance_percent)
    except ValueError:
        logger.error(
            f"No valid chance percent given for schedule: {chance_percent}, job {job_name}"
        )
        return False
    if randint(1, 100) <= chance_percent:
        logger.debug(f"schedule on chance has decided {job_name} is required")
        return True
    return False


def schedule_on_chance_or_interval(
    job_name: str, chance_percent: int, interval: int
) -> bool:
    """
    Decide if we will run a job according to chance_percent or interval
    """
    if schedule_on_chance(chance_percent, job_name) or schedule_on_interval(
        interval, job_name
    ):
        return True
    return False
