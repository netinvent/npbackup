#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.jobs"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026031501"

# This module helps scheduling jobs without using a daemon
# We can schedule on a random percentage or a fixed interval


from logging import getLogger
from random import randint
from npbackup.local_storage import load_storage, save_storage

logger = getLogger()


def schedule_on_interval(
    job_name: str, config_uuid: str, repo_uuid: str, interval: int
) -> bool:
    """
    Basic counter that returns true only every X times this is called

    We need to make to select a write counter file that is writable
    So we actually test a local file and a temp file (less secure for obvious reasons, ie tmp file deletions)
    We just have to make sure that once we can write to one file, we stick to it unless proven otherwise

    The for loop logic isn't straight simple, but allows file fallback
    """
    if not interval:
        logger.debug(f"No interval given for job {job_name}: {interval}")
        return False

    try:
        interval = int(interval)
    except ValueError:
        logger.error(f"No valid interval given for job {job_name}: {interval}")
        return False

    storage = load_storage(config_uuid)
    try:
        count = storage.g(f"{job_name}.{repo_uuid}", default=1)
    except AssertionError:
        count = 0
        try:
            storage.s(f"{job_name}.{repo_uuid}", count)
        except TypeError:
            storage.s(f"{job_name}", {})
            storage.s(f"{job_name}.{repo_uuid}", count)
    if count >= interval:
        storage.s(f"{job_name}.{repo_uuid}", 1)
        schedule_required = True
        logger.info(f"schedule on interval has decided {job_name} is required")
    else:
        storage.s(f"{job_name}.{repo_uuid}", count + 1)
        schedule_required = False
    result = save_storage(config_uuid, storage)
    if not result:
        logger.error(
            f"Failed to save storage for job {job_name} with config_uuid {config_uuid}"
        )
        return False
    return schedule_required


def schedule_on_chance(job_name: str, chance_percent: int) -> bool:
    """
    Randomly decide if we need to run a job according to chance_percent
    """
    if not chance_percent:
        logger.debug(f"No chance percent given for job {job_name}: {chance_percent}")
        return False
    try:
        chance_percent = int(chance_percent)
    except ValueError:
        logger.error(
            f"No valid chance percent given for job {job_name}: {chance_percent}"
        )
        return False
    if randint(1, 100) <= chance_percent:
        logger.debug(f"schedule on chance has decided {job_name} is required")
        return True
    return False


def schedule_on_chance_or_interval(
    job_name: str, config_uuid: str, repo_uuid: str, chance_percent: int, interval: int
) -> bool:
    """
    Decide if we will run a job according to chance_percent or interval
    """
    if schedule_on_chance(job_name, chance_percent) or schedule_on_interval(
        job_name, config_uuid, repo_uuid, interval
    ):
        return True
    return False
