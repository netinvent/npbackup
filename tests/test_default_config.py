#! /usr/bin/env python3
#  -*- coding: utf-8 -*-

__intname__ = "npbackup_default_config_tests"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2026 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2026101801"


"""
A new configuration, repo or group uses a filesystem snapshot only where restic can make one:
VSS is Windows-only, and elsewhere use_fs_snapshot only made restic warn on every backup
"""

import sys
import os

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from npbackup.configuration import get_default_config, get_default_group_config


def test_use_fs_snapshot_is_on_by_default_only_on_windows():
    on_windows = os.name == "nt"
    config = get_default_config()
    assert (
        config["groups"]["default_group"]["backup_opts"]["use_fs_snapshot"]
        is on_windows
    )
    assert get_default_group_config()["backup_opts"]["use_fs_snapshot"] is on_windows
