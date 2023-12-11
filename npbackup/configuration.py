#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.configuration"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023121001"
__version__ = "2.0.0 for npbackup 2.3.0+"

from typing import Tuple, Optional, List, Callable, Any
import sys
import os
from copy import deepcopy
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.compat import ordereddict
from logging import getLogger
import re
import platform
from cryptidy import symmetric_encryption as enc
from ofunctions.random import random_string
from ofunctions.misc import deep_dict_update
from npbackup.customization import ID_STRING


sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

# Try to import a private key, if not available, fallback to the default key
try:
    from PRIVATE._private_secret_keys import AES_KEY
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
        from npbackup.secret_keys import AES_KEY

        IS_PRIV_BUILD = False
        try:
            from npbackup.secret_keys import EARLIER_AES_KEY
        except ImportError:
            EARLIER_AES_KEY = None
    except ImportError:
        print("No secret_keys file. Please read documentation.")
        sys.exit(1)


logger = getLogger()


# Monkeypatching ruamel.yaml ordreddict so we get to use pseudo dot notations
# eg data.g('my.array.keys') == data['my']['array']['keys']
# and data.s('my.array.keys', 'new_value')
def g(self, path, sep='.', default=None, list_ok=False):
    """
    Getter for dot notation in an a dict/OrderedDict
    print(d.g('my.array.keys'))
    """
    return self.mlget(path.split(sep), default=default, list_ok=list_ok)

def s(self, path, value, sep='.'):
    """
    Setter for dot notation in a dict/OrderedDict
    d.s('my.array.keys', 'new_value')
    """
    data = self
    keys = path.split(sep)
    lastkey = keys[-1]
    for key in keys[:-1]:
        data = data[key]     
    data[lastkey] = value

ordereddict.g = g
ordereddict.s = s

# NPF-SEC-00003: Avoid password command divulgation
ENCRYPTED_OPTIONS = [
    "repo_uri", "repo_password", "repo_password_command", "http_username", "http_password", "encrypted_variables",
    "auto_upgrade_server_username", "auto_upgrade_server_password"
]

# This is what a config file looks like
empty_config_dict = {
    "repos": {
            "default": {
                "repo_uri": "",
                "group": "default_group",
                "backup_opts": {},
                "repo_opts": {},
                "prometheus": {},
                "env": {
                    "variables": {},
                    "encrypted_variables": {}
            },
            },
    },
    "groups": {
        "default_group": {
            "backup_opts": {
                "paths": [],
                "tags": [],
                "compression": "auto",
                "use_fs_snapshot": True,
                "ignore_cloud_files": True,
                "exclude_caches": True,
                "exclude_case_ignore": False,
                "one_file_system": True,
                "priority": "low",
                "exclude_caches": True,
                "exclude_files": [
                    "excludes/generic_excluded_extensions",
                    "excludes/generic_excludes",
                    "excludes/windows_excludes",
                    "excludes/linux_excludes"
                ],
                "exclude_patterns": None,
                "exclude_patterns_source_type": "files_from_verbatim",
                "exclude_patterns_case_ignore": False,
                "additional_parameters": None,
                "additional_backup_only_parameters": None,
                "pre_exec_commands": [],
                "pre_exec_per_command_timeout": 3600,
                "pre_exec_failure_is_fatal": False,
                "post_exec_commands": [],
                "post_exec_per_command_timeout": 3600,
                "post_exec_failure_is_fatal": False,
                "post_exec_execute_even_on_error": True,  # TODO
                }
            },
            "repo_opts": {
                "repo_password": "",
                "repo_password_command": "",
                # Minimum time between two backups, in minutes
                # Set to zero in order to disable time checks
                "minimum_backup_age": 1440,
                "upload_speed": 1000000,  # in KiB, use 0 for unlimited upload speed
                "download_speed": 0,  # in KiB, use 0 for unlimited download speed
                "backend_connections": 0,  # Fine tune simultaneous connections to backend, use 0 for standard configuration
                "retention_strategy": {
                    "hourly": 72,
                    "daily": 30,
                    "weekly": 4,
                    "monthly": 12,
                    "yearly": 3
                }
            },
            "prometheus": {
                "backup_job": "${MACHINE_ID}",
                "group": "${MACHINE_GROUP}",
            },
            "env": {
                "variables": {},
                "encrypted_variables": {}
        },
    },
    "identity": {
        "machine_id": "${HOSTNAME}__${RANDOM}[4]",
        "machine_group": "",
    },
    "prometheus": {
        "metrics": False,
        "instance": "${MACHINE_ID}",
        "destination": "",
        "http_username": "",
        "http_password": "",
        "additional_labels": "",
    },
    "global_options": {
        "auto_upgrade": True,
        "auto_upgrade_interval": 10,
        "auto_upgrade_server_url": "",
        "auto_upgrade_server_username": "",
        "auto_upgrade_server_password": "",
        "auto_upgrade_host_identity": "${MACHINE_ID}",
        "auto_upgrade_group": "${MACHINE_GROUP}",
    },
}


def iter_over_keys(d: dict, fn: Callable) -> dict:
    """
    Execute value=fn(value) on any key in a nested env
    """
    for key, value in d.items():
        if isinstance(value, dict):
            d[key] = iter_over_keys(value, fn)
        else:
            d[key] = fn(key, d[key])
    return d


def crypt_config(config: dict, aes_key: str, encrypted_options: List[str], operation: str):
    try:
        def _crypt_config(key: str, value: Any) -> Any:
            if key in encrypted_options:
                if operation == 'encrypt':
                    if isinstance(value, str) and not value.startswith("__NPBACKUP__") or not isinstance(value, str):
                        value = enc.encrypt_message_hf(
                            value, aes_key, ID_STRING, ID_STRING
                        )
                elif operation == 'decrypt':
                    if isinstance(value, str) and value.startswith("__NPBACKUP__"):
                        value = enc.decrypt_message_hf(
                                        value,
                                        aes_key,
                                        ID_STRING,
                                        ID_STRING,
                                    )
                else:
                    raise ValueError(f"Bogus operation {operation} given")
            return value

        return iter_over_keys(config, _crypt_config)
    except Exception as exc:
        logger.error(f"Cannot {operation} configuration.")
        return False


def is_encrypted(config: dict) -> bool:
    is_encrypted = True

    def _is_encrypted(key, value) -> Any:
        nonlocal is_encrypted 

        if key in ENCRYPTED_OPTIONS:
            if isinstance(value, str) and not value.startswith("__NPBACKUP__"):
                is_encrypted = True
        return value

    iter_over_keys(config, _is_encrypted)
    return is_encrypted


def has_random_variables(config: dict) -> Tuple[bool, dict]:
    """
    Replaces ${RANDOM}[n] with n random alphanumeric chars, directly in config dict
    """
    is_modified = False
    
    def _has_random_variables(key, value) -> Any:
        nonlocal is_modified

        if isinstance(value, str):
            matches = re.search(r"\${RANDOM}\[(.*)\]", value)
            if matches:
                try:
                    char_quantity = int(matches.group(1))
                except (ValueError, TypeError):
                    char_quantity = 1
                value = re.sub(r"\${RANDOM}\[.*\]", random_string(char_quantity), value)
                is_modified = True
        return value
    
    config = iter_over_keys(config, _has_random_variables)
    return is_modified, config


def evaluate_variables(config: dict, value: str) -> str:
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
            new_value = config["identity"]["machine_id"]
        # TypeError may happen if config_dict[x][y] is None
        except (KeyError, TypeError):
            new_value = None
        value = value.replace("${MACHINE_ID}", new_value if new_value else "")

        try:
            new_value = config["identity"]["machine_group"]
        # TypeError may happen if config_dict[x][y] is None
        except (KeyError, TypeError):
            new_value = None
        value = value.replace("${MACHINE_GROUP}", new_value if new_value else "")

        try:
            new_value = config["prometheus"]["backup_job"]
        # TypeError may happen if config_dict[x][y] is None
        except (KeyError, TypeError):
            new_value = None
        value = value.replace("${BACKUP_JOB}", new_value if new_value else "")

        count += 1
    return value


