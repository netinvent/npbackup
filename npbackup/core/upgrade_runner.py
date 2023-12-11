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


def check_new_version(config_dict: dict) -> bool:
    try:
        upgrade_url = config_dict["options"]["auto_upgrade_server_url"]
        username = config_dict["options"]["auto_upgrade_server_username"]
        password = config_dict["options"]["auto_upgrade_server_password"]
    except KeyError as exc:
        logger.error("Missing auto upgrade info: %s, cannot launch auto upgrade", exc)
        return None
    else:
        return _check_new_version(upgrade_url, username, password)


def run_upgrade(config_dict):
    try:
        auto_upgrade_upgrade_url = config_dict["options"]["auto_upgrade_server_url"]
        auto_upgrade_username = config_dict["options"]["auto_upgrade_server_username"]
        auto_upgrade_password = config_dict["options"]["auto_upgrade_server_password"]
    except KeyError as exc:
        logger.error("Missing auto upgrade info: %s, cannot launch auto upgrade", exc)
        return False

    auto_upgrade_host_identity = config_dict.g("global_options.auto_upgrade_host_identity")
    group = config_dict.g("global_options.auto_upgrade_group")

    result = auto_upgrader(
        upgrade_url=auto_upgrade_upgrade_url,
        username=auto_upgrade_username,
        password=auto_upgrade_password,
        auto_upgrade_host_identity=auto_upgrade_host_identity,
        installed_version=npbackup_version,
        group=group,
    )
    return result
