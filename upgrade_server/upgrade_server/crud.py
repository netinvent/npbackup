#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_server.crud"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025011401"


import os
from typing import Optional, Union
from logging import getLogger
import hashlib
from argparse import ArgumentParser
from datetime import datetime, timezone
from upgrade_server.models.files import FileGet, FileSend
from upgrade_server.models.oper import CurrentVersion
import upgrade_server.configuration as configuration


# Make sure we load given config files again
parser = ArgumentParser()
parser.add_argument(
    "-c",
    "--config-file",
    dest="config_file",
    type=str,
    default=None,
    required=False,
    help="Path to upgrade_server.conf file",
)
args = parser.parse_args()
if args.config_file:
    config_dict = configuration.load_config(args.config_file)
else:
    config_dict = configuration.load_config()


logger = getLogger()


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


def store_host_info(destination: str, host_id: dict) -> None:
    try:
        data = (
            datetime.now(timezone.utc).isoformat()
            + ","
            + ",".join([value if value else "" for value in host_id.values()])
            + "\n"
        )
        with open(destination, "a", encoding="utf-8") as fpw:
            fpw.write(data)
    except OSError as exc:
        logger.error("Cannot write statistics file")
        logger.error("Trace:", exc_info=True)


def get_current_version() -> Optional[CurrentVersion]:
    try:
        path = os.path.join(config_dict["upgrades"]["data_root"], "VERSION")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                ver = fh.readline().strip()
                return CurrentVersion(version=ver)
    except OSError as exc:
        logger.error("Cannot get current version")
        logger.error("Trace:", exc_info=True)
    except Exception as exc:
        logger.error("Version seems to be bogus in VERSION file")
        logger.error("Trace:", exc_info=True)


def get_file(
    file: FileGet, content: bool = False
) -> Optional[Union[FileSend, bytes, dict]]:
    if file.platform.value == "windows":
        extension = "zip"
    else:
        extension = "tar.gz"
    possible_filename = f"npbackup-{file.build_type.value}.{extension}"
    base_path = os.path.join(
        config_dict["upgrades"]["data_root"],
        file.platform.value,
        file.arch.value,
    )

    for posssible_sub_path in [
        file.auto_upgrade_host_identity.value,
        file.installed_version.value,
        file.group.value,
    ]:
        if posssible_sub_path:
            possibile_sub_path = os.path.join(base_path, posssible_sub_path)
            if os.path.isdir(possibile_sub_path):
                logger.info(f"Found specific upgrade path in {possibile_sub_path}")
                base_path = possibile_sub_path
                break

    path = os.path.join(base_path, possible_filename)

    logger.info(f"Searching for {path}")
    if not os.path.isfile(path):
        logger.info(f"No upgrade file found in {path}")
        return {
            "arch": file.arch.value,
            "platform": file.platform.value,
            "build_type": file.build_type.value,
            "sha256sum": None,
            "filename": None,
            "file_length": 0,
        }

    with open(path, "rb") as fh:
        bytes = fh.read()
        if content:
            return bytes
        length = len(bytes)
        sha256 = sha256sum_data(bytes)
        file_send = FileSend(
            arch=file.arch.value,
            platform=file.platform.value,
            build_type=file.build_type.value,
            sha256sum=sha256,
            filename=possible_filename,
            file_length=length,
        )
        return file_send
