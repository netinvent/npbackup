#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.configuration"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023020101"
__version__ = "1.5.0 for npbackup 2.2.0+"

import sys
from ruamel.yaml import YAML
from logging import getLogger
from cryptidy import symmetric_encryption as enc
from npbackup.customization import ID_STRING

# Try to import a private key, if not available, fallback to the default key
try:
    from npbackup._private_secret_keys import AES_KEY, ADMIN_PASSWORD
    from npbackup._private_revac import revac

    AES_KEY = revac(AES_KEY)
except ImportError:
    try:
        from npbackup.secret_keys import AES_KEY, ADMIN_PASSWORD
    except ImportError:
        print("No secret_keys file. Please read documentation.")
        sys.exit(1)


logger = getLogger(__name__)

ENCRYPTED_OPTIONS = [
    {"section": "repo", "name": "repository", "type": str},
    {"section": "repo", "name": "password", "type": str},
    {"section": "prometheus", "name": "http_username", "type": str},
    {"section": "prometheus", "name": "http_password", "type": str},
    {"section": "options", "name": "server_username", "type": str},
    {"section": "options", "name": "server_password", "type": str},
]

empty_config_dict = {
    "backup": {
        "compression": "auto",
        "use_fs_snapshot": True,
        "ignore_cloud_files": True,
        "exclude_caches": True,
        "priority": "low",
    },
    "repo": {"minimum_backup_age": 1440},
    "prometheus": {},
    "env": {},
    "options": {},
}


def decrypt_data(config_dict):
    try:
        for option in ENCRYPTED_OPTIONS:
            try:
                if config_dict[option["section"]][option["name"]] and config_dict[
                    option["section"]
                ][option["name"]].startswith(ID_STRING):
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
        sys.exit(12)
    return config_dict


def encrypt_data(config_dict):
    for option in ENCRYPTED_OPTIONS:
        try:
            if config_dict[option["section"]][option["name"]] and not config_dict[
                option["section"]
            ][option["name"]].startswith(ID_STRING):
                config_dict[option["section"]][option["name"]] = enc.encrypt_message_hf(
                    config_dict[option["section"]][option["name"]],
                    AES_KEY,
                    ID_STRING,
                    ID_STRING,
                ).decode("utf-8")
        except KeyError:
            logger.error(
                "No {}:{} available.".format(option["section"], option["name"])
            )
    return config_dict


def is_encrypted(config_dict):
    try:
        is_enc = True
        for option in ENCRYPTED_OPTIONS:
            try:
                if isinstance(
                    config_dict[option["section"]][option["name"]],
                    option["type"],
                ) and not config_dict[option["section"]][option["name"]].startswith(
                    ID_STRING
                ):
                    is_enc = False
            except KeyError:
                # Don't care about encryption on missing items
                pass
        return is_enc
    except AttributeError:
        # NoneType
        return False


def load_config(config_file):
    """
    Using ruamel.yaml preserves comments and order of yaml files
    """
    logger.debug("Using configuration file {}".format(config_file))
    with open(config_file, "r", encoding="utf-8") as file_handle:
        # RoundTrip loader is default and preserves comments and ordering
        yaml = YAML(typ="rt")
        config_dict = yaml.load(file_handle)
        if not is_encrypted(config_dict):
            logger.info("Encrypting non encrypted data in configuration file")
            config_dict = encrypt_data(config_dict)
            save_config(config_file, config_dict)
        config_dict = decrypt_data(config_dict)
        return config_dict


def save_config(config_file, config_dict):
    with open(config_file, "w", encoding="utf-8") as file_handle:
        if not is_encrypted(config_dict):
            config_dict = encrypt_data(config_dict)
        yaml = YAML(typ="rt")
        yaml.dump(config_dict, file_handle)
    # Since we deal with global objects in ruamel.yaml, we need to decrypt after saving
    config_dict = decrypt_data(config_dict)
