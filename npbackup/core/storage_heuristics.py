#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.storage_heuristics"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026031501"


from typing import Tuple
import logging
from statistics import mean
from npbackup.__env__ import STORAGE_HISTORY_KEEP, STORAGE_HISTORY_EVALUATION_HISTORY_COUNT
from npbackup.local_storage import load_storage, save_storage

logger = logging.getLogger()


def storage_size_heuristics(
    config_uuid: str, repo_uuid: str, storage_size: int, allowed_deviation_percent: Tuple[int, int]
) -> Tuple[bool, bool]:
    """
    Takes last storage size results and calculates whether the current storage is too small
    or too big according to two allowed deviancce percentages
    """
    if not isinstance(storage_size, int):
        logger.warning("Storage size heuristics received non int storage size, skipping heuristics")
        return False, False

    storage = load_storage(config_uuid)
    try:
        storage_history = storage.g(f"storage_history.{repo_uuid}", default=[])
    except AssertionError:
        storage_history = []

    too_small = False
    too_big = False

    if len(storage_history) > 0:
        # Let's use mean instead of median which could produce unexpected spikes
        historic_storage_size = mean(storage_history[-STORAGE_HISTORY_EVALUATION_HISTORY_COUNT :])
        if allowed_deviation_percent[0] is not None:
            if storage_size < historic_storage_size * (1 - allowed_deviation_percent[0] / 100):
                too_small = True
        if allowed_deviation_percent[1] is not None:
            if storage_size > historic_storage_size * (1 + allowed_deviation_percent[1] / 100):
                too_big = True
             
    storage_history.append(storage_size)
    if len(storage_history) > STORAGE_HISTORY_KEEP:
        storage_history = storage_history[-STORAGE_HISTORY_KEEP :]
    try:
        storage.s(f"storage_history.{repo_uuid}", storage_history)
    except TypeError:
        storage.s("storage_history", {})
        storage.s(f"storage_history.{repo_uuid}", storage_history)
    result = save_storage(config_uuid, storage)
    if not result:
        logger.warning(f"Failed to save storage statistics for config_uuid {config_uuid}")

    return too_small, too_big
