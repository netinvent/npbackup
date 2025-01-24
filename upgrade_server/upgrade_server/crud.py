#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_server.crud"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025012401"


import os
from typing import Optional, Union, Tuple
from logging import getLogger
import hashlib
from datetime import datetime, timezone
from upgrade_server.models.files import ClientTargetIdentification, FileGet, FileSend
from upgrade_server.models.oper import CurrentVersion


logger = getLogger()


def sha256sum_data(data):
    # type: (bytes) -> str
    """
    Returns sha256sum of some data
    """
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()


def is_enabled(config_dict) -> bool:
    path = os.path.join(config_dict["upgrades"]["data_root"], "DISABLED")
    return not os.path.isfile(path)


def _get_path_from_target_id(
    config_dict, target_id: ClientTargetIdentification
) -> Tuple[str, str]:
    """
    Determine specific or generic upgrade path depending on target_id sent by client

    If a specific sub path is found, we'll return that one, otherwise we'll return the default path

    Possible archive names are:
    npbackup-{platform}-{arch}-{build_type}-{audience}.{archive_extension}

    Possible upgrade script names are:
    npbackup-{platform}-{arch}-{build_type}-{audience}.sh
    npbackup-{platform}-{arch}-{build_type}-{audience}.cmd
    npbackup-{platform}.sh
    npbackup-{platform}.cmd

    """
    if target_id.platform.value == "windows":
        archive_extension = "zip"
        script_extension = "cmd"
    else:
        archive_extension = "tar.gz"
        script_extension = "sh"

    expected_archive_filename = f"npbackup-{target_id.platform.value}-{target_id.arch.value}-{target_id.build_type.value}-{target_id.audience.value}.{archive_extension}"
    expected_script_filename = f"npbackup-{target_id.platform.value}-{target_id.arch.value}-{target_id.build_type.value}-{target_id.audience.value}.{script_extension}"

    base_path = os.path.join(
        config_dict["upgrades"]["data_root"],
    )

    for posssible_sub_path in [
        target_id.auto_upgrade_host_identity,
        target_id.installed_version,
        target_id.group,
    ]:
        if posssible_sub_path:
            possibile_sub_path = os.path.join(base_path, posssible_sub_path)
            if os.path.isdir(possibile_sub_path):
                logger.info(f"Found specific upgrade path in {possibile_sub_path}")
                base_path = possibile_sub_path
                break

    archive_path = os.path.join(base_path, expected_archive_filename)
    script_path = os.path.join(base_path, expected_script_filename)

    version_file_path = os.path.join(base_path, "VERSION")

    return version_file_path, archive_path, script_path


def store_host_info(destination: str, host_id: dict) -> None:
    try:
        data = (
            datetime.now(timezone.utc).isoformat()
            + ","
            + ",".join([str(value) if value else "" for value in host_id.values()])
            + "\n"
        )
        with open(destination, "a", encoding="utf-8") as fpw:
            fpw.write(data)
    except OSError as exc:
        logger.error("Cannot write statistics file")
        logger.error("Trace:", exc_info=True)


def get_current_version(
    config_dict: dict,
    target_id: ClientTargetIdentification,
) -> Optional[CurrentVersion]:
    try:
        version_filename, _, _ = _get_path_from_target_id(config_dict, target_id)
        logger.info(f"Searching for version in {version_filename}")
        if os.path.isfile(version_filename):
            with open(version_filename, "r", encoding="utf-8") as fh:
                ver = fh.readline().strip()
                return CurrentVersion(version=ver)
    except OSError as exc:
        logger.error(f"Cannot get current version: {exc}")
        logger.error("Trace:", exc_info=True)
    except Exception as exc:
        logger.error(f"Version seems to be bogus in VERSION file: {exc}")
        logger.error("Trace:", exc_info=True)


def get_file(
    config_dict: dict, file: FileGet, content: bool = False
) -> Optional[Union[FileSend, bytes, bool]]:

    _, archive_path, script_path = _get_path_from_target_id(config_dict, file)

    unknown_artefact = FileSend(
        artefact=file.artefact.value,
        arch=file.arch.value,
        platform=file.platform.value,
        build_type=file.build_type.value,
        audience=file.audience.value,
        sha256sum=None,
        filename=None,
        file_length=0,
    )

    if file.artefact.value == "archive":
        artefact_path = archive_path
    elif file.artefact.value == "script":
        artefact_path = script_path
    else:
        logger.error(f"Unknown artefact type {file.artefact.value}")
        return unknown_artefact
    logger.info(
        f"Searching for file {'info' if not content else 'content'} in {artefact_path}"
    )
    if not os.path.isfile(artefact_path):
        logger.info(f"No {file.artefact.value} file found in {artefact_path}")
        if content:
            return False
        return unknown_artefact

    with open(artefact_path, "rb") as fh:
        file_content_bytes = fh.read()
        if content:
            return file_content_bytes
        length = len(file_content_bytes)
        sha256 = sha256sum_data(file_content_bytes)
        file_send = FileSend(
            artefact=file.artefact.value,
            arch=file.arch.value,
            platform=file.platform.value,
            build_type=file.build_type.value,
            audience=file.audience.value,
            sha256sum=sha256,
            filename=os.path.basename(artefact_path),
            file_length=length,
        )
        return file_send
