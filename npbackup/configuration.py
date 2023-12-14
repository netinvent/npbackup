#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.configuration"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023121301"
__version__ = "2.0.0 for npbackup 2.3.0+"

CONF_VERSION = 2.3

from typing import Tuple, Optional, List, Callable, Any, Union
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
    "conf_version": CONF_VERSION,
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
                "permissions": {
                    "restore": True,
                    "verify": True,
                    "delete": False,
                },
                "repo_password": "",
                "repo_password_command": "",
                # Minimum time between two backups, in minutes
                # Set to zero in order to disable time checks
                "minimum_backup_age": 1440,
                "upload_speed": 1000000,  # in KiB, use 0 for unlimited upload speed
                "download_speed": 0,  # in KiB, use 0 for unlimited download speed
                "backend_connections": 0,  # Fine tune simultaneous connections to backend, use 0 for standard configuration
                "retention": {
                    "hourly": 72,
                    "daily": 30,
                    "weekly": 4,
                    "monthly": 12,
                    "yearly": 3,
                    "custom_time_server": None,
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
    "global_prometheus": {
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
    if isinstance(d, dict):
        for key, value in d.items():
            if isinstance(value, dict):
                d[key] = iter_over_keys(value, fn)
            else:
                d[key] = fn(key, d[key])
    return d


# TODO: use ofunctions.misc
def replace_in_iterable(
    src: Union[dict, list], original: Union[str, Callable], replacement: Any = None, callable_wants_key: bool = False
):
    """
    Recursive replace data in a struct

    Replaces every instance of string original with string replacement in a list/dict

    If original is a callable function, it will replace every instance of original with callable(original)
    If original is a callable function and callable_wants_key == True,
      it will replace every instance of original with callable(key, original) for dicts
      and with callable(original) for any other data type
    """

    def _replace_in_iterable(key, _src):
        if isinstance(_src, dict) or isinstance(_src, list):
            _src = replace_in_iterable(_src, original, replacement, callable_wants_key)
        elif isinstance(original, Callable):
            if callable_wants_key:
                _src = original(key, _src)
            else:
                _src = original(_src)
        elif isinstance(_src, str) and isinstance(replacement, str):
            _src = _src.replace(original, replacement)
        else:
            _src = replacement
        return _src

    if isinstance(src, dict):
        for key, value in src.items():
            src[key] = _replace_in_iterable(key, value)
    elif isinstance(src, list):
        result = []
        for entry in src:
            result.append(_replace_in_iterable(None, entry))
        src = result
    else:
        src = _replace_in_iterable(None, src)
    return src


def crypt_config(full_config: dict, aes_key: str, encrypted_options: List[str], operation: str):
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

        return replace_in_iterable(full_config, _crypt_config, callable_wants_key=True)
    except Exception as exc:
        logger.error(f"Cannot {operation} configuration: {exc}.")
        return False


def is_encrypted(full_config: dict) -> bool:
    is_encrypted = True

    def _is_encrypted(key, value) -> Any:
        nonlocal is_encrypted 

        if key in ENCRYPTED_OPTIONS:
            if isinstance(value, str) and not value.startswith("__NPBACKUP__"):
                is_encrypted = True
        return value

    replace_in_iterable(full_config, _is_encrypted, callable_wants_key=True)
    return is_encrypted


def has_random_variables(full_config: dict) -> Tuple[bool, dict]:
    """
    Replaces ${RANDOM}[n] with n random alphanumeric chars, directly in config dict
    """
    is_modified = False
    
    def _has_random_variables(value) -> Any:
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
    
    full_config = replace_in_iterable(full_config, _has_random_variables)
    return is_modified, full_config


def evaluate_variables(repo_config: dict, full_config: dict) -> dict:
    """
    Replace runtime variables with their corresponding value
    """
    def _evaluate_variables(value):
        if isinstance(value, str):
            if "${MACHINE_ID}" in value:
                machine_id = full_config.g("identity.machine_id")
                value = value.replace("${MACHINE_ID}", machine_id if machine_id else "")
            
            if "${MACHINE_GROUP}" in value:
                machine_group = full_config.g("identity.machine_group")
                value = value.replace("${MACHINE_GROUP}", machine_group if machine_group else "")

            if "${BACKUP_JOB}" in value:
                backup_job = repo_config.g("backup_opts.backup_job")
                value = value.replace("${BACKUP_JOB}", backup_job if backup_job else "")

            if "${HOSTNAME}" in value:
                value = value.replace("${HOSTNAME}", platform.node())
        return value
    
    # We need to make a loop to catch all nested variables (ie variable in a variable)
    # but we also need a max recursion limit
    # If each variable has two sub variables, we'd have max 4x2x2 loops
    # While this is not the most efficient way, we still get to catch all nested variables
    # and of course, we don't have thousands of lines to parse, so we're good
    count = 0
    maxcount = 4 * 2 * 2
    while count < maxcount:
        repo_config = replace_in_iterable(repo_config, _evaluate_variables)
        count += 1
    return repo_config


def get_repo_config(full_config: dict, repo_name: str = 'default', eval_variables: bool = True) -> Tuple[dict, dict]:
    """
    Create inherited repo config
    Returns a dict containing the repo config, with expanded variables
    and a dict containing the repo interitance status
    """

    repo_config = ordereddict()
    config_inheritance = ordereddict()

    try:
        repo_config = deepcopy(full_config.g(f'repos.{repo_name}'))
        # Let's make a copy of config since it's a "pointer object"
        config_inheritance = replace_in_iterable(deepcopy(full_config.g(f'repos.{repo_name}')), False)
    except KeyError:
        logger.error(f"No repo with name {repo_name} found in config")
        return None
    try:
        repo_group = full_config.g(f'repos.{repo_name}.group')
    except KeyError:
        logger.warning(f"Repo {repo_name} has no group")
    else:
        sections = full_config.g(f'groups.{repo_group}')
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
                sub_sections = full_config.g(f'groups.{repo_group}.{section}')
                if sub_sections:
                    for entries in sub_sections:
                        # Do not overwrite repo values already present
                        if not repo_config.g(f'{section}.{entries}'):
                            repo_config.s(f'{section}.{entries}', full_config.g(f'groups.{repo_group}.{section}.{entries}'))
                            config_inheritance.s(f'{section}.{entries}', True)
                        else:
                            config_inheritance.s(f'{section}.{entries}', False)

    if eval_variables:
        repo_config = evaluate_variables(repo_config, full_config)
    return repo_config, config_inheritance


def get_group_config(full_config: dict, group_name: str, eval_variables: bool = True) -> dict:
    try:
        group_config = deepcopy(full_config.g(f"groups.{group_name}"))
    except KeyError:
        logger.error(f"No group with name {group_name} found in config")
        return None
    
    if eval_variables:
        group_config = evaluate_variables(group_config, full_config)
    return group_config


def _load_config_file(config_file: Path) -> Union[bool, dict]:
    """
    Checks whether config file is valid
    """
    try:
        with open(config_file, "r", encoding="utf-8") as file_handle:
            yaml = YAML(typ="rt")
            full_config = yaml.load(file_handle)

            conf_version = full_config.g("conf_version")
            if conf_version != CONF_VERSION:
                logger.critical(f"Config file version {conf_version} is not required version {CONF_VERSION}")
                return False
            return full_config
    except OSError:
        logger.critical(f"Cannot load configuration file from {config_file}")
        return False

def load_config(config_file: Path) -> Optional[dict]:
    logger.info(f"Loading configuration file {config_file}")

    full_config = _load_config_file(config_file)
    if not full_config:
        return None
    config_file_is_updated = False

    # Check if we need to encrypt some variables
    if not is_encrypted(full_config):
        logger.info("Encrypting non encrypted data in configuration file")
        config_file_is_updated = True
    # Decrypt variables
    full_config = crypt_config(full_config, AES_KEY, ENCRYPTED_OPTIONS, operation='decrypt')
    if full_config == False:
        if EARLIER_AES_KEY:
            logger.warning("Trying to migrate encryption key")
            full_config = crypt_config(full_config, EARLIER_AES_KEY, ENCRYPTED_OPTIONS, operation='decrypt')
            if full_config == False:
                logger.critical("Cannot decrypt config file with earlier key")
                sys.exit(12)
            else:
                config_file_is_updated = True
                logger.warning("Successfully migrated encryption key")
        else:
            logger.critical("Cannot decrypt config file")
            sys.exit(11)


    # Check if we need to expand random vars
    is_modified, full_config = has_random_variables(full_config)
    if is_modified:
        config_file_is_updated = True
        logger.info("Handling random variables in configuration files")

    # save config file if needed
    if config_file_is_updated:
        logger.info("Updating config file")
        save_config(config_file, full_config)

    return full_config


def save_config(config_file: Path, full_config: dict) -> bool:
    try:
        with open(config_file, "w", encoding="utf-8") as file_handle:
            if not is_encrypted(full_config):
                full_config = crypt_config(full_config, AES_KEY, ENCRYPTED_OPTIONS, operation='encrypt')
            yaml = YAML(typ="rt")
            yaml.dump(full_config, file_handle)
        # Since yaml is a "pointer object", we need to decrypt after saving
        full_config = crypt_config(full_config, AES_KEY, ENCRYPTED_OPTIONS, operation='decrypt')
        return True
    except OSError:
        logger.critical(f"Cannot save configuration file to {config_file}")
        return False


def get_repo_list(full_config: dict) -> List[str]:
    return list(full_config.g("repos").keys())


def get_group_list(full_config: dict) -> List[str]:
    return list(full_config.g("groups").keys())
