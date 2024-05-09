#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.runner_interface"
__author__ = "Orsiris de Jong"
__site__ = "https://www.netperfect.fr/npbackup"
__description__ = "NetPerfect Backup Client"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024010201"


import sys
from logging import getLogger
import json
import datetime
from npbackup.core.runner import NPBackupRunner


logger = getLogger()


def serialize_datetime(obj):
    """
    By default, datetime objects aren't serialisable to json directly
    Here's a quick converter from https://www.geeksforgeeks.org/how-to-fix-datetime-datetime-not-json-serializable-in-python/
    """
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    raise TypeError("Type not serializable")


def entrypoint(*args, **kwargs):
    repo_config = kwargs.pop("repo_config")
    json_output = kwargs.pop("json_output")
    backend_binary = kwargs.pop("backend_binary", None)

    npbackup_runner = NPBackupRunner()
    if repo_config:
        npbackup_runner.repo_config = repo_config
    npbackup_runner.dry_run = kwargs.pop("dry_run")
    npbackup_runner.verbose = kwargs.pop("verbose")
    npbackup_runner.live_output = not json_output
    npbackup_runner.json_output = json_output
    if backend_binary:
        npbackup_runner.binary = backend_binary
    result = npbackup_runner.__getattribute__(kwargs.pop("operation"))(
        **kwargs.pop("op_args"), __no_threads=True
    )
    if not json_output:
        if not isinstance(result, bool):

            # We need to temprarily remove the stdout handler
            # Since we already get live output from the runner
            # But we still need to log the result to our logfile
            for handler in logger.handlers:
                if handler.stream == sys.stdout:
                    logger.removeHandler(handler)
                    break
            logger.info(f"\n{result}")
            logger.addHandler(handler)
        if result:
            logger.info(f"Operation finished with success")
        else:
            logger.error(f"Operation finished with errors")
    else:
        print(json.dumps(result, default=serialize_datetime))
        sys.exit(0)
