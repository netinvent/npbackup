#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.upgrade_runner"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023011701"


from logging import getLogger
from npbackup.upgrade_client.upgrader import auto_upgrader


logger = getLogger(__intname__)


def run_upgrade(config_dict):
    try:
        auto_upgrade_upgrade_url = config_dict["options"]["server_url"]
        auto_upgrade_username = config_dict["options"][
            "server_username"
        ]
        auto_upgrade_password = config_dict["options"][
            "server_password"
        ]
    except KeyError as exc:
        logger.error("Missing auto upgrade info: %s, cannot launch auto upgrade", exc)
        return False
    else:
        result = auto_upgrader(
            upgrade_url=auto_upgrade_upgrade_url,
            username=auto_upgrade_username,
            password=auto_upgrade_password,
        )
        return result