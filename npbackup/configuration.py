#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.configuration"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023031701"
__version__ = "1.6.2 for npbackup 2.2.0+"

from typing import Tuple, Optional
import sys
from ruamel.yaml import YAML
from logging import getLogger
import re
import platform
from cryptidy import symmetric_encryption as enc
from ofunctions.random import random_string
from npbackup.customization import ID_STRING


# Try to import a private key, if not available, fallback to the default key
try:
    from npbackup._private_secret_keys import AES_KEY, DEFAULT_BACKUP_ADMIN_PASSWORD
    from npbackup._private_revac import revac

    AES_KEY = revac(AES_KEY)
except ImportError:
    try:
        from npbackup.secret_keys import AES_KEY, DEFAULT_BACKUP_ADMIN_PASSWORD
    except ImportError:
        print("No secret_keys file. Please read documentation.")
        sys.exit(1)


logger = getLogger(__name__)

ENCRYPTED_OPTIONS = [
    {"section": "repo", "name": "repository", "type": str},
    {"section": "repo", "name": "password", "type": str},
    {"section": "prometheus", "name": "http_username", "type": str},
    {"section": "prometheus", "name": "http_password", "type": str},
    {"section": "options", "name": "auto_upgrade_server_username", "type": str},
    {"section": "options", "name": "auto_upgrade_server_password", "type": str},
    {"section": "options", "name": "backup_admin_password", "type": str},
]

empty_config_dict = {
    "backup": {
        "compression": "auto",
        "use_fs_snapshot": True,
        "ignore_cloud_files": True,
        "exclude_caches": True,
        "exclude_case_ignore": False,
        "one_file_system": True,
        "priority": "low",
    },
    "repo": {
        "repository": "",
        "password": "",
        "minimum_backup_age": 1440,
        "upload_speed": 0,
        "download_speed": 0,
        "backend_connections": 0,
    },
    "identity": {
        "machine_id": "${HOSTNAME}__${RANDOM}[4]",
        "machine_group": "",
    },
    "prometheus": {
        "metrics": False,
        "instance": "${MACHINE_ID}",
        "backup_job": "${MACHINE_ID}",
        "group": "${MACHINE_GROUP}",
        "destination": "",
        "http_username": "",
        "http_password": "",
        "additional_labels": "",
    },
    "env": {},
    "options": {
        "auto_upgrade": True,
        "auto_upgrade_interval": 10,
        "auto_upgrade_server_url": "",
        "auto_upgrade_server_username": "",
        "auto_upgrade_server_password": "",
        "auto_upgrade_host_identity": "${MACHINE_ID}",
        "auto_upgrade_group": "${MACHINE_GROUP}",
        "backup_admin_password": DEFAULT_BACKUP_ADMIN_PASSWORD,
    },
}


def decrypt_data(config_dict: dict) -> dict:
    try:
        for option in ENCRYPTED_OPTIONS:
            try:
                if (
                    config_dict[option["section"]][option["name"]]
                    and isinstance(config_dict[option["section"]][option["name"]], str)
                    and config_dict[option["section"]][option["name"]].startswith(
                        ID_STRING
                    )
                ):
                    (
                        _,
                        config_dict[option["section"]][option["name"]],
                    ) = enc.decrypt_message_hf(
                        config_dict[option["section"]][option["name"]],
                        AES_KEY,
                        ID_STRING,
                        ID_STRING,
                    )
            except KeyError:
                logger.error(
                    "No {}:{} available.".format(option["section"], option["name"])
                )
    except ValueError:
        logger.error(
            "Cannot decrypt this configuration file. Has the AES key changed ?",
            exc_info=True,
        )
        sys.exit(11)
    except TypeError:
        logger.error(
            "Cannot decrypt this configuration file. No base64 encoded strings available."
        )
        return False
    return config_dict


