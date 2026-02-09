#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.upgrade_runner"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025030701"


from logging import getLogger
from npbackup.upgrade_client.upgrader import auto_upgrader, _check_new_version
import npbackup.configuration

logger = getLogger()


def check_new_version(full_config: dict) -> bool:
    upgrade_url = full_config.g("global_options.auto_upgrade_server_url")
    username = full_config.g("global_options.auto_upgrade_server_username")
    password = full_config.g("global_options.auto_upgrade_server_password")
    if not upgrade_url or not username or not password:
        logger.warning(
            "Missing auto upgrade info, cannot check new version for auto upgrade"
        )
        return None
    else:
        return _check_new_version(upgrade_url, username, password)


def run_upgrade(
    config_file: str, full_config: dict, ignore_errors: bool = False
) -> bool:
    upgrade_url = full_config.g("global_options.auto_upgrade_server_url")
    username = full_config.g("global_options.auto_upgrade_server_username")
    password = full_config.g("global_options.auto_upgrade_server_password")
    if not upgrade_url or not username or not password:
        logger.warning("Missing auto upgrade info, cannot launch auto upgrade")
        return False

    evaluated_full_config = npbackup.configuration.evaluate_variables(
        full_config, full_config
    )
    auto_upgrade_host_identity = evaluated_full_config.g(
        "global_options.auto_upgrade_host_identity"
    )
    group = evaluated_full_config.g("global_options.auto_upgrade_group")

    result = auto_upgrader(
        config_file=config_file,
        upgrade_url=upgrade_url,
        username=username,
        password=password,
        auto_upgrade_host_identity=auto_upgrade_host_identity,
        group=group,
        ignore_errors=ignore_errors,
    )
    return result
