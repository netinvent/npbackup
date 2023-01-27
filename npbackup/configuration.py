#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.configuration"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023012401"
__version__ = "1.3.0"

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


empty_config_dict = {"backup": {}, "repo": {}, "prometheus": {}, "env": {}}


def decrypt_data(config_dict):
    try:
        try:
            if config_dict["repo"]["repository"]:
                _, config_dict["repo"]["repository"] = enc.decrypt_message_hf(
                    config_dict["repo"]["repository"], AES_KEY, ID_STRING, ID_STRING
                )
        except KeyError:
            logger.error("No repository URL available.")
            logger.debug("Trace", exc_info=True)

        try:
            if config_dict["repo"]["password"]:
                _, config_dict["repo"]["password"] = enc.decrypt_message_hf(
                    config_dict["repo"]["password"], AES_KEY, ID_STRING, ID_STRING
                )
        except KeyError:
            logger.error("No password available.")
            logger.debug("Trace", exc_info=True)

        try:
            if config_dict["prometheus"]["http_username"]:
                _, config_dict["prometheus"]["http_username"] = enc.decrypt_message_hf(
                    config_dict["prometheus"]["http_username"],
                    AES_KEY,
                    ID_STRING,
                    ID_STRING,
                )
        except KeyError as exc:
            logger.error("No encrypted http username available.")
            logger.debug("Trace", exc_info=True)

        try:
            if config_dict["prometheus"]["http_password"]:
                _, config_dict["prometheus"]["http_password"] = enc.decrypt_message_hf(
                    config_dict["prometheus"]["http_password"],
                    AES_KEY,
                    ID_STRING,
                    ID_STRING,
                )
        except KeyError:
            logger.error("No encrypted http password available.")
            logger.debug("Trace", exc_info=True)
    except ValueError:
        logger.error(
            "Cannot decrypt this configuration file. Has the AES key changed ?"
        )
        sys.exit(11)
    except TypeError:
        logger.error(
            "Cannot decrypt this configuration file. No base64 encoded strings available."
        )
        sys.exit(12)
    return config_dict


def encrypt_data(config_dict):
    try:
        if config_dict["repo"]["repository"] and not config_dict["repo"][
            "repository"
        ].startswith(ID_STRING):
            config_dict["repo"]["repository"] = enc.encrypt_message_hf(
                config_dict["repo"]["repository"], AES_KEY, ID_STRING, ID_STRING
            ).decode("utf-8")
    except KeyError:
        logger.error("No repository URL available.")
        logger.debug("Trace", exc_info=True)
    try:
        if config_dict["repo"]["password"] and not config_dict["repo"][
            "password"
        ].startswith(ID_STRING):
            config_dict["repo"]["password"] = enc.encrypt_message_hf(
                config_dict["repo"]["password"], AES_KEY, ID_STRING, ID_STRING
            ).decode("utf-8")
    except KeyError:
        logger.error("No repository password available.")
        logger.debug("Trace", exc_info=True)

    try:
        if config_dict["prometheus"]["http_username"] and not config_dict["prometheus"][
            "http_username"
        ].startswith(ID_STRING):
            config_dict["prometheus"]["http_username"] = enc.encrypt_message_hf(
                config_dict["prometheus"]["http_username"],
                AES_KEY,
                ID_STRING,
                ID_STRING,
            ).decode("utf-8")
    except KeyError:
        logger.error("No http username available.")
        logger.debug("Trace", exc_info=True)
    try:
        if config_dict["prometheus"]["http_password"] and not config_dict["prometheus"][
            "http_password"
        ].startswith(ID_STRING):
            config_dict["prometheus"]["http_password"] = enc.encrypt_message_hf(
                config_dict["prometheus"]["http_password"],
                AES_KEY,
                ID_STRING,
                ID_STRING,
            ).decode("utf-8")
    except KeyError:
        logger.error("No http password available.")
        logger.debug("Trace", exc_info=True)

    return config_dict


def is_encrypted(config_dict):
    try:
        if (
            isinstance(config_dict["repo"]["repository"], str)
            and config_dict["repo"]["repository"].startswith(ID_STRING)
            and isinstance(config_dict["repo"]["password"], str)
            and config_dict["repo"]["password"].startswith(ID_STRING)
            and isinstance(config_dict["prometheus"]["http_username"], str)
            and config_dict["prometheus"]["http_username"].startswith(ID_STRING)
            and isinstance(config_dict["prometheus"]["http_password"], str)
            and config_dict["prometheus"]["http_password"].startswith(ID_STRING)
        ):
            return True
        return False
    except KeyError:
        return False
    except AttributeError:
        # NoneType
        return False


def load_config(config_file):
    """
    Using ruamel.yaml preserves comments and order of yaml files
    """
    with open(config_file, "r", encoding="utf-8") as file_handle:
        # RoundTrip loader is default and preserves comments and ordering
        yaml = YAML(typ="rt")
        config_dict = yaml.load(file_handle)
        if not is_encrypted(config_dict):
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
