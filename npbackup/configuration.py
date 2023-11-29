#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.configuration"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023052801"
__version__ = "1.7.1 for npbackup 2.2.0+"

from typing import Tuple, Optional, List
import sys
import os
from ruamel.yaml import YAML
from logging import getLogger
import re
import platform
from cryptidy import symmetric_encryption as enc
from ofunctions.random import random_string
from npbackup.customization import ID_STRING
from npbackup.core.nuitka_helper import IS_COMPILED


sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

# Try to import a private key, if not available, fallback to the default key
try:
    from PRIVATE._private_secret_keys import AES_KEY, DEFAULT_BACKUP_ADMIN_PASSWORD
    from PRIVATE._private_obfuscation import obfuscation

    AES_KEY = obfuscation(AES_KEY)
    IS_PRIV_BUILD = True
    try:
        from PRIVATE._private_secret_keys import EARLIER_AES_KEY

        EARLIER_AES_KEY = obfuscation(EARLIER_AES_KEY)
    except ImportError:
        EARLIER_AES_KEY = None
except ImportError:
    try:
        from npbackup.secret_keys import AES_KEY, DEFAULT_BACKUP_ADMIN_PASSWORD

        IS_PRIV_BUILD = False
        try:
            from npbackup.secret_keys import EARLIER_AES_KEY
        except ImportError:
            EARLIER_AES_KEY = None
    except ImportError:
        print("No secret_keys file. Please read documentation.")
        sys.exit(1)


logger = getLogger()

# NPF-SEC-00003: Avoid password command divulgation
ENCRYPTED_OPTIONS = [
    {"section": "repo", "name": "repository", "type": str},
    {"section": "repo", "name": "password", "type": str},
    {"section": "repo", "name": "password_command", "type": str},
    {"section": "prometheus", "name": "http_username", "type": str},
    {"section": "prometheus", "name": "http_password", "type": str},
    {"section": "env", "name": "encrypted_variables", "type": str},
    {"section": "options", "name": "auto_upgrade_server_username", "type": str},
    {"section": "options", "name": "auto_upgrade_server_password", "type": str},
]

# By default, backup_admin_password should never be encrypted on the fly, since
# one could simply change it in the config file
ENCRYPTED_OPTIONS_SECURE = [
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
        "password_command": "",
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
    },
}


