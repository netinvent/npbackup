#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.local_storage"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026031501"

# This module allows to use local storage for persistent data


import os
from typing import Optional, Union
import tempfile
import logging
from ruamel.yaml import YAML
from ruamel.yaml.scanner import ScannerError
from ruamel.yaml.compat import ordereddict
from ruamel.yaml.comments import CommentedMap
from npbackup.path_helper import CURRENT_DIR, NPBACKUP_ROOT_DIR, sanitize_filename
from npbackup.__version__ import __version__
from npbackup.configuration import convert_to_commented_map

logger = logging.getLogger()


default_storage_config = {
    "conf_version": __version__,
    "storage_history": {},
    "auto_upgrade_counter": {},
    "housekeeping_after_backup_counter": {},
}


def get_default_storage_config() -> CommentedMap:
    return convert_to_commented_map(default_storage_config)


def get_storage_path(config_uuid: str) -> Optional[str]:
    """
    Get a writeable storage parth for a given config_uuid
    """
    storage_file = sanitize_filename(f"npbackup_{config_uuid}") + ".dat"

    # Prefer a non temporary path if possible
    path_list = [
        os.path.join(NPBACKUP_ROOT_DIR, storage_file),
        os.path.join(CURRENT_DIR, storage_file),
    ]

    if os.name != "nt":
        path_list = path_list + [
            os.path.join("/var/log", storage_file),
            os.path.join(tempfile.gettempdir(), storage_file),
        ]
    else:
        path_list = path_list + [
            os.path.join(tempfile.gettempdir(), storage_file),
            os.path.join(r"C:\Windows\Temp", storage_file),
        ]

    for path in path_list:
        try:
            # We need to really try to write to file since os.access(path, os.W_OK) doesn't always work
            file_handle = open(path, "a", encoding="utf-8")
            file_handle.close()
            logger.debug(f"Storage file {path} is writable")
            return path
        except (PermissionError, OSError) as exc:
            logger.debug(f"Cannot write to {path}, trying next option: {exc}")

    logger.error(f"No writable local storage found for {storage_file}")
    return None


def load_storage(config_uuid: str) -> dict:
    """
    Load storage config specific to a given repo in config_file
    """
    storage_file = get_storage_path(config_uuid)
    if not storage_file:
        logger.warning(
            "Loading default storage config, this will prevent autoupgrade / housekeeping / storage analysis to work"
        )
        return get_default_storage_config()
    try:
        with open(storage_file, "r", encoding="utf-8") as file_handle:
            yaml = YAML(typ="rt")
            storage_config = yaml.load(file_handle)
            if storage_config:
                return storage_config
    except OSError as exc:
        logger.error(f"Cannot load storage file from {storage_file}: {exc}")
        logger.debug("Trace:", exc_info=True)
    except ScannerError as exc:
        logger.error(f"Storage file {storage_file} is not a valid yaml file: {exc}")
        logger.debug("Trace:", exc_info=True)
    return get_default_storage_config()


def save_storage(config_uuid: str, storage_config: dict) -> bool:
    """
    Save storage config specific to a given repo in config_file
    """
    storage_file = get_storage_path(config_uuid)
    if not storage_file:
        return False
    try:
        with open(storage_file, "w", encoding="utf-8") as file_handle:
            yaml = YAML(typ="rt")
            yaml.dump(storage_config, file_handle)
        logger.info(f"Saved storage file {storage_file}")
        return True
    except OSError as exc:
        logger.error(f"Cannot save storage file to {storage_file}: {exc}")
        logger.debug("Trace:", exc_info=True)
        return False


if __name__ == "__main__":
    # Test the function
    storage_path = get_storage_path("some_uuid")
    if storage_path:
        print(f"Storage path: {storage_path}")
    else:
        print("No writable storage path found")