def encrypt_data(config_dict: dict) -> dict:
    for option in ENCRYPTED_OPTIONS:
        try:
            if config_dict[option["section"]][option["name"]]:
                if not str(config_dict[option["section"]][option["name"]]).startswith(
                    ID_STRING
                ):
                    config_dict[option["section"]][
                        option["name"]
                    ] = enc.encrypt_message_hf(
                        config_dict[option["section"]][option["name"]],
                        AES_KEY,
                        ID_STRING,
                        ID_STRING,
                    ).decode(
                        "utf-8"
                    )
        except KeyError:
            logger.error(
                "No {}:{} available.".format(option["section"], option["name"])
            )
    return config_dict


def is_encrypted(config_dict: dict) -> bool:
    try:
        is_enc = True
        for option in ENCRYPTED_OPTIONS:
            try:
                if config_dict[option["section"]][option["name"]] and not str(
                    config_dict[option["section"]][option["name"]]
                ).startswith(ID_STRING):
                    is_enc = False
            except (TypeError, KeyError):
                # Don't care about encryption on missing items
                # TypeError happens on empty files
                pass
        return is_enc
    except AttributeError:
        # NoneType
        return False


def has_random_variables(config_dict: dict) -> Tuple[bool, dict]:
    """
    Replaces ${RANDOM}[n] with n random alphanumeric chars, directly in config_dict
    """
    is_modified = False
    for section in config_dict.keys():
        for entry in config_dict[section].keys():
            if isinstance(config_dict[section][entry], str):
                matches = re.search(r"\${RANDOM}\[(.*)\]", config_dict[section][entry])
                if matches:
                    try:
                        char_quantity = int(matches.group(1))
                    except (ValueError, TypeError):
                        char_quantity = 1
                    config_dict[section][entry] = re.sub(
                        r"\${RANDOM}\[.*\]",
                        random_string(char_quantity),
                        config_dict[section][entry],
                    )
                    is_modified = True
    return is_modified, config_dict


def evaluate_variables(config_dict: dict, value: str) -> str:
    """
    Replaces various variables with their actual value in a string
    """

    # We need to make a loop to catch all nested variables
    while (
        "${MACHINE_ID}" in value
        or "${MACHINE_GROUP}" in value
        or "${BACKUP_JOB}" in value
        or "${HOSTNAME}" in value
    ):
        value = value.replace("${HOSTNAME}", platform.node())
        try:
            value = value.replace(
                "${MACHINE_ID}", config_dict["identity"]["machine_id"]
            )
        except KeyError:
            pass
        try:
            value = value.replace(
                "${MACHINE_GROUP}", config_dict["identity"]["machine_group"]
            )
        except KeyError:
            pass
        try:
            value = value.replace(
                "${BACKUP_JOB}", config_dict["prometheus"]["backup_job"]
            )
        except KeyError:
            pass
    return value


def load_config(config_file: str) -> Optional[dict]:
    """
    Using ruamel.yaml preserves comments and order of yaml files
    """
    try:
        logger.debug("Using configuration file {}".format(config_file))
        with open(config_file, "r", encoding="utf-8") as file_handle:
            # RoundTrip loader is default and preserves comments and ordering
            yaml = YAML(typ="rt")
            config_dict = yaml.load(file_handle)
            is_modified, config_dict = has_random_variables(config_dict)
            if is_modified:
                logger.info("Handling random variables in configuration files")
                save_config(config_file, config_dict)
            if not is_encrypted(config_dict):
                logger.info("Encrypting non encrypted data in configuration file")
                config_dict = encrypt_data(config_dict)
                save_config(config_file, config_dict)
            config_dict = decrypt_data(config_dict)
            return config_dict
    except OSError:
        logger.critical("Cannot load configuration file from %s", config_file)
        return None


def save_config(config_file: str, config_dict: dict) -> bool:
    try:
        with open(config_file, "w", encoding="utf-8") as file_handle:
            if not is_encrypted(config_dict):
                config_dict = encrypt_data(config_dict)
            yaml = YAML(typ="rt")
            yaml.dump(config_dict, file_handle)
        # Since we deal with global objects in ruamel.yaml, we need to decrypt after saving
        config_dict = decrypt_data(config_dict)
        return True
    except OSError:
        logger.critical("Cannot save configuartion file to %s", config_file)
        return False
