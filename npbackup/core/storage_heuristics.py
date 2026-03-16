#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.storage_heuristics"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026031501"


from typing import Tuple, List
import logging
from statistics import mean
from npbackup.__env__ import (
    STORAGE_HISTORY_KEEP,
    STORAGE_HISTORY_EVALUATION_HISTORY_COUNT,
    MODIFIED_FILES_HISTORY_EVALUATION_HISTORY_COUNT,
)
from npbackup.local_storage import load_storage, save_storage

logger = logging.getLogger()


def storage_heuristics(
    config_uuid: str,
    repo_uuid: str,
    storage_size: int,
    modified_files: int,
    allowed_deviation_percent: List[int],
) -> Tuple[bool, bool, bool]:
    """
    Takes last storage size results and calculates whether the current storage is too small
    or too big according to two allowed deviation percentages

    Also checks for too many modified files which could be a sign of ransomware
    """
    for index in range(3):
        try:
            if allowed_deviation_percent[index] is not None:
                allowed_deviation_percent[index] = int(allowed_deviation_percent[index])
        except ValueError:
            logger.error(
                f"Invalid allowed deviation percent in configuration: {allowed_deviation_percent[index]}, skipping"
            )
            allowed_deviation_percent[index] = None

    storage = load_storage(config_uuid)
    try:
        storage_history = storage.g(f"storage_history.{repo_uuid}", default=[])
    except AssertionError:
        storage_history = []

    try:
        modified_files_history = storage.g(
            f"modified_files_history.{repo_uuid}", default=[]
        )
    except AssertionError:
        modified_files_history = []

    too_small = False
    too_big = False
    too_many_modified_files = False

    if isinstance(storage_size, int):
        if len(storage_history) > 0:
            # Let's use mean instead of median which could produce unexpected spikes
            historic_storage_size = mean(
                storage_history[-STORAGE_HISTORY_EVALUATION_HISTORY_COUNT:]
            )
            if allowed_deviation_percent[0] is not None:
                if storage_size < historic_storage_size * (
                    1 - allowed_deviation_percent[0] / 100
                ):
                    too_small = True
            if allowed_deviation_percent[1] is not None:
                if storage_size > historic_storage_size * (
                    1 + allowed_deviation_percent[1] / 100
                ):
                    too_big = True

        storage_history.append(storage_size)
        if len(storage_history) > STORAGE_HISTORY_KEEP:
            storage_history = storage_history[-STORAGE_HISTORY_KEEP:]
        try:
            storage.s(f"storage_history.{repo_uuid}", storage_history)
        except (KeyError, TypeError):
            storage.s("storage_history", {})
            storage.s(f"storage_history.{repo_uuid}", storage_history)
    else:
        logger.warning(
            "Storage size heuristics received non int storage size, skipping heuristics"
        )

    if isinstance(modified_files, int):
        # Don't actually trigger any ransomware alerts based on too few data
        if (
            len(modified_files_history)
            > MODIFIED_FILES_HISTORY_EVALUATION_HISTORY_COUNT
        ):
            historic_modified_files = mean(
                modified_files_history[
                    -MODIFIED_FILES_HISTORY_EVALUATION_HISTORY_COUNT:
                ]
            )
            if allowed_deviation_percent[2] is not None:
                if modified_files > historic_modified_files * (
                    1 + allowed_deviation_percent[2] / 100
                ):
                    too_many_modified_files = True

        modified_files_history.append(modified_files)
        if (
            len(modified_files_history)
            > MODIFIED_FILES_HISTORY_EVALUATION_HISTORY_COUNT
        ):
            modified_files_history = modified_files_history[
                -MODIFIED_FILES_HISTORY_EVALUATION_HISTORY_COUNT:
            ]
        try:
            storage.s(f"modified_files_history.{repo_uuid}", modified_files_history)
        except (KeyError, TypeError):
            storage.s("modified_files_history", {})
            storage.s(f"modified_files_history.{repo_uuid}", modified_files_history)
    else:
        logger.warning(
            "Storage modified files heuristics received non int modified files count, skipping heuristics"
        )

    result = save_storage(config_uuid, storage)
    if not result:
        logger.warning(
            f"Failed to save storage statistics for config_uuid {config_uuid}"
        )

    return too_small, too_big, too_many_modified_files
