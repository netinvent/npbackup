#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.configuration"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026032301"
__version__ = "npbackup 3.1.0+"


from typing import Tuple, Optional, List, Any, Union
import sys
import os
from copy import deepcopy
from pathlib import Path
import re
import platform
import zlib
import uuid
import gc
from logging import getLogger
from ruamel.yaml import YAML
from ruamel.yaml.scanner import ScannerError
from ruamel.yaml.compat import ordereddict
from ruamel.yaml.comments import CommentedMap
from packaging.version import parse as version_parse, InvalidVersion
from cryptidy import symmetric_encryption as enc
from ofunctions.random import random_string
from ofunctions.misc import replace_in_iterable, BytesConverter, iter_over_keys
from resources.customization import ID_STRING
from resources.audience import CURRENT_AUDIENCE
from npbackup.key_management import AES_KEY, EARLIER_AES_KEYS, get_aes_key, obfuscation
from npbackup.__version__ import __version__ as MAX_CONF_VERSION

MIN_MIGRATABLE_CONF_VERSION = "3.0.0"
# MIN_CONF_VERSION defines which config version we accept without migration
# This is also the version we try to migrate to, and should be equivalent to MAX_CONF_VERSION
MIN_CONF_VERSION = "3.1.0-dev"


sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))


logger = getLogger()
opt_aes_key, msg = get_aes_key()
if opt_aes_key:
    logger.info(msg)
    AES_KEY = opt_aes_key
elif opt_aes_key is False:
    logger.critical(msg)


# Monkeypatching ruamel.yaml ordereddict so we get to use pseudo dot notations
# eg data.g('my.array.keys') == data['my']['array']['keys']
# and data.s('my.array.keys', 'new_value')
def g(self, path, sep=".", default=None, list_ok=False):
    """
    Getter for dot notation in a dict/OrderedDict
    print(d.g('my.array.keys'))
    """
    try:
        return self.mlget(path.split(sep), default=default, list_ok=list_ok)
    except AssertionError as exc:
        logger.debug(
            f"CONFIG ERROR {exc} for path={path},sep={sep},default={default},list_ok={list_ok}"
        )
        raise AssertionError from exc


def s(self, path, value, sep="."):
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


def d(self, path, sep="."):
    """
    Deletion for dot notation in a dict/OrderedDict
    d.d('my.array.keys')
    """
    try:
        data = self
        keys = path.split(sep)
        lastkey = keys[-1]
        for key in keys[:-1]:
            data = data[key]
        data.pop(lastkey)
    except KeyError:
        # We don't care deleting non existent keys ^^
        pass


ordereddict.g = g
ordereddict.s = s
ordereddict.d = d

# NPF-SEC-00003: Avoid password command and various passwords disclosure
ENCRYPTED_OPTIONS = [
    "repo_uri",
    "repo_opts.repo_password",
    "repo_opts.repo_password_command",
    "global_prometheus.http_password",
    "global_email.smtp_password",
    "global_zabbix.tls_key",
    "global_zabbix.psk",
    "global_healthchecksio.password",
    "global_webhooks.password",
    "env.encrypted_env_variables",
    "global_options.auto_upgrade_server_password",
]

