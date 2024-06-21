#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.upgrade_runner"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024041801"


import os
from typing import Optional
import tempfile
from logging import getLogger
from npbackup.upgrade_client.upgrader import auto_upgrader, _check_new_version
from npbackup.__version__ import __version__ as npbackup_version
from npbackup.path_helper import CURRENT_DIR


logger = getLogger()


def need_upgrade(upgrade_interval: int) -> bool:
    """
    Basic counter which allows an upgrade only every X times this is called so failed operations won't end in an endless upgrade loop

    We need to make to select a write counter file that is writable
    So we actually test a local file and a temp file (less secure for obvious reasons)
    We just have to make sure that once we can write to one file, we stick to it unless proven otherwise

    The for loop logic isn't straight simple, but allows file fallback
    """
    # file counter, local, home, or temp if not available
    counter_file = "npbackup.autoupgrade.log"

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
            with open(file, "r", encoding="utf-8") as fpr:
                count = int(fpr.read())
                return count
        except OSError:
            # We may not have read privileges
            None
        except ValueError:
            logger.error("Bogus upgrade counter in %s", file)
            return None

    try:
        upgrade_interval = int(upgrade_interval)
    except ValueError:
        logger.error("Bogus upgrade interval given. Will not upgrade")
        return False

    for file in [
        os.path.join(CURRENT_DIR, counter_file),
        os.path.join(tempfile.gettempdir(), counter_file),
    ]:
        if not os.path.isfile(file):
            if _write_count(file, 1):
                logger.debug("Initial upgrade counter written to %s", file)
            else:
                logger.debug("Cannot write to upgrade counter file %s", file)
                continue
        count = _get_count(file)
        # Make sure we can write to the file before we make any assumptions
        result = _write_count(file, count + 1)
        if result:
            if count >= upgrade_interval:
                # Reinitialize upgrade counter before we actually approve upgrades
                if _write_count(file, 1):
                    logger.info("Auto upgrade has decided upgrade check is required")
                    return True
            break
        else:
            logger.debug("Cannot write upgrade counter to %s", file)
            continue
    return False


def check_new_version(full_config: dict) -> bool:
    upgrade_url = full_config.g("global_options.auto_upgrade_server_url")
    username = full_config.g("global_options.auto_upgrade_server_username")
    password = full_config.g("global_options.auto_upgrade_server_password")
    if not upgrade_url or not username or not password:
        logger.warning(f"Missing auto upgrade info, cannot launch auto upgrade")
        return None
    else:
        return _check_new_version(upgrade_url, username, password)


def run_upgrade(full_config: dict) -> bool:
    upgrade_url = full_config.g("global_options.auto_upgrade_server_url")
    username = full_config.g("global_options.auto_upgrade_server_username")
    password = full_config.g("global_options.auto_upgrade_server_password")
    if not upgrade_url or not username or not password:
        logger.warning(f"Missing auto upgrade info, cannot launch auto upgrade")
        return False

    auto_upgrade_host_identity = full_config.g(
        "global_options.auto_upgrade_host_identity"
    )
    group = full_config.g("global_options.auto_upgrade_group")

    result = auto_upgrader(
        upgrade_url=upgrade_url,
        username=username,
        password=password,
        auto_upgrade_host_identity=auto_upgrade_host_identity,
        installed_version=npbackup_version,
        group=group,
    )
    return result