def decrypt_data(
    config_dict: dict,
    encrypted_options: List[dict],
    non_encrypted_data_is_fatal: bool = True,
) -> dict:
    if not config_dict:
        return None
    try:
        for option in encrypted_options:
            try:
                if config_dict[option["section"]][option["name"]] and isinstance(
                    config_dict[option["section"]][option["name"]], str
                ):
                    if config_dict[option["section"]][option["name"]].startswith(
                        ID_STRING
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
                    else:
                        if non_encrypted_data_is_fatal:
                            logger.critical(
                                "SECURITY BREACH: Config file was altered in {}:{}".format(
                                    option["section"], option["name"]
                                )
                            )
                            sys.exit(99)
            except KeyError:
                # NPF-SEC-00001 SECURITY-ADMIN-BACKUP-PASSWORD ONLY AVAILABLE ON PRIVATE COMPILED BUILDS
                if (
                    not option["section"] == "options"
                    and not option["name"] == "backup_admin_password"
                    and IS_COMPILED
                    and IS_PRIV_BUILD
                ):
                    logger.info(
                        "No {}:{} available.".format(option["section"], option["name"])
                    )
            except ValueError as exc:
                logger.error(
                    'Cannot decrypt this configuration file for option "{}". Has the AES key changed ? {}'.format(
                        option, exc
                    )
                )
                logger.debug("Trace:", exc_info=True)
                return False
    except TypeError:
        logger.error(
            "Cannot decrypt this configuration file. No base64 encoded strings available."
        )
        logger.debug("Trace:", exc_info=True)
        logger.critical("Won't run with a non properly encrypted config file.")
        sys.exit(98)
    return config_dict


def encrypt_data(config_dict: dict, encrypted_options: List[dict]) -> dict:
    for option in encrypted_options:
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
            # NPF-SEC-00001 SECURITY-ADMIN-BACKUP-PASSWORD ONLY AVAILABLE ON PRIVATE COMPILED BUILDS
            if (
                not option["section"] == "options"
                and not option["name"] == "backup_admin_password"
                and IS_COMPILED
                and IS_PRIV_BUILD
            ):
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
    # but we also need a max recursion limit
    # If each variable has two sub variables, we'd have max 4x2x2 loops
    count = 0
    maxcount = 4 * 2 * 2
    while (
        "${MACHINE_ID}" in value
        or "${MACHINE_GROUP}" in value
        or "${BACKUP_JOB}" in value
        or "${HOSTNAME}" in value
    ) and count <= maxcount:
        value = value.replace("${HOSTNAME}", platform.node())

        try:
            new_value = config_dict["identity"]["machine_id"]
        # TypeError may happen if config_dict[x][y] is None
        except (KeyError, TypeError):
            new_value = None
        value = value.replace("${MACHINE_ID}", new_value if new_value else "")

        try:
            new_value = config_dict["identity"]["machine_group"]
        # TypeError may happen if config_dict[x][y] is None
        except (KeyError, TypeError):
            new_value = None
        value = value.replace("${MACHINE_GROUP}", new_value if new_value else "")

        try:
            new_value = config_dict["prometheus"]["backup_job"]
        # TypeError may happen if config_dict[x][y] is None
        except (KeyError, TypeError):
            new_value = None
        value = value.replace("${BACKUP_JOB}", new_value if new_value else "")

        count += 1
    return value


def load_config(config_file: str) -> Optional[dict]:
    """
    Using ruamel.yaml preserves comments and order of yaml files
    """
    global AES_KEY
    global EARLIER_AES_KEY

    try:
        logger.debug("Using configuration file {}".format(config_file))
        with open(config_file, "r", encoding="utf-8") as file_handle:
            # RoundTrip loader is default and preserves comments and ordering
            yaml = YAML(typ="rt")
            config_dict = yaml.load(file_handle)

            config_file_needs_save = False
            # Check modifications before decrypting since ruamel object is a pointer !!!
            is_modified, config_dict = has_random_variables(config_dict)
            if is_modified:
                logger.info("Handling random variables in configuration files")
                config_file_needs_save = True
            if not is_encrypted(config_dict):
                logger.info("Encrypting non encrypted data in configuration file")
                config_file_needs_save = True

            config_dict_decrypted = decrypt_data(
                config_dict, ENCRYPTED_OPTIONS, non_encrypted_data_is_fatal=False
            )
            if config_dict_decrypted == False:
                if EARLIER_AES_KEY:
                    new_aes_key = AES_KEY
                    AES_KEY = EARLIER_AES_KEY
                    logger.info("Trying to migrate encryption key")
                    config_dict_decrypted = decrypt_data(
                        config_dict,
                        ENCRYPTED_OPTIONS,
                        non_encrypted_data_is_fatal=False,
                    )
                    if config_dict_decrypted is not False:
                        AES_KEY = new_aes_key
                        logger.info("Migrated encryption")
                        config_file_needs_save = True
                        new_aes_key = None
                        EARLIER_AES_KEY = None
                    else:
                        logger.critical("Cannot decrypt config file.")
                        sys.exit(12)
                else:
                    sys.exit(11)
            if config_file_needs_save:
                logger.info("Updating config file")
                save_config(config_file, config_dict)

            # Decrypt potential admin password separately
            config_dict_decrypted = decrypt_data(
                config_dict, ENCRYPTED_OPTIONS_SECURE, non_encrypted_data_is_fatal=True
            )
            return config_dict
    except OSError:
        logger.critical("Cannot load configuration file from %s", config_file)
        return None


def save_config(config_file: str, config_dict: dict) -> bool:
    try:
        with open(config_file, "w", encoding="utf-8") as file_handle:
            if not is_encrypted(config_dict):
                config_dict = encrypt_data(
                    config_dict, ENCRYPTED_OPTIONS + ENCRYPTED_OPTIONS_SECURE
                )
            yaml = YAML(typ="rt")
            yaml.dump(config_dict, file_handle)
        # Since we deal with global objects in ruamel.yaml, we need to decrypt after saving
        config_dict = decrypt_data(
            config_dict, ENCRYPTED_OPTIONS, non_encrypted_data_is_fatal=False
        )
        config_dict = decrypt_data(
            config_dict, ENCRYPTED_OPTIONS_SECURE, non_encrypted_data_is_fatal=True
        )
        return True
    except OSError:
        logger.critical("Cannot save configuartion file to %s", config_file)
        return False


def is_priv_build() -> bool:
    return IS_PRIV_BUILD