# This is what a config file looks like
empty_config_dict = {
    "conf_version": MAX_CONF_VERSION,
    "uuid": None,
    "audience": None,
    "repos": {
        # Don't allow repo names to contain dots
        "default": {
            "repo_uri": None,
            "permissions": "full",
            "manager_password": None,
            "repo_group": "default_group",
            "backup_opts": {
                "paths": [],
                "tags": [],
            },
            "repo_opts": {},
            "monitoring": {
                "backup_job": None,
                "group": None,
                "instance": None,
                "additional_labels": {},
            },
            "env": {
                "env_variables": {},
                "encrypted_env_variables": {},
            },
        },
    },
    "groups": {
        # Don't allow group names to contain dots
        "default_group": {
            "backup_opts": {
                "paths": [],
                # Accepted values are None, "folder_list", "files_from_verbatim", "files_from_raw", "stdin_from_command"
                "source_type": None,
                "stdin_from_command": None,
                "stdin_filename": None,
                "tags": [],
                "pack_size": 0,  # integer, 4 is minimum, 16 is default with restic 0.18
                "use_fs_snapshot": True,
                "ignore_cloud_files": True,
                "one_file_system": False,
                "priority": "low",
                "exclude_caches": True,
                "excludes_case_ignore": False,
                "exclude_files": [
                    "excludes/generic_excluded_extensions",
                    "excludes/generic_excludes",
                    "excludes/windows_excludes",
                    "excludes/linux_excludes",
                ],
                "exclude_patterns": None,
                "exclude_files_larger_than": None,  # allows BytesConverter units
                "additional_parameters": None,
                "additional_backup_only_parameters": None,
                "additional_restore_only_parameters": None,
                "minimum_backup_size_error": "10 MiB",  # allows BytesConverter units
                "storage_heuristics_allowed_lower_standard_deviation": 10,  # In percent
                "storage_heuristics_allowed_higher_standard_deviation": 50,  # In percent
                "storage_heuristics_allowed_modified_files_standard_deviation": 20,  # In percent
                "pre_exec_commands": [],
                "pre_exec_per_command_timeout": 3600,
                "pre_exec_failure_is_fatal": False,
                "post_exec_commands": [],
                "post_exec_per_command_timeout": 3600,
                "post_exec_failure_is_fatal": False,
                "post_exec_execute_even_on_backup_error": True,
                "post_backup_housekeeping_percent_chance": 0,  # 0 means disabled, 100 means always
                "post_backup_housekeeping_interval": 0,  # how many runs between a housekeeping after backup operation
            },
            "repo_opts": {
                "repo_password": None,
                "repo_password_command": None,
                "compression": "auto",  # Can be auto, max, off
                # Minimum time between two backups, in minutes
                # Set to zero in order to disable time checks
                "minimum_backup_age": 1435,
                "random_delay_before_backup": 200,  # Random delay in minutes added to a backup launch (allows floats)
                "upload_speed": "800 Mib",  # allows BytesConverter units, use 0 for unlimited upload speed
                "download_speed": "0 Mib",  # allows BytesConverter units, use 0 for unlimited download speed
                "backend_connections": 0,  # Fine tune simultaneous connections to backend, use 0 for standard configuration
                "retention_policy": {
                    "last": 3,
                    "hourly": 72,
                    "daily": 30,
                    "weekly": 4,
                    "monthly": 12,
                    "yearly": 3,
                    "keep_tags": [],
                    "apply_on_tags": [],
                    "keep_within": True,
                    "group_by_host": True,
                    "group_by_tags": True,
                    "group_by_paths": False,
                    "ntp_server": None,
                },
                "prune_max_unused": "0 B",  # allows BytesConverter units, but also allows percents, ie 10%
                "prune_max_repack_size": None,  # allows BytesConverter units
                "read_data_subset": None,  # Restic specific string allowing %, byte units or fractions
            },
            "monitoring": {
                "backup_job": "${REPO_NAME}",  # In system/VM scenarios, this will be replaced with VM names or system name
                "group": "${MACHINE_GROUP}",
                "instance": "${MACHINE_ID}",
                "tenant": "${MACHINE_TENANT}",
                "additional_labels": {},
            },
            "env": {"env_variables": {}, "encrypted_env_variables": {}},
        },
    },
    "identity": {
        "machine_id": "${HOSTNAME}__${RANDOM}[4]",
        "machine_group": None,
        "machine_tenant": None,
    },
    "global_prometheus": {
        "enabled": False,
        "destination": None,
        "http_username": None,
        "http_password": None,
        "no_cert_verify": False,
    },
    "global_zabbix": {
        "enabled": False,
        "server": None,
        "port": 10051,
        "authentication": "none",  # can be none, tls or psk
        "no_cert_verify": False,
        "tls_cert": None,
        "tls_key": None,
        "tls_cacert": None,
        "psk_identity": None,
        "psk": None,
    },
    "global_healthchecksio": {
        "enabled": False,
        "url": None,
        "username": None,
        "password": None,
        "no_cert_verify": False,
    },
    "global_webhooks": {
        "enabled": False,
        "destination": None,
        "method": "POST",
        "username": None,
        "password": None,
        "pretty_json": False,
        "no_cert_verify": False,
    },
    "global_email": {
        "enabled": False,
        "smtp_server": None,
        "smtp_port": 587,
        "smtp_security": None,  # can be None, "ssl" or "tls"
        "smtp_username": None,
        "smtp_password": None,
        "sender": None,
        "recipients": {
            "on_backup_success": [],
            "on_backup_failure": [],
            "on_operations_success": [],
            "on_operations_failure": [],
        },
    },
    "global_options": {
        "auto_upgrade": False,
        "auto_upgrade_percent_chance": 5,  # On all runs. On 15m interval runs, this could be 5% (ie once a day), on daily runs, this should be 95% (ie once a day)
        "auto_upgrade_interval": 15,  # How many NPBackup runs before an auto upgrade is attempted
        "auto_upgrade_server_url": None,
        "auto_upgrade_server_username": None,
        "auto_upgrade_server_password": None,
        "auto_upgrade_host_identity": "${MACHINE_ID}",
        "auto_upgrade_group": "${MACHINE_GROUP}",
        "full_concurrency": False,  # Allow multiple npbackup instances to run at the same time
        "repo_aware_concurrency": False,  # Allow multiple npbackup instances to run at the same time, but only for different repos
    },
    "presets": {
        # Retention settings settings
        "retention_policy": {
            "14d": {
                "last": 3,
                "hourly": 72,
                "daily": 14,
                "weekly": 0,
                "monthly": 0,
                "yearly": 0,
                "keep_within": True,
                "group_by_host": True,
                "group_by_tags": True,
                "group_by_paths": False,
            },
            "30d": {
                "last": 3,
                "hourly": 72,
                "daily": 30,
                "weekly": 0,
                "monthly": 0,
                "yearly": 0,
                "keep_within": True,
                "group_by_host": True,
                "group_by_tags": True,
                "group_by_paths": False,
            },
            "90d": {
                "last": 3,
                "hourly": 72,
                "daily": 90,
                "weekly": 0,
                "monthly": 0,
                "yearly": 0,
                "keep_within": True,
                "group_by_host": True,
                "group_by_tags": True,
                "group_by_paths": False,
            },
            "gfs": {
                "last": 3,
                "hourly": 72,
                "daily": 30,
                "weekly": 4,
                "monthly": 12,
                "yearly": 3,
                "keep_within": True,
                "group_by_host": True,
                "group_by_tags": True,
                "group_by_paths": False,
            },
            "keep_all": {
                "last": "all",
                "hourly": "all",
                "daily": "all",
                "weekly": "all",
                "monthly": "all",
                "yearly": "all",
                "keep_within": True,
                "group_by_host": True,
                "group_by_tags": True,
                "group_by_paths": False,
            },
        }
    },
}


def gen_uuid_from_path(file: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, str(file)))


def convert_to_commented_map(
    source_dict,
):
    if isinstance(source_dict, dict):
        return CommentedMap(
            {k: convert_to_commented_map(v) for k, v in source_dict.items()}
        )
    return source_dict


def get_default_config() -> dict:
    """
    Returns a config dict as nested CommentedMaps (used by ruamel.yaml to keep comments intact)
    """
    full_config = deepcopy(empty_config_dict)

    return convert_to_commented_map(full_config)


def get_default_repo_config() -> dict:
    """
    Returns a repo config dict as nested CommentedMaps (used by ruamel.yaml to keep comments intact)
    """
    repo_config = deepcopy(empty_config_dict["repos"]["default"])
    return convert_to_commented_map(repo_config)


def get_default_group_config() -> dict:
    """
    Returns a group config dict as nested CommentedMaps (used by ruamel.yaml to keep comments intact)
    """
    group_config = deepcopy(empty_config_dict["groups"]["default_group"])
    return convert_to_commented_map(group_config)


def key_should_be_encrypted(key: str, encrypted_options: List[str]):
    """
    Checks whether key should be encrypted
    """
    if key:
        for option in encrypted_options:
            if option in key:
                return True
    return False


def crypt_config(
    full_config: dict, aes_key: str, encrypted_options: List[str], operation: str
):
    try:

        def _crypt_config(key: str, value: Any) -> Any:
            if key_should_be_encrypted(key, encrypted_options):
                if value is not None:
                    if operation == "encrypt":
                        if (
                            isinstance(value, str)
                            and (
                                not value.startswith(ID_STRING)
                                or not value.endswith(ID_STRING)
                            )
                        ) or not isinstance(value, str):
                            value = enc.encrypt_message_hf(
                                value, obfuscation(aes_key), ID_STRING, ID_STRING
                            ).decode("utf-8")
                    elif operation == "decrypt":
                        if (
                            isinstance(value, str)
                            and value.startswith(ID_STRING)
                            and value.endswith(ID_STRING)
                        ):
                            _, value = enc.decrypt_message_hf(
                                value,
                                obfuscation(aes_key),
                                ID_STRING,
                                ID_STRING,
                            )
                    else:
                        raise ValueError(f"Bogus operation {operation} given")
            # Let's run garbage collection after encryption / decryption operations
            # so the actual unobfuscated values don't stay in memory longer than needed
            gc.collect()
            return value

        return replace_in_iterable(
            full_config,
            _crypt_config,
            callable_wants_key=True,
            callable_wants_root_key=True,
        )
    except Exception as exc:
        logger.error(f"Cannot {operation} configuration: {exc}.")
        logger.debug("Trace:", exc_info=True)
        return False


def is_encrypted(full_config: dict) -> bool:
    is_encrypted = True

    def _is_encrypted(key, value) -> Any:
        nonlocal is_encrypted

        if key_should_be_encrypted(key, ENCRYPTED_OPTIONS):
            if value is not None:
                if isinstance(value, str) and (
                    not value.startswith(ID_STRING) or not value.endswith(ID_STRING)
                ):
                    is_encrypted = False
        return value

    replace_in_iterable(
        full_config,
        _is_encrypted,
        callable_wants_key=True,
        callable_wants_root_key=True,
    )
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


def evaluate_variables(
    repo_config: dict, monitoring_config: dict = None, full_config: dict = None
) -> dict:
    """
    Replace runtime variables with their corresponding value
    Also replaces human bytes notation with ints
    """

    def _evaluate_variables(_, value):
        if isinstance(value, str):
            if "${MACHINE_ID}" in value:
                machine_id = full_config.g("identity.machine_id")
                value = value.replace("${MACHINE_ID}", machine_id if machine_id else "")

            if "${MACHINE_GROUP}" in value:
                machine_group = full_config.g("identity.machine_group")
                value = value.replace(
                    "${MACHINE_GROUP}", machine_group if machine_group else ""
                )

            if "${MACHINE_TENANT}" in value:
                machine_tenant = full_config.g("identity.machine_tenant")
                value = value.replace("${MACHINE_TENANT}", machine_tenant if machine_tenant else "")

            if "${BACKUP_JOB}" in value:
                backup_job = repo_config.g("monitoring.backup_job")
                value = value.replace("${BACKUP_JOB}", backup_job if backup_job else "")

            if "${REPO_NAME}" in value:
                repo_name = repo_config.g("name")
                value = value.replace("${REPO_NAME}", repo_name if repo_name else "")

            if "${REPO_GROUP}" in value:
                repo_group = repo_config.g("repo_group")
                value = value.replace("${REPO_GROUP}", repo_group if repo_group else "")

            if "${HOSTNAME}" in value:
                value = value.replace("${HOSTNAME}", platform.node())
        if value == "":
            value = None
        return value

    # We need to make a loop to catch all nested variables (ie variable in a variable)
    # but we also need a max recursion limit
    # If each variable has two sub variables, we'd have max 4x2x2 loops
    # While this is not the most efficient way, we still get to catch all nested variables
    # and of course, we don't have thousands of lines to parse, so we're good
    if monitoring_config:
        maxcount = 4 * 2 * 2
        count = 0
        while count < maxcount:
            monitoring_config = replace_in_iterable(
                monitoring_config, _evaluate_variables, callable_wants_key=True
            )
            count += 1
        return monitoring_config
    count = 0
    maxcount = 4 * 2 * 2
    while count < maxcount:
        repo_config = replace_in_iterable(
            repo_config, _evaluate_variables, callable_wants_key=True
        )
        count += 1
    return repo_config


def expand_units(object_config: dict, unexpand: bool = False) -> dict:
    """
    Evaluate human bytes notation
    eg 50 KB to  50000 bytes
    eg 50 KiB to 51200 bytes
    and 50000 to 50 KB in unexpand mode
    """

    def _expand_units(key, value):
        if key in (
            "minimum_backup_size_error",  # Bytes default
            "exclude_files_larger_than",  # Bytes default
            "upload_speed",  # Bits default
            "download_speed",  # Bits default
        ):
            try:
                if value:
                    if unexpand:
                        if key in (
                            "minimum_backup_size_error",
                            "exclude_files_larger_than",
                        ):
                            return BytesConverter(value).human_iec_bytes
                        return BytesConverter(value).human_iec_bits
                    return BytesConverter(value)
                else:
                    if unexpand:
                        if key in (
                            "minimum_backup_size_error",
                            "exclude_files_larger_than",
                        ):
                            return BytesConverter(0).human_iec_bytes
                        return BytesConverter(0).human_iec_bits
                    return BytesConverter(0)
            except ValueError:
                logger.warning(
                    f'Cannot parse bytes value {key}:"{value}", setting to zero'
                )
                if unexpand:
                    if key in (
                        "minimum_backup_size_error",
                        "exclude_files_larger_than",
                    ):
                        return BytesConverter(0).human_iec_bytes
                    return BytesConverter(0).human_iec_bits
                return BytesConverter(0)
        return value

    return replace_in_iterable(object_config, _expand_units, callable_wants_key=True)


def extract_permissions_from_full_config(full_config: dict) -> dict:
    """
    Extract permissions and manager password from repo_uri tuple
    repo_config objects in memory are always "expanded"
    This function is in order to expand when loading config
    """
    for object_type in ("repos", "groups"):
        if full_config.g(object_type) is None:
            logger.info(f"No {object_type} found in config")
            continue
        for object_name in full_config.g(object_type).keys():
            repo_uri = full_config.g(f"{object_type}.{object_name}.repo_uri")
            if repo_uri:
                # Extract permissions and manager password from repo_uri if set as string
                if "," in repo_uri:
                    repo_uri = [item.strip() for item in repo_uri.split(",")]
                if isinstance(repo_uri, tuple) or isinstance(repo_uri, list):
                    if len(repo_uri) == 3:
                        repo_uri, permissions, manager_password = repo_uri
                        # Overwrite existing permissions / password if it was set in repo_uri
                        full_config.s(f"{object_type}.{object_name}.repo_uri", repo_uri)
                        full_config.s(
                            f"{object_type}.{object_name}.permissions", permissions
                        )
                        full_config.s(
                            f"{object_type}.{object_name}.manager_password",
                            manager_password,
                        )
                    else:
                        logger.error("Bogus extra information given in repo_uri")
                else:
                    logger.debug(
                        f"No extra information for {object_type} {object_name} found"
                    )
                    # If no permissions are set, we get to use default permissions
                    full_config.s(
                        f"{object_type}.{object_name}.permissions",
                        empty_config_dict["repos"]["default"]["permissions"],
                    )
                    full_config.s(f"{object_type}.{object_name}.manager_password", None)
    return full_config


def inject_permissions_into_full_config(full_config: dict) -> dict:
    """
    Make sure repo_uri is a tuple containing permissions and manager password
    This function is used before saving config

    NPF-SEC-00006: Never inject permissions if some are already present unless current manager password equals initial one
    """
    for object_type in ("repos", "groups"):
        for object_name in full_config.g(object_type).keys():
            repo_uri = full_config.g(f"{object_type}.{object_name}.repo_uri")
            manager_password = full_config.g(
                f"{object_type}.{object_name}.manager_password"
            )
            permissions = full_config.g(f"{object_type}.{object_name}.permissions")
            new_manager_password = full_config.g(
                f"{object_type}.{object_name}.new_manager_password"
            )
            # Getting current manager password is only needed in CLI mode, to avoid overwriting existing manager password
            current_manager_password = full_config.g(
                f"{object_type}.{object_name}.current_manager_password"
            )
            new_permissions = full_config.g(
                f"{object_type}.{object_name}.new_permissions"
            )

            # Always first consider there is no protection
            full_config.s(f"{object_type}.{object_name}.is_protected", False)

            # We may set new_password_manager to false to explicitly disabling password manager
            if (
                new_manager_password is not None
                and current_manager_password == manager_password
            ):
                full_config.s(
                    f"{object_type}.{object_name}.repo_uri",
                    (repo_uri, new_permissions, new_manager_password),
                )
                full_config.s(f"{object_type}.{object_name}.is_protected", True)
                logger.info(f"New permissions set for {object_type} {object_name}")
            elif new_manager_password:
                logger.critical(
                    f"Cannot set new permissions for {object_type} {object_name} without current manager password"
                )
            elif manager_password:
                full_config.s(
                    f"{object_type}.{object_name}.repo_uri",
                    (repo_uri, permissions, manager_password),
                )
                full_config.s(f"{object_type}.{object_name}.is_protected", True)
                logger.debug(f"Permissions exist for {object_type} {object_name}")

            # Don't keep decrypted manager password and permissions bare in config file
            # They should be injected in repo_uri tuple
            full_config.d(f"{object_type}.{object_name}.new_manager_password")
            full_config.d(f"{object_type}.{object_name}.current_manager_password")
            full_config.d(f"{object_type}.{object_name}.new_permissions")
            full_config.d(f"{object_type}.{object_name}.permissions")
            full_config.d(f"{object_type}.{object_name}.manager_password")
    return full_config


def get_manager_password(full_config: dict, repo_name: str) -> str:
    return full_config.g(f"repos.{repo_name}.manager_password")


def get_repo_config(
    full_config: dict, repo_name: str = "default", eval_variables: bool = True
) -> Tuple[dict, dict]:
    """
    Create inherited repo config
    Returns a dict containing the repo config, with expanded variables
    and a dict containing the repo inheritance status
    """

    def inherit_group_settings(
        repo_config: dict, group_config: dict
    ) -> Tuple[dict, dict]:
        """
        iter over group settings, update repo_config, and produce an identical version of repo_config
        called config_inheritance, where every value is replaced with a boolean which states inheritance status
        When lists are encountered, merge the lists, but product a dict in config_inheritance with list values: inheritance_bool
        """

        _repo_config = deepcopy(repo_config)
        _group_config = deepcopy(group_config)
        _config_inheritance = deepcopy(repo_config)
        # Make sure we make the initial config inheritance values False
        _config_inheritance = replace_in_iterable(_config_inheritance, lambda _: False)

        def _inherit_group_settings(
            _repo_config: dict, _group_config: dict, _config_inheritance: dict
        ) -> Tuple[dict, dict]:
            if isinstance(_group_config, dict):
                if _repo_config is None:
                    # Initialize blank if not set
                    _repo_config = CommentedMap()
                    _config_inheritance = CommentedMap()
                for key, value in _group_config.items():
                    if isinstance(value, dict):
                        __repo_config, __config_inheritance = _inherit_group_settings(
                            _repo_config.g(key),
                            value,
                            _config_inheritance.g(key),
                        )
                        _repo_config.s(key, __repo_config)
                        _config_inheritance.s(key, __config_inheritance)
                    elif isinstance(value, list):
                        if isinstance(_repo_config.g(key), list):
                            merged_lists = _repo_config.g(key) + value
                        # Case where repo config already contains non list info but group config has list
                        elif _repo_config.g(key):
                            merged_lists = [_repo_config.g(key)] + value
                        else:
                            merged_lists = value

                        # Special case when merged lists contain multiple dicts, we'll need to merge dicts
                        # unless lists have other object types than dicts
                        merged_items_dict = {}
                        can_replace_merged_list = True
                        for list_elt in merged_lists:
                            if isinstance(list_elt, dict):
                                merged_items_dict.update(list_elt)
                            else:
                                can_replace_merged_list = False
                        if can_replace_merged_list:
                            merged_lists = merged_items_dict

                        # Make sure we avoid duplicates in lists while preserving order (do not use sets here)
                        merged_lists = list(dict.fromkeys(merged_lists))
                        _repo_config.s(key, merged_lists)
                        _config_inheritance.s(key, {})
                        for v in merged_lists:
                            _grp_conf = value
                            # Make sure we test inheritance against possible lists
                            if not isinstance(_grp_conf, list):
                                _grp_conf = [_grp_conf]
                            if _grp_conf:
                                for _grp_conf_item in _grp_conf:
                                    if v == _grp_conf_item:
                                        # We need to avoid using dot notation here since value might contain dots
                                        _config_inheritance.g(key)[v] = True
                                        # _config_inheritance.s(f"{key}.{v}", True)
                                        break
                                    else:
                                        _config_inheritance.g(key)[v] = False
                                        # _config_inheritance.s(f"{key}.{v}", False)
                            else:
                                _config_inheritance.g(key)[v] = False
                    else:
                        # repo_config may or may not already contain data
                        if _repo_config is None or _repo_config == "":
                            _repo_config = CommentedMap()
                            _config_inheritance = CommentedMap()
                        if _repo_config.g(key) is None or _repo_config.g(key) == "":
                            _repo_config.s(key, value)
                            _config_inheritance.s(key, True)
                        # Case where repo_config contains list but group info has single str
                        elif (
                            isinstance(_repo_config.g(key), list)
                            and value is not None
                            and value != ""
                        ):
                            merged_lists = _repo_config.g(key) + [value]

                            # Special case when merged lists contain multiple dicts, we'll need to merge dicts
                            # unless lists have other object types than dicts
                            merged_items_dict = {}
                            can_replace_merged_list = True
                            for list_elt in merged_lists:
                                if isinstance(list_elt, dict):
                                    merged_items_dict.update(list_elt)
                                else:
                                    can_replace_merged_list = False
                            if can_replace_merged_list:
                                merged_lists = merged_items_dict

                            # Make sure we avoid duplicates in lists while preserving order (do not use sets here)
                            merged_lists = list(dict.fromkeys(merged_lists))
                            _repo_config.s(key, merged_lists)

                            _config_inheritance.s(key, {})
                            for v in merged_lists:
                                _grp_conf = value
                                # Make sure we test inheritance against possible lists
                                if not isinstance(_grp_conf, list):
                                    _grp_conf = [_grp_conf]
                                if _grp_conf:
                                    for _grp_conf_item in _grp_conf:
                                        if v == _grp_conf_item:
                                            _config_inheritance.g(key)[v] = True
                                            # _config_inheritance.s(f"{key}.{v}", True)
                                            break
                                        else:
                                            _config_inheritance.g(key)[v] = False
                                            # _config_inheritance.s(f"{key}.{v}", False)
                                else:
                                    _config_inheritance.g(key)[v] = False
                        else:
                            # In other cases, just keep repo config
                            _config_inheritance.s(key, False)

            return _repo_config, _config_inheritance

        return _inherit_group_settings(_repo_config, _group_config, _config_inheritance)

    if not full_config:
        return None, None

    try:
        # Let's make a copy of config since it's a "pointer object"
        repo_config = deepcopy(full_config.g(f"repos.{repo_name}"))
        if not repo_config:
            logger.error(
                f"No repo with name {repo_name} found in config. If running CLI, please use --repo-name or --repo-group"
            )
            return None, None
    except KeyError:
        logger.error(f"No repo with name {repo_name} found in configuration file")
        return None, None

    try:
        repo_group = full_config.g(f"repos.{repo_name}.repo_group")
        group_config = full_config.g(f"groups.{repo_group}")
    except KeyError:
        logger.error(f"Repo {repo_name} has no group, reset to first available group")
        try:
            first_group = get_group_list(full_config)[0]
            full_config.s(f"repos.{repo_name}.repo_group", first_group)
            group_config = full_config.g(f"groups.{first_group}")
        except IndexError:
            logger.error("No group found in config")
            group_config = {}

    repo_config.s("name", repo_name)
    repo_config.s("uuid", gen_uuid_from_path(repo_name))
    repo_config.s("config_uuid", full_config.g("uuid"))
    repo_config, config_inheritance = inherit_group_settings(repo_config, group_config)

    if eval_variables:
        repo_config = evaluate_variables(
            repo_config=repo_config, full_config=full_config
        )
    repo_config = expand_units(repo_config, unexpand=True)

    return repo_config, config_inheritance


def get_group_config(
    full_config: dict, group_name: str, eval_variables: bool = True
) -> dict:
    try:
        group_config = deepcopy(full_config.g(f"groups.{group_name}"))
    except KeyError:
        logger.error(f"No group with name {group_name} found in config")
        return None

    if eval_variables:
        group_config = evaluate_variables(
            repo_config=group_config, full_config=full_config
        )
    group_config = expand_units(group_config, unexpand=True)
    return group_config


def _get_config_file_checksum(config_file: Path) -> str:
    """
    It's nice to log checksums of config file to see whenever it was changed
    """
    with open(config_file, "rb") as fh:
        cur_hash = 0
        while True:
            s = fh.read(65536)
            if not s:
                break
            cur_hash = zlib.crc32(s, cur_hash)
        return "%08X" % (cur_hash & 0xFFFFFFFF)


def _migrate_config_dict(full_config: dict, old_version: str, new_version: str) -> dict:
    """
    Migrate config dict from old version to new version
    This is used when config file version is not the same as current version
    """
    logger.info(f"Migrating config file from version {old_version} to {new_version}")

    def _migrate_retention_policy_3_0_0_to_3_0_3(
        full_config: dict,
        object_name: str,
        object_type: str,
    ) -> dict:
        try:
            if full_config.g(
                f"{object_type}.{object_name}.repo_opts.retention_policy.tags"
            ) is not None and not full_config.g(
                f"{object_type}.{object_name}.repo_opts.retention_policy.keep_tags"
            ):
                full_config.s(
                    f"{object_type}.{object_name}.repo_opts.retention_policy.keep_tags",
                    full_config.g(
                        f"{object_type}.{object_name}.repo_opts.retention_policy.tags"
                    ),
                )
                full_config.d(
                    f"{object_type}.{object_name}.repo_opts.retention_policy.tags"
                )
                logger.info(
                    f"Migrated {object_name} retention policy tags to keep_tags"
                )
        except KeyError:
            logger.info(
                f"{object_type} {object_name} has no retention policy, skipping migration"
            )
        return full_config

    def _migrate_compression_3_0_0_to_3_0_4(
        full_config: dict,
        object_name: str,
        object_type: str,
    ) -> dict:
        try:
            if (
                full_config.g(f"{object_type}.{object_name}.repo_opts.compression")
                is None
                and full_config.g(
                    f"{object_type}.{object_name}.backup_opts.compression"
                )
                is not None
            ):
                full_config.s(
                    f"{object_type}.{object_name}.repo_opts.compression",
                    full_config.g(
                        f"{object_type}.{object_name}.backup_opts.compression"
                    ),
                )
                full_config.d(f"{object_type}.{object_name}.backup_opts.compression")
                logger.info(f"Migrated {object_name} compression to repo_opts")
        except KeyError:
            logger.info(
                f"{object_type} {object_name} has no compression, skipping migration"
            )
        return full_config

    def _migrate_monitoring_3_0_4_to_3_1_0(
        full_config: dict,
        object_name: str,
        object_type: str,
    ) -> dict:

        # Change prometheus "metrics" to "enabled" to be consistent with other monitoring entries
        try:
            prometheus_monitoring = full_config.g("global_prometheus.metrics")
            full_config.d("global_prometheus.metrics")
            full_config.s("global_prometheus.enabled", prometheus_monitoring)
        except KeyError:
            logger.info("No global_prometheus migration is done")

        # Change email "enable" to "enabled" to be consistent with other monitoring entries
        try:
            email_monitoring = full_config.g("global_email.enable")
            full_config.d("global_email.enable")
            full_config.s("global_email.enabled", email_monitoring)
        except KeyError:
            logger.info("No global_email migration is done")

        # Add new monitoring sections
        try:
            if not full_config.g("global_zabbix"):
                full_config.s(
                    "global_zabbix", deepcopy(empty_config_dict["global_zabbix"])
                )
        except KeyError:
            logger.info("No global_zabbix migration is done")

        try:
            if not full_config.g("global_healthchecksio"):
                full_config.s(
                    "global_healthchecksio",
                    deepcopy(empty_config_dict["global_healthchecksio"]),
                )
        except KeyError:
            logger.info("No global_healthchecksio migration is done")

        try:
            if not full_config.g("global_webhooks"):
                full_config.s(
                    "global_webhooks", deepcopy(empty_config_dict["global_webhooks"])
                )
        except KeyError:
            logger.info("No global_webhooks migration is done")

        monitoring = full_config.g(f"{object_type}.{object_name}.prometheus")
        if monitoring is not None:
            full_config.d(f"{object_type}.{object_name}.prometheus")
            full_config.s(
                f"{object_type}.{object_name}.monitoring", deepcopy(monitoring)
            )
        else:
            full_config.s(
                f"{object_type}.{object_name}.monitoring",
                deepcopy(empty_config_dict["groups"]["default_group"]["monitoring"]),
            )
        try:
            full_config.d(f"global_prometheus.instance")
        except KeyError:
            pass
        try:
            full_config.d(f"global_email.instance")
        except KeyError:
            pass
        logger.info(
            f"Migrated {object_name} prometheus monitoring to monitoring section"
        )

        additional_labels = full_config.g("global_prometheus.additional_labels")
        if additional_labels is not None and additional_labels:
            full_config.s(
                f"{object_type}.{object_name}.monitoring.additional_labels",
                additional_labels,
            )
            logger.info(
                f"Migration additional_labels to monitoring section for {object_type} {object_name}"
            )

        return full_config

    def _apply_global_migration_3_0_4_to_3_1_0(full_config: dict) -> dict:
        # Clean old global settings if present
        full_config.d("global_prometheus.additional_labels")
        full_config.d("global_email.additional_labels")

        # Migrate earlier email format:
        """
        global_email:
            recipients: [list of recipients]
            on_backup_success: true
            on_backup_failure: true
            on_operations_success: false
            on_operations_failure: true

        to:
        
        global_email:
            recipients:
                on_backup_success: [list of recipients]
                on_backup_failure: [list of recipients]
                on_operations_success: [list of recipients]
                on_operations_failure: [list of recipients]
        """
        try:
            if isinstance(full_config.g("global_email.recipients"), list) or isinstance(
                full_config.g("global_email.recipients"), str
            ):
                # Convert to list if single address was given
                if isinstance(full_config.g("global_email.recipients"), str):
                    full_config.s(
                        "global_email.recipients",
                        [full_config.g("global_email.recipients")],
                    )
                recipients = {
                    "on_backup_success": [],
                    "on_backup_failure": [],
                    "on_operations_success": [],
                    "on_operations_failure": [],
                }
                for recipient in full_config.g("global_email.recipients"):
                    if full_config.g("global_email.on_backup_success"):
                        recipients["on_backup_success"].append(recipient)
                    if full_config.g("global_email.on_backup_failure"):
                        recipients["on_backup_failure"].append(recipient)
                    if full_config.g("global_email.on_operations_success"):
                        recipients["on_operations_success"].append(recipient)
                    if full_config.g("global_email.on_operations_failure"):
                        recipients["on_operations_failure"].append(recipient)
                full_config.s("global_email.recipients", recipients)
                full_config.d("global_email.on_backup_success")
                full_config.d("global_email.on_backup_failure")
                full_config.d("global_email.on_operations_success")
                full_config.d("global_email.on_operations_failure")
        except KeyError:
            logger.info("No global_email.recipients key to migrate")

        return full_config

    def _apply_migrations(
        full_config: dict,
        object_name: str,
        object_type: str,
    ) -> dict:
        if version_parse(old_version) < version_parse("3.0.3"):
            full_config = _migrate_retention_policy_3_0_0_to_3_0_3(
                full_config, object_name, object_type
            )
        if version_parse(old_version) < version_parse("3.0.4"):
            full_config = _migrate_compression_3_0_0_to_3_0_4(
                full_config, object_name, object_type
            )
        if version_parse(old_version) < version_parse("3.1.0"):
            full_config = _migrate_monitoring_3_0_4_to_3_1_0(
                full_config, object_name, object_type
            )
        # no need to return full_config since CommentedMap is a pointer object
        return full_config

    # Apply per object migrations
    for repo in get_repo_list(full_config):
        full_config = _apply_migrations(full_config, repo, "repos")

    for group in get_group_list(full_config):
        full_config = _apply_migrations(full_config, group, "groups")

    # Apply global migrations
    if version_parse(old_version) < version_parse("3.1.0"):
        full_config = _apply_global_migration_3_0_4_to_3_1_0(full_config)

    full_config.s("conf_version", new_version)
    return full_config


def _load_config_file(config_file: Path) -> Union[bool, dict]:
    """
    Checks whether config file is valid
    """
    try:
        with open(config_file, "r", encoding="utf-8") as file_handle:
            yaml = YAML(typ="rt")
            full_config = yaml.load(file_handle)
            if not full_config or not isinstance(full_config, dict):
                logger.critical(f"Config file {config_file} seems empty or invalid !")
                return False
            if (
                full_config.g("audience")
                and full_config.g("audience") != CURRENT_AUDIENCE
            ):
                logger.critical(
                    f"Config file {config_file} is for audience {full_config.g('audience')}, but current audience is {CURRENT_AUDIENCE}. Won't load this."
                )
                return False
            try:
                conf_version = version_parse(str(full_config.g("conf_version")))
                if not conf_version:
                    logger.critical(
                        f"Config file {config_file} has no configuration version. Is this a valid npbackup config file?"
                    )
                    return False
                if conf_version < version_parse(
                    MIN_MIGRATABLE_CONF_VERSION
                ) or conf_version > version_parse(MAX_CONF_VERSION):
                    logger.critical(
                        f"Config file version {str(conf_version)} is not in required version range min={MIN_MIGRATABLE_CONF_VERSION}, max={MAX_CONF_VERSION}"
                    )
                    return False
                if conf_version < version_parse(MIN_CONF_VERSION):
                    try:
                        full_config = _migrate_config_dict(
                            full_config, str(conf_version), MIN_CONF_VERSION
                        )
                    except Exception as exc:
                        logger.critical(
                            f"Cannot migrate config file {config_file} from version {str(conf_version)} to version {MIN_CONF_VERSION}: {exc}. Please fix your config file manually."
                        )
                        logger.error("Trace:", exc_info=True)
                        sys.exit(1)
                    logger.info("Writing migrated config file")
                    save_config(config_file, full_config)
            except (AttributeError, TypeError, InvalidVersion) as exc:
                logger.critical(
                    f"Cannot read conf version from config file {config_file}, which seems bogus: {exc}"
                )
                logger.debug("Trace:", exc_info=True)
                return False
            logger.info(
                f"Loaded config {_get_config_file_checksum(config_file)} in {config_file.absolute()}"
            )
            return full_config
    except OSError as exc:
        logger.critical(f"Cannot load configuration file from {config_file}: {exc}")
        logger.debug("Trace:", exc_info=True)
        return False
    except ScannerError as exc:
        logger.critical(f"Config file {config_file} is not a valid yaml file: {exc}")
        logger.debug("Trace:", exc_info=True)
        sys.exit(1)


