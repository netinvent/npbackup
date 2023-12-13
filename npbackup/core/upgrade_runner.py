#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.upgrade_runner"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023040401"


from logging import getLogger
from npbackup import configuration
from npbackup.upgrade_client.upgrader import auto_upgrader, _check_new_version
from npbackup.__version__ import __version__ as npbackup_version


logger = getLogger()


def check_new_version(full_config: dict) -> bool:
    upgrade_url = full_config.g("global_options.auto_upgrade_server_url")
    username = full_config.g("global_options.auto_upgrade_server_username")
    password = full_config.g("global_options.auto_upgrade_server_password")
    if not upgrade_url or not username or not password:
        logger.error(f"Missing auto upgrade info, cannot launch auto upgrade")
        return None
    else:
        return _check_new_version(upgrade_url, username, password)


def run_upgrade(full_config: dict) -> bool:
    upgrade_url = full_config.g("global_options.auto_upgrade_server_url")
    username = full_config.g("global_options.auto_upgrade_server_username")
    password = full_config.g("global_options.auto_upgrade_server_password")
    if not upgrade_url or not username or not password:
        logger.error(f"Missing auto upgrade info, cannot launch auto upgrade")
        return False

    auto_upgrade_host_identity = full_config.g("global_options.auto_upgrade_host_identity")
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
