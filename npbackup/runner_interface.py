#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.runner_interface"
__author__ = "Orsiris de Jong"
__site__ = "https://www.netperfect.fr/npbackup"
__description__ = "NetPerfect Backup Client"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023122801"


import os
from logging import getLogger
from npbackup.core.runner import NPBackupRunner


logger = getLogger()


def entrypoint(*args, **kwargs):
    npbackup_runner = NPBackupRunner()
    npbackup_runner.repo_config = kwargs.pop("repo_config")
    npbackup_runner.dry_run = kwargs.pop("dry_run")
    npbackup_runner.verbose = kwargs.pop("verbose")
    result = npbackup_runner.__getattribute__(kwargs.pop("operation"))(**kwargs.pop("op_args"), __no_threads=True)


def auto_upgrade(full_config: dict):
    pass

"""
def interface():

    # Program entry
    if args.create_scheduled_task:
        try:
            result = create_scheduled_task(
                executable_path=CURRENT_EXECUTABLE,
                interval_minutes=int(args.create_scheduled_task),
            )
            if result:
                sys.exit(0)
            else:
                sys.exit(22)
        except ValueError:
            sys.exit(23)

    if args.upgrade_conf:
        # Whatever we need to add here for future releases
        # Eg:

        logger.info("Upgrading configuration file to version %s", __version__)
        try:
            config_dict["identity"]
        except KeyError:
            # Create new section identity, as per upgrade 2.2.0rc2
            config_dict["identity"] = {"machine_id": "${HOSTNAME}"}
        configuration.save_config(CONFIG_FILE, config_dict)
        sys.exit(0)

    # Try to perform an auto upgrade if needed
    try:
        auto_upgrade = config_dict["options"]["auto_upgrade"]
    except KeyError:
        auto_upgrade = True
    try:
        auto_upgrade_interval = config_dict["options"]["interval"]
    except KeyError:
        auto_upgrade_interval = 10

    if (auto_upgrade and need_upgrade(auto_upgrade_interval)) or args.auto_upgrade:
        if args.auto_upgrade:
            logger.info("Running user initiated auto upgrade")
        else:
            logger.info("Running program initiated auto upgrade")
        result = run_upgrade(full_config)
        if result:
            sys.exit(0)
        elif args.auto_upgrade:
            sys.exit(23)

    if args.list:
        result = npbackup_runner.list()
        if result:
            for snapshot in result:
                try:
                    tags = snapshot["tags"]
                except KeyError:
                    tags = None
                logger.info(
                    "ID: {} Hostname: {}, Username: {}, Tags: {}, source: {}, time: {}".format(
                        snapshot["short_id"],
                        snapshot["hostname"],
                        snapshot["username"],
                        tags,
                        snapshot["paths"],
                        dateutil.parser.parse(snapshot["time"]),
                    )
                )
            sys.exit(0)
        else:
            sys.exit(2)
"""