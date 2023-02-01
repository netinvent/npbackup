#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_server.crud"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "202303101"


import os
from typing import Optional, Union
from logging import getLogger
import hashlib
from upgrade_server.models.files import FileGet, FileSend
from upgrade_server.models.oper import CurrentVersion
import upgrade_server.configuration as configuration


config_dict = configuration.load_config()

logger = getLogger(__intname__)


def sha256sum_data(data):
    # type: (bytes) -> str
    """
    Returns sha256sum of some data
    """
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()


def is_enabled() -> bool:
    return not os.path.isfile("DISABLED")


def get_current_version() -> Optional[CurrentVersion]:
    try:
        path = os.path.join(config_dict["upgrades"]["data_root"], "VERSION")
        if os.path.isfile(path):
            with open(path, "r") as fh:
                ver = fh.readline()
                return CurrentVersion(version=ver)
    except OSError:
        logger.error("Cannot get current version")
    except Exception:
        logger.error("Version seems to be bogus in VERSION file")


def get_file(file: FileGet, content: bool = False) -> Optional[Union[FileSend, bytes]]:
    possible_filename = "npbackup{}".format(
        ".exe" if file.platform.value == "windows" else ""
    )
    path = os.path.join(
        config_dict["upgrades"]["data_root"],
        file.platform.value,
        file.arch.value,
        possible_filename,
    )
    logger.info("Searching for %s", path)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        bytes = fh.read()
        if content:
            return bytes
        length = len(bytes)
        sha256 = sha256sum_data(bytes)
        file_send = FileSend(
            arch=file.arch.value,
            platform=file.platform.value,
            sha256sum=sha256,
            filename=possible_filename,
            file_length=length,
        )
        return file_send