def load_config(config_file: Path) -> Optional[dict]:
    full_config = _load_config_file(config_file)
    if not full_config:
        return None
    config_file_is_updated = False

    # Make sure we expand every key that should be a list into a list
    # We'll use iter_over_keys instead of replace_in_iterable to avoid changing list contents by lists
    # This basically allows "bad" formatted (ie manually written yaml) to be processed correctly
    # without having to deal with various errors
    def _make_struct(key: str, value: Union[str, int, float, dict, list]) -> Any:
        if key in (
            "paths",
            "tags",
            "exclude_patterns",
            "exclude_files",
            "pre_exec_commands",
            "post_exec_commands",
        ):
            if not isinstance(value, list):
                if value is not None:
                    value = [value]
                else:
                    value = []

        if key in (
            "additional_labels",
            "env_variables",
            "encrypted_env_variables",
        ):
            if not isinstance(value, dict):
                if value is None:
                    value = CommentedMap()
        return value

    iter_over_keys(full_config, _make_struct)

    # Check if we need to encrypt some variables
    if not is_encrypted(full_config):
        logger.info("Encrypting non encrypted data in configuration file")
        config_file_is_updated = True
    # Decrypt variables
    _full_config = crypt_config(
        full_config, AES_KEY, ENCRYPTED_OPTIONS, operation="decrypt"
    )
    if _full_config is False:
        if EARLIER_AES_KEYS:
            logger.info("Trying to migrate encryption key")
            earlier_aes_key_works = False
            for earlier_key in EARLIER_AES_KEYS:
                full_config = crypt_config(
                    full_config, earlier_key, ENCRYPTED_OPTIONS, operation="decrypt"
                )
                if full_config is False:
                    msg = "Cannot decrypt config file. Looks like our keys don't match."
                    logger.info(msg)

                else:
                    config_file_is_updated = True
                    logger.info("Successfully migrated encryption key")
                    earlier_aes_key_works = True
                    break
            if not earlier_aes_key_works:
                msg = "None of our earlier encryption keys did work."
                logger.critical(msg)
                raise EnvironmentError(msg)
        else:
            msg = "Cannot decrypt config file"
            logger.critical(msg)
            raise EnvironmentError(msg)
    else:
        full_config = _full_config

    # Check if we need to expand random vars
    is_modified, full_config = has_random_variables(full_config)
    if is_modified:
        config_file_is_updated = True
        logger.info("Handling random variables in configuration files")

    # Extract permissions / password from repo if set
    full_config = extract_permissions_from_full_config(full_config)

    # Inject config UUID for local storage tracking
    full_config.s("uuid", gen_uuid_from_path(config_file))

    # save config file if needed
    if config_file_is_updated:
        logger.info("Updating config file")
        save_config(config_file, full_config)
    return full_config


def save_config(config_file: Path, full_config: dict) -> bool:
    try:
        full_config = inject_permissions_into_full_config(full_config)
        full_config.s("audience", CURRENT_AUDIENCE)
        with open(config_file, "w", encoding="utf-8") as file_handle:
            if not is_encrypted(full_config):
                full_config = crypt_config(
                    full_config, AES_KEY, ENCRYPTED_OPTIONS, operation="encrypt"
                )
            yaml = YAML(typ="rt")
            yaml.dump(full_config, file_handle)
        # Since yaml is a "pointer object", we need to decrypt after saving
        full_config = crypt_config(
            full_config, AES_KEY, ENCRYPTED_OPTIONS, operation="decrypt"
        )
        # We also need to extract permissions again
        full_config = extract_permissions_from_full_config(full_config)
        logger.info(f"Saved configuration file {config_file}")
        return True
    except OSError as exc:
        logger.critical(f"Cannot save configuration file to {config_file}: {exc}")
        return False


def get_repo_list(full_config: dict) -> List[str]:
    if full_config:
        try:
            return list(full_config.g("repos").keys())
        except AttributeError:
            pass
    return []


def get_group_list(full_config: dict) -> List[str]:
    if full_config:
        try:
            return list(full_config.g("groups").keys())
        except AttributeError:
            pass
    return []


def get_object_list(full_config: dict) -> List[str]:
    """
    Get list of all objects (repos + groups) in config
    """
    if full_config:
        return get_repo_list(full_config) + get_group_list(full_config)
    return []


def get_object_names_and_types(full_config: dict) -> dict:
    """
    Get dict of all objects (repos + groups) in config with their type
    as:
        {
            "repo_name": "repos",
            "group_name": "groups",
        }
    """
    object_type_dict = {}
    if full_config:
        for repo in get_repo_list(full_config):
            object_type_dict[repo] = "repos"
        for group in get_group_list(full_config):
            object_type_dict[group] = "groups"
    return object_type_dict


def get_repos_by_group(full_config: dict, group: str) -> List[str]:
    """
    Return repo list by group
    If special group __all__ is given, return all repos
    """
    repo_list = []
    if full_config:
        for repo in get_repo_list(full_config):
            if (
                full_config.g(f"repos.{repo}.repo_group") == group or group == "__all__"
            ) and group not in repo_list:
                repo_list.append(repo)
    return repo_list


def get_anonymous_repo_config(repo_config: dict, show_encrypted: bool = False) -> dict:
    """
    Replace each encrypted value with
    """

    def _get_anonymous_repo_config(key: str, value: Any) -> Any:
        if key_should_be_encrypted(key, ENCRYPTED_OPTIONS):
            if isinstance(value, list):
                for i, _ in enumerate(value):
                    value[i] = "__(o_O)__"
            else:
                value = "__(o_O)__"
        return value

    # NPF-SEC-00008: Don't show manager password / sensitive data with --show-config unless it's empty
    if repo_config.get("manager_password", None):
        repo_config["manager_password"] = "__(x_X)__"
    repo_config.pop("update_manager_password", None)
    if show_encrypted:
        return repo_config
    return replace_in_iterable(
        repo_config,
        _get_anonymous_repo_config,
        callable_wants_key=True,
        callable_wants_root_key=True,
    )


def get_monitoring_config(repo_config: dict, full_config: dict):
    global_monitoring = CommentedMap()
    if full_config:
        try:
            global_monitoring.s("global_prometheus", full_config.g("global_prometheus"))
        except AttributeError:
            pass
        try:
            global_monitoring.s("global_zabbix", full_config.g("global_zabbix"))
        except AttributeError:
            pass
        try:
            global_monitoring.s(
                "global_healthchecksio", full_config.g("global_healthchecksio")
            )
        except AttributeError:
            pass
        try:
            global_monitoring.s("global_webhooks", full_config.g("global_webhooks"))
        except AttributeError:
            pass
        try:
            global_monitoring.s("global_email", full_config.g("global_email"))
        except AttributeError:
            pass
        try:
            global_monitoring.s("identity", full_config.g("identity"))
        except AttributeError:
            pass
    if repo_config:
        global_monitoring = evaluate_variables(
            repo_config, global_monitoring, full_config
        )
    else:
        logger.error(
            "Missing repo config while trying to get monitoring config. Identity will not be evaluated"
        )
    return global_monitoring