def get_repo_config(config: dict, repo_name: str = 'default') -> Tuple[dict, dict]:
    """
    Created inherited repo config
    Returns a dict containing the repo config
    and a dict containing the repo interitance status
    """

    def _is_inheritance(key, value):
        return False

    repo_config = ordereddict()
    config_inheritance = ordereddict()

    try:
        repo_config = deepcopy(config.g(f'repos.{repo_name}'))
        # Let's make a copy of config since it's a "pointer object"
        config_inheritance = iter_over_keys(deepcopy(config.g(f'repos.{repo_name}')), _is_inheritance)
    except KeyError:
        logger.error(f"No repo with name {repo_name} found in config")
        return None
    try:
        repo_group = config.g(f'repos.{repo_name}.group')
    except KeyError:
        logger.warning(f"Repo {repo_name} has no group")
    else:
        sections = config.g(f'groups.{repo_group}')
        if sections:
            for section in sections:
                # TODO: ordereddict.g() returns None when key doesn't exist instead of KeyError
                # So we need this horrible hack
                try:
                    if not repo_config.g(section):
                        repo_config.s(section, {})
                        config_inheritance.s(section, {})
                except KeyError:
                    repo_config.s(section, {})
                    config_inheritance.s(section, {})
                sub_sections = config.g(f'groups.{repo_group}.{section}')
                if sub_sections:
                    for entries in sub_sections:
                        # Do not overwrite repo values already present
                        if not repo_config.g(f'{section}.{entries}'):
                            repo_config.s(f'{section}.{entries}', config.g(f'groups.{repo_group}.{section}.{entries}'))
                            config_inheritance.s(f'{section}.{entries}', True)
                        else:
                            config_inheritance.s(f'{section}.{entries}', False)
    return repo_config, config_inheritance

def load_config(config_file: Path) -> Optional[dict]:
    logger.info(f"Loading configuration file {config_file}")
    try:
        with open(config_file, "r", encoding="utf-8") as file_handle:
            # Roundtrip loader is default and preserves comments and ordering
            yaml = YAML(typ="rt")
            config = yaml.load(file_handle)
            config_file_is_updated = False

            # Check if we need to encrypt some variables
            if not is_encrypted(config):
                logger.info("Encrypting non encrypted data in configuration file")
                config_file_is_updated = True

            # Decrypt variables
            config = crypt_config(config, AES_KEY, ENCRYPTED_OPTIONS, operation='decrypt')
            if config == False:
                if EARLIER_AES_KEY:
                    logger.warning("Trying to migrate encryption key")
                    config = crypt_config(config, EARLIER_AES_KEY, ENCRYPTED_OPTIONS, operation='decrypt')
                    if config == False:
                        logger.critical("Cannot decrypt config file with earlier key")
                        sys.exit(12)
                    else:
                        config_file_is_updated = True
                        logger.warning("Successfully migrated encryption key")
                else:
                    logger.critical("Cannot decrypt config file")
                    sys.exit(11)


            # Check if we need to expand random vars
            is_modified, config = has_random_variables(config)
            if is_modified:
                config_file_is_updated = True
                logger.info("Handling random variables in configuration files")

            # save config file if needed
            if config_file_is_updated:
                logger.info("Updating config file")
                save_config(config_file, config)

            return config

    except OSError:
        logger.critical(f"Cannot load configuration file from {config_file}")
        return None


def save_config(config_file: Path, config: dict) -> bool:
    try:
        with open(config_file, "w", encoding="utf-8") as file_handle:
            if not is_encrypted(config):
                config = crypt_config(config, AES_KEY, ENCRYPTED_OPTIONS, operation='encrypt')
            yaml = YAML(typ="rt")
            yaml.dump(config, file_handle)
        # Since yaml is a "pointer object", we need to decrypt after saving
        config = crypt_config(config, AES_KEY, ENCRYPTED_OPTIONS, operation='decrypt')
        return True
    except OSError:
        logger.critical(f"Cannot save configuration file to {config_file}")
        return False
