#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.common_gui_logic"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026040301"


import os
from typing import List, Tuple, Optional, Union
import re
from logging import getLogger
import FreeSimpleGUI as sg
from ruamel.yaml.comments import CommentedMap
from datetime import datetime
from copy import deepcopy
from ofunctions.threading import threaded
import npbackup.gui.common_gui
from npbackup.gui.helpers import popup_error, password_complexity, WaitWindow
from npbackup.core.i18n_helper import _t
import npbackup.configuration
from npbackup.core.monitoring.email import EmailMonitor
from npbackup.gui.constants import combo_boxes
from ofunctions.misc import get_key_from_value, BytesConverter
from ofunctions.mailer import is_mail_address
import npbackup.task
from resources.customization import (
    INHERITED_ICON,
    NON_INHERITED_ICON,
    FILE_ICON,
    FOLDER_ICON,
    INHERITED_FILE_ICON,
    INHERITED_FOLDER_ICON,
    TREE_ICON,
    INHERITED_TREE_ICON,
    IRREGULAR_FILE_ICON,
    INHERITED_IRREGULAR_FILE_ICON,
    MISSING_FILE_ICON,
    INHERITED_MISSING_FILE_ICON,
    SYMLINK_ICON,
    INHERITED_SYMLINK_ICON,
    TREE_ICON as SYSTEM_ICON,  # WIP features
    TREE_ICON as HYPER_V_ICON,  # WIP features
    TREE_ICON as KVM_ICON,  # WIP features
)

logger = getLogger()

# Note for my future self
# SimpleGUI TreeData used to need monkeypatching delete function until FreeSimpleGUI with npbfixes patch which we use here
# sg.TreeData.delete = delete

# Don't let SimpleGUI handle key errors since we might have new keys in config file
sg.set_options(
    suppress_raise_key_errors=True,
    suppress_error_popups=True,
    suppress_key_guessing=True,
)

ENCRYPTED_DATA_PLACEHOLDER = "<{}>".format(_t("config_gui.encrypted_data"))

# multi row counters
COLUMN_LIST_COUNTERS = {
    "EMAIL-RECIPIENTS": 0,
    "RETENTION-APPLY-ON-TAG": 0,
    "RETENTION-KEEP-TAG": 0,
    "BACKUP-TAG": 0,
}
column_list_keys = {
    "backup_opts.tags": "BACKUP-TAG",
    "repo_opts.retention_policy.keep_tags": "RETENTION-KEEP-TAG",
    "repo_opts.retention_policy.apply_on_tags": "RETENTION-APPLY-ON-TAG",
}

# Init fresh config objects
BAD_KEYS_FOUND_IN_CONFIG = set()

backup_paths_tree = sg.TreeData()
exclude_patterns_tree = sg.TreeData()
exclude_files_tree = sg.TreeData()
pre_exec_commands_tree = sg.TreeData()
post_exec_commands_tree = sg.TreeData()
monitoring_additional_labels_tree = sg.TreeData()
env_variables_tree = sg.TreeData()
encrypted_env_variables_tree = sg.TreeData()


#### FILE ICON RELATED LOGIC ####
def get_icons_per_file(file_path: str) -> Tuple[str, bytes]:
    """
    Get icons depending on file/folder existing paths
    """
    try:
        if not file_path:
            icon = MISSING_FILE_ICON
            inherited_icon = INHERITED_MISSING_FILE_ICON
        elif os.path.islink(file_path):
            icon = SYMLINK_ICON
            inherited_icon = INHERITED_SYMLINK_ICON
        elif os.path.isdir(file_path):
            if os.access(file_path, os.X_OK):
                icon = FOLDER_ICON
                inherited_icon = INHERITED_FOLDER_ICON
            else:
                icon = IRREGULAR_FILE_ICON
                inherited_icon = INHERITED_IRREGULAR_FILE_ICON
        elif os.path.isfile(file_path):
            icon = FILE_ICON
            inherited_icon = INHERITED_FILE_ICON
        else:
            icon = MISSING_FILE_ICON
            inherited_icon = INHERITED_MISSING_FILE_ICON
    except (OSError, PermissionError, TypeError) as exc:
        # We might not be able to check paths that are not present
        # on current computer when preparing configuration files
        # In that case, just assume it's a file
        logger.debug(f"Current path {file_path} cannot be processed: {exc}")
        icon = IRREGULAR_FILE_ICON
        inherited_icon = INHERITED_IRREGULAR_FILE_ICON

    return icon, inherited_icon


#### MANAGER PASSWORD RELATED LOGIC ####


def ask_manager_password(manager_password: str) -> bool:
    if manager_password:
        if sg.popup_get_text(
            _t("config_gui.set_manager_password"), password_char="*"
        ) == str(manager_password):
            return True
        popup_error(_t("config_gui.wrong_password"))
        return False
    return True


def set_permissions(full_config: dict, object_type: str, object_name: str) -> dict:
    """
    Sets repo wide repo_uri / password / permissions
    """
    if object_type == "groups":
        popup_error(_t("config_gui.permissions_only_for_repos"))
        return full_config
    permissions = list(combo_boxes["permissions"].values())
    current_perm = full_config.g(f"{object_type}.{object_name}.permissions")
    if not current_perm:
        # So we need to represent no permission as full in GUI, so if not set, let's take highest permission
        current_perm = permissions[-1]
    else:
        current_perm = combo_boxes["permissions"][current_perm]
    manager_password = full_config.g(f"{object_type}.{object_name}.manager_password")

    layout = [
        [
            sg.Text(_t("config_gui.permissions"), size=(40, 1)),
            sg.Combo(permissions, default_value=current_perm, key="permissions"),
        ],
        [sg.HorizontalSeparator()],
        [
            sg.Text(_t("config_gui.set_manager_password"), size=(40, 1)),
            sg.Input(
                None,
                key="-MANAGER-PASSWORD-",
                size=(50, 1),
                password_char="*",
            ),
        ],
        [
            sg.Push(),
            sg.Button(
                _t("config_gui.remove_password"),
                key="--SUPPRESS-PASSWORD--",
                button_color="red",
            ),
            sg.Button(_t("generic.cancel"), key="--CANCEL--"),
            sg.Button(_t("generic.accept"), key="--ACCEPT--"),
        ],
    ]

    # We need to set current_manager_password variable to make sure we have sufficient permissions to modify settings
    full_config.s(
        f"{object_type}.{object_name}.current_manager_password",
        full_config.g(f"{object_type}.{object_name}.manager_password"),
    )

    window = sg.Window(
        _t("config_gui.permissions"),
        layout,
        keep_on_top=True,
        no_titlebar=False,
        grab_anywhere=True,
    )
    window.finalize()
    # Stupid fix because using window update method will fill input with "0" if False is given
    window["-MANAGER-PASSWORD-"].Update(manager_password if manager_password else "")
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--CANCEL--"):
            break
        if event == "--ACCEPT--":
            if not values["-MANAGER-PASSWORD-"]:
                popup_error(
                    _t("config_gui.setting_permissions_requires_manager_password"),
                )
                continue

            if not password_complexity(values["-MANAGER-PASSWORD-"]):
                popup_error(_t("config_gui.password_too_simple"))
                continue
            if not values["permissions"] in permissions:
                popup_error(_t("generic.bogus_data_given"))
                continue
            # Transform translated permission value into key
            permission = get_key_from_value(
                combo_boxes["permissions"], values["permissions"]
            )
            full_config.s(f"{object_type}.{object_name}.new_permissions", permission)
            full_config.s(
                f"{object_type}.{object_name}.new_manager_password",
                values["-MANAGER-PASSWORD-"],
            )
            break
        if event == "--SUPPRESS-PASSWORD--":
            full_config.s(f"{object_type}.{object_name}.new_permissions", "full")
            full_config.s(f"{object_type}.{object_name}.new_manager_password", False)
            break
    window.close()
    return full_config


#### GET TASK USER AND PASSWORD ####


def get_user_and_password_for_run_as() -> Tuple[Optional[str], Optional[str]]:
    layout = [
        [
            sg.Text(
                _t("config_gui.run_task_as_explanation"), size=(90, 4), expand_x=True
            ),
        ],
        [
            sg.Text(_t("config_gui.run_task_as"), size=(40, 1)),
            sg.Input(key="-RUN-AS-USER-", size=(50, 1)),
        ],
        [
            sg.Text(_t("generic.password").capitalize(), size=(40, 1)),
            sg.Input(
                key="-RUN-AS-PASSWORD-",
                size=(50, 1),
                password_char="*",
            ),
        ],
        [
            sg.Push(),
            sg.Button(_t("generic.cancel"), key="--CANCEL--"),
            sg.Button(_t("generic.accept"), key="--ACCEPT--"),
        ],
    ]
    window = sg.Window(
        _t("config_gui.run_task_as"),
        layout,
        keep_on_top=True,
        no_titlebar=False,
        grab_anywhere=True,
    )
    run_as_user = None
    password = None
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--CANCEL--"):
            break
        if event == "--ACCEPT--":
            run_as_user = values["-RUN-AS-USER-"]
            password = values["-RUN-AS-PASSWORD-"]
            if not run_as_user or not password:
                popup_error(_t("config_gui.run_task_as_requires_user_and_password"))
                continue
            break
    window.close()
    return run_as_user, password


#### OBJECT RELATED LOGIC ###


def create_object(window: sg.Window, full_config: dict) -> dict:
    object_type = None
    object_name = None
    layout = [
        [
            sg.Text(_t("generic.type")),
            sg.Combo(["repo", "group"], default_value="repo", key="-OBJECT-TYPE-"),
            sg.Text(_t("generic.name")),
            sg.Input(key="-OBJECT-NAME-"),
        ],
        [
            sg.Push(),
            sg.Button(_t("generic.cancel"), key="--CANCEL--"),
            sg.Button(_t("generic.accept"), key="--ACCEPT--"),
        ],
    ]

    subwindow = sg.Window(
        _t("config_gui.create_object"),
        layout=layout,
        keep_on_top=True,
        no_titlebar=False,
        grab_anywhere=True,
    )
    while True:
        event, values = subwindow.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--CANCEL--"):
            break
        if event == "--ACCEPT--":
            object_type = "groups" if values["-OBJECT-TYPE-"] == "group" else "repos"
            object_name = values["-OBJECT-NAME-"]
            if object_name is None or object_name == "" or "." in object_name:
                popup_error(_t("config_gui.object_name_cannot_be_empty"))
                continue
            if object_name == "__all__":
                popup_error(_t("config_gui.object_name_cannot_be_all"))
                continue
            if object_type == "repos":
                if full_config.g(f"{object_type}.{object_name}"):
                    popup_error(_t("config_gui.repo_already_exists"))
                    continue
                full_config.s(f"{object_type}.{object_name}", CommentedMap())
                full_config.s(
                    f"{object_type}.{object_name}",
                    npbackup.configuration.get_default_repo_config(),
                )
                break
            elif object_type == "groups":
                if full_config.g(f"{object_type}.{object_name}"):
                    popup_error(_t("config_gui.group_already_exists"))
                    continue
                full_config.s(
                    f"{object_type}.{object_name}",
                    npbackup.configuration.get_default_group_config(),
                )
                break
            else:
                raise ValueError("Bogus object type given")
    subwindow.close()
    if object_type and object_name:
        full_config = update_object_gui(
            window,
            full_config,
            object_type,
            object_name,
            unencrypted=False,
            is_wizard=False,
        )
        update_global_gui(window, full_config, unencrypted=False, is_wizard=False)
    return full_config, object_type, object_name


def get_objects(full_config) -> List[str]:
    """
    Adds repos and groups in a list for combobox
    """
    object_list = []
    for repo in npbackup.configuration.get_repo_list(full_config):
        object_list.append(create_object_name_for_combo("repos", repo))
    for group in npbackup.configuration.get_group_list(full_config):
        object_list.append(create_object_name_for_combo("groups", group))
    return object_list


def delete_object(window: sg.Window, full_config: dict, full_object_name: str) -> dict:
    object_type, object_name = get_object_from_combo(full_object_name)
    if not object_type and not object_name:
        popup_error(_t("config_gui.no_object_to_delete"))
        return full_config
    result = sg.popup(
        _t("config_gui.are_you_sure_to_delete") + f" {object_type} {object_name} ?",
        keep_on_top=True,
        custom_text=(_t("generic.no"), _t("generic.yes")),
    )
    if result == _t("generic.yes"):
        full_config.d(f"{object_type}.{object_name}")
        full_config = update_object_gui(
            window, full_config, None, unencrypted=False, is_wizard=False
        )
        update_global_gui(window, full_config, unencrypted=False, is_wizard=False)
    return full_config


def get_object_from_combo(combo_value: str) -> Tuple[str, str]:
    """
    Extracts selected object from combobox
    Returns object type and name
    """
    try:
        if combo_value.startswith("Repo: "):
            object_type = "repos"
            object_name = combo_value[len("Repo: ") :]
        elif combo_value.startswith("Group: "):
            object_type = "groups"
            object_name = combo_value[len("Group: ") :]
        else:
            object_type = None
            object_name = None
            logger.error(
                f"Could not obtain object_type and object_name from string {combo_value}"
            )
    except AttributeError:
        object_type = None
        object_name = None
        logger.error(f"Could not obtain object_type and object_name from {combo_value}")
    return object_type, object_name


def create_object_name_for_combo(object_type: str, object_name: str) -> str:
    """
    Creates a string to be displayed in object selector combobox from object type and name
    """
    if object_type == "repos":
        return f"Repo: {object_name}"
    elif object_type == "groups":
        return f"Group: {object_name}"
    else:
        logger.error(f"Bogus object type given: {object_type}")
        return None


def update_object_selector(
    window: sg.Window,
    full_config: dict,
    object_name: str = None,
    object_type: str = None,
) -> Tuple[str, str]:
    object_list = get_objects(full_config)
    if not object_name or not object_type:
        if len(object_list) > 0:
            obj = object_list[0]
        else:
            obj = None
    else:
        # We need to remove the "s" and the end if we want our combobox name to be usable later
        obj = f"{object_type.rstrip('s').capitalize()}: {object_name}"

    window["-OBJECT-SELECT-"].Update(values=object_list)
    window["-OBJECT-SELECT-"].Update(value=obj)

    # Also update task object selector
    if "-OBJECT-SELECT-TASKS-" in window.AllKeysDict:
        window["-OBJECT-SELECT-TASKS-"].Update(values=object_list)
        window["-OBJECT-SELECT-TASKS-"].Update(value=obj)

    return get_object_from_combo(obj)


#### GENERIC OBJECT CONFIG LOGIC ####


def iter_over_config(
    window: sg.Window,
    full_config: dict,
    object_config: dict,
    config_inheritance: dict = None,
    object_type: str = None,
    unencrypted: bool = False,
    is_wizard: bool = False,
    root_key: str = "",
):
    """
    Iter over a dict while retaining the full key path to current object
    """
    base_object = object_config

    def _iter_over_config(object_config: dict, root_key=""):
        # We need to handle a special case here where env variables are dicts but shouldn't itered over here
        # but handled in in update_gui_values
        if isinstance(object_config, dict) and root_key not in (
            "env.env_variables",
            "env.encrypted_env_variables",
            "monitoring.additional_labels",
        ):
            for key in object_config.keys():
                if root_key:
                    _iter_over_config(object_config[key], root_key=f"{root_key}.{key}")
                else:
                    _iter_over_config(object_config[key], root_key=f"{key}")
        else:
            if config_inheritance:
                inherited = config_inheritance.g(root_key)
            else:
                inherited = False
            update_gui_values(
                window,
                full_config,
                root_key,
                base_object.g(root_key),
                inherited,
                object_type,
                unencrypted,
                is_wizard,
            )

    _iter_over_config(object_config, root_key)


def update_object_gui(
    window: sg.Window,
    full_config: dict,
    object_type: str = None,
    object_name: str = None,
    unencrypted: bool = False,
    is_wizard: bool = False,
) -> dict:
    """
    Reload current object configuration settings to GUI
    """
    global backup_paths_tree
    global exclude_files_tree
    global exclude_patterns_tree
    global pre_exec_commands_tree
    global post_exec_commands_tree
    global monitoring_additional_labels_tree
    global env_variables_tree
    global encrypted_env_variables_tree

    # Load fist available repo or group if none given
    if not object_name:
        try:
            object_type, object_name = get_object_from_combo(
                get_objects(full_config)[0]
            )
        except IndexError:
            object_type = None
            object_name = None

    # First we need to clear the whole GUI to reload new values
    for key in window.AllKeysDict:
        # We only clear config keys, which have '.' separator
        if "." in str(key) and "inherited" not in str(key):
            if isinstance(window[key], sg.Tree):
                window[key].Update(sg.TreeData())
            else:
                window[key]("")

    # We also need to clear tree objects
    backup_paths_tree = sg.TreeData()
    monitoring_additional_labels_tree = sg.TreeData()
    exclude_patterns_tree = sg.TreeData()
    exclude_files_tree = sg.TreeData()
    pre_exec_commands_tree = sg.TreeData()
    post_exec_commands_tree = sg.TreeData()
    env_variables_tree = sg.TreeData()
    encrypted_env_variables_tree = sg.TreeData()

    if object_type == "repos":
        object_config, config_inheritance = npbackup.configuration.get_repo_config(
            full_config, object_name, eval_variables=False
        )

        # Enable settings only valid for repos
        if "repo_uri" in window.AllKeysDict:
            window["repo_uri"].Update(visible=True)
        if not is_wizard:
            window["--SET-PERMISSIONS--"].Update(visible=True)
            window["current_permissions"].Update(visible=True)
            window["manager_password_set"].Update(visible=True)
            window["repo_group"].Update(visible=True)

    elif object_type == "groups" and not is_wizard:
        object_config = npbackup.configuration.get_group_config(
            full_config, object_name, eval_variables=False
        )
        config_inheritance = None

        # Disable settings only valid for repos
        window["repo_uri"].Update(visible=False)
        window["--SET-PERMISSIONS--"].Update(visible=False)
        window["current_permissions"].Update(visible=False)
        window["manager_password_set"].Update(visible=False)
        window["repo_group"].Update(visible=False)

    else:
        object_config = None
        config_inheritance = None
        logger.error(f"Bogus object {object_type}.{object_name}")
        return full_config

    # Now let's iter over the whole config object and update keys accordingly
    iter_over_config(
        window,
        full_config,
        object_config,
        config_inheritance,
        object_type,
        unencrypted,
        is_wizard,
        None,
    )

    # Special case when no source type is set
    if not is_wizard:
        if window["backup_opts.source_type"].Get() == "":
            window["backup_opts.source_type"].Update(
                value=combo_boxes["backup_opts.source_type"]["folder_list"]
            )
        source_type = get_key_from_value(
            combo_boxes["backup_opts.source_type"],
            window["backup_opts.source_type"].Get(),
        )
        update_source_layout(window, source_type)

    # Not using f-strings since python 3.8 doesn't accept backslashes in f-string expressions
    if BAD_KEYS_FOUND_IN_CONFIG:
        answer = sg.popup(
            _t("config_gui.key_error")
            + "\n"
            + _t("config_gui.delete_bad_keys")
            + ":\n\n{}".format("\n".join(BAD_KEYS_FOUND_IN_CONFIG)),
            keep_on_top=True,
            icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
            custom_text=(_t("generic.no"), _t("generic.yes")),
            title=_t("generic.warning").capitalize(),
        )
        if answer == _t("generic.yes"):
            for key in BAD_KEYS_FOUND_IN_CONFIG:
                full_key_path = f"{object_type}.{object_name}.{key}"
                logger.info(f"Deleting bogus key {full_key_path}")
                full_config.d(full_key_path)
    return full_config


def update_global_gui(
    window: sg.Window, full_config: dict, unencrypted: bool = False, is_wizard=False
):
    global_config = CommentedMap()

    # Only update global options gui with identified global keys
    for key, value in full_config.items():
        # We need to handle global_email.recipients here since we don't want to iter over it's subkeys
        if key == "global_email":
            recipients = {}
            try:
                for email_notification_type in value["recipients"].keys():
                    for recipient in value["recipients"][email_notification_type]:
                        if recipient not in recipients:
                            recipients[recipient] = []
                        recipients[recipient].append(email_notification_type)
                for recipient, notification_types in recipients.items():
                    add_email_recipient_row(window, recipient, notification_types)
            except KeyError:
                logger.debug("No recipients found in global_email settings, skipping")

        if is_wizard and key in ("global_options", "identity"):
            continue
        if (
            key in ("identity", "global_options")
            or key.startswith("global_")
            and (key[len("global_") :]) in npbackup.gui.common_gui.MONITORING_ENABLE
        ):
            global_config.s(key, full_config.g(key))
    iter_over_config(window, full_config, global_config, None, "group", unencrypted, "")


def update_monitoring_visibility(window: sg.Window, values):
    try:
        if "-GLOBAL-PROMETHEUS-SETTINGS-" in window.AllKeysDict:
            window["-GLOBAL-PROMETHEUS-SETTINGS-"].update(
                visible=values["global_prometheus.enabled"]
            )
    except KeyError as exc:
        logger.debug(f"No prometheus config: {exc}")
    try:
        if "-GLOBAL-HEALTHCHECKSIO-SETTINGS-" in window.AllKeysDict:
            window["-GLOBAL-HEALTHCHECKSIO-SETTINGS-"].update(
                visible=values["global_healthchecksio.enabled"]
            )
    except KeyError as exc:
        logger.debug(f"No healthchecksio config: {exc}")
    try:
        if "-GLOBAL-WEBHOOKS-SETTINGS-" in window.AllKeysDict:
            window["-GLOBAL-WEBHOOKS-SETTINGS-"].update(
                visible=values["global_webhooks.enabled"]
            )
    except KeyError as exc:
        logger.debug(f"No webhooks config: {exc}")
    try:
        if "-GLOBAL-ZABBIX-SETTINGS-" in window.AllKeysDict:
            window["-GLOBAL-ZABBIX-SETTINGS-"].update(
                visible=values["global_zabbix.enabled"]
            )
    except KeyError as exc:
        logger.debug(f"No zabbix config: {exc}")
    try:
        if "-GLOBAL-EMAIL-SETTINGS-" in window.AllKeysDict:
            window["-GLOBAL-EMAIL-SETTINGS-"].update(
                visible=values["global_email.enabled"]
            )
    except KeyError as exc:
        logger.debug(f"No email config: {exc}")


def update_zabbix_option_visibility(window: sg.Window, values):
    window["-ZABBIX-RAW-JSON-OPTIONS-"].update(
        visible=values["global_zabbix.method"] == "RawJSON"
    )
    window["-ZABBIX-TLS-OPTIONS-"].update(
        visible=values["global_zabbix.authentication"] == "tls"
    )
    window["-ZABBIX-PSK-OPTIONS-"].update(
        visible=values["global_zabbix.authentication"] == "psk"
    )


def update_gui_values(
    window: sg.Window,
    full_config: dict,
    key: str,
    value,
    inherited: bool,
    object_type: str,
    unencrypted: bool,
    is_wizard: bool = False,
):
    """
    Update gui values depending on their type
    This not called directly, but rather from update_object_gui which calls iter_over_config which calls this function
    """
    # Do not redefine those variables here since they're not modified, fixes flake8 F824

    # nonlocal backup_paths_tree
    # nonlocal exclude_files_tree
    # nonlocal exclude_patterns_tree
    # nonlocal pre_exec_commands_tree
    # nonlocal post_exec_commands_tree
    # nonlocal monitoring_additional_labels_tree
    # nonlocal env_variables_tree
    # nonlocal encrypted_env_variables_tree

    try:
        # Don't bother to update repo name
        # Also permissions / manager_password are in a separate gui

        if key in (
            "name",
            "is_protected",
            "current_manager_password",
            "uuid",
            "config_uuid",
        ):
            return

        # Note that keys with "new" must be processed after "current" keys
        # This will happen automatically since adding new values are at the end of the config
        if key in ("permissions", "new_permissions") and not is_wizard:
            # So we need to represent no permission as full in GUI
            if value is None:
                value = "full"
            window["current_permissions"].Update(combo_boxes["permissions"][value])
            return
        if key in ("manager_password", "new_manager_password"):
            if is_wizard:
                return
            if value:
                window["manager_password_set"].Update(_t("generic.yes"))
                window["--SET-PERMISSIONS--"].Update(button_color="green")
            else:
                window["manager_password_set"].Update(_t("generic.no"))
                window["--SET-PERMISSIONS--"].Update(button_color="red")
            return

        # Update GUI column rows from list
        # Must be handled before window.AllKeysDict since the window itself won't have a key for those

        if key in list(column_list_keys.keys()):
            column_key = column_list_keys[key]
            for entry in value:
                add_generic_row(window, column_key, entry, inherited[entry])
            return

        # We need to discard sukeys from recipients in order to avoid searching for subkeys in GUI
        if key.startswith("global_email.recipients."):
            return

        # Since FreeSimpleGUI does not allow to suppress the debugger anymore in v5.1.0, we need to handle KeyError
        if key not in window.AllKeysDict:
            if is_wizard:
                # logger.debug(f"Key {key} not found in wizard GUI, skipping")
                return
            # KeyError is caught below for log purposes
            raise KeyError

        # NPF-SEC-00009
        # Don't show sensitive info unless unencrypted requested
        if not unencrypted:
            # Use last part of key only
            if key in npbackup.configuration.ENCRYPTED_OPTIONS:
                try:
                    if isinstance(value, dict):
                        for k in value.keys():
                            value[k] = ENCRYPTED_DATA_PLACEHOLDER
                    elif value is not None and not str(value).startswith(
                        npbackup.configuration.ID_STRING
                    ):
                        value = ENCRYPTED_DATA_PLACEHOLDER
                except (KeyError, TypeError):
                    pass

        if key in ("repo_uri", "repo_group"):
            if object_type == "groups":
                if not is_wizard:
                    window[key].Disabled = True
                    window[key].Update(value=None)
            else:
                window[key].Disabled = False
                # Update the combo group selector
                if value is None:
                    window[key].Update(value="")
                else:
                    # Update possible values for repo group combobox after a new group is created
                    if key == "repo_group" and not is_wizard:
                        window[key].Update(
                            values=npbackup.configuration.get_group_list(full_config)
                        )
                    window[key].Update(value=value)
            return

        # Update tree objects
        if key == "backup_opts.paths":
            if value:
                for val in value:
                    icon, inherited_icon = get_icons_per_file(val)

                    if object_type != "groups" and inherited[val]:
                        backup_paths_tree.insert("", val, val, val, icon=inherited_icon)
                    else:
                        backup_paths_tree.insert("", val, val, val, icon=icon)
                window["backup_opts.paths"].update(values=backup_paths_tree)
            return
        elif key in (
            "backup_opts.pre_exec_commands",
            "backup_opts.post_exec_commands",
            "backup_opts.exclude_files",
            "backup_opts.exclude_patterns",
        ):
            if key == "backup_opts.pre_exec_commands":
                tree = pre_exec_commands_tree
            elif key == "backup_opts.post_exec_commands":
                tree = post_exec_commands_tree
            elif key == "backup_opts.exclude_files":
                tree = exclude_files_tree
            elif key == "backup_opts.exclude_patterns":
                tree = exclude_patterns_tree
            else:
                tree = None

            if value:
                if isinstance(value, list):
                    for val in value:
                        if val is None:
                            continue
                        if object_type != "groups" and inherited[val]:
                            icon = INHERITED_TREE_ICON
                        else:
                            icon = TREE_ICON
                        if tree:
                            tree.insert("", val, val, val, icon=icon)
                    window[key].Update(values=tree)
                else:
                    logger.error(rf"Bogus configuration value for {key}: {value}")
            return

        if key in (
            "env.env_variables",
            "env.encrypted_env_variables",
            "monitoring.additional_labels",
        ):
            if key == "env.env_variables":
                tree = env_variables_tree
            if key == "env.encrypted_env_variables":
                tree = encrypted_env_variables_tree
            if key == "monitoring.additional_labels":
                tree = monitoring_additional_labels_tree

            if value:
                if isinstance(value, dict):
                    for skey, val in value.items():
                        if object_type != "groups" and inherited and inherited[skey]:
                            icon = INHERITED_TREE_ICON
                        else:
                            icon = TREE_ICON
                        tree.insert("", skey, skey, values=[val], icon=icon)
                    window[key].Update(values=tree)
                else:
                    logger.error(f"Bogus configuration value for {key}: {value}")
            return

        # Update units into separate value and unit combobox
        if key in (
            "backup_opts.minimum_backup_size_error",
            "backup_opts.exclude_files_larger_than",
            "repo_opts.upload_speed",
            "repo_opts.download_speed",
            "repo_opts.prune_max_unused",
            "repo_opts.prune_max_repack_size",
        ):
            # We don't need a better split here since the value string comes from BytesConverter
            # which always provides "0 MiB" or "5 KB" etc.
            # except repo_opts.prune_max_unused which also allows percent, eg "5%" or "5 %"
            if value is not None:
                unit = None
                try:

                    matches = re.search(r"(\d+(?:\.\d+)?)\s*([\w%]*)", value)
                    if matches:
                        value = str(matches.group(1))
                        unit = str(matches.group(2))
                except (TypeError, IndexError, AttributeError):
                    logger.error(
                        f"Error decoding value {value} of key {key}. Setting default value"
                    )
                    value = "0"
                    unit = "MiB"
                window[key].Update(value)
                window[f"{key}_unit"].Update(unit)

        if key in combo_boxes.keys() and value:
            window[key].Update(value=combo_boxes[key][value])
        else:
            window[key].Update(value=value)

        # Enable inheritance icon when needed
        inheritance_key = f"inherited.{key}"
        if inheritance_key in window.AllKeysDict:
            if inherited:
                window[inheritance_key].update(INHERITED_ICON)
            else:
                window[inheritance_key].update(NON_INHERITED_ICON)

    except KeyError as exc:
        if not is_wizard:
            logger.error(f"{_t('config_gui.key_error')}: {key}")
            logger.debug("Trace:", exc_info=True)
            BAD_KEYS_FOUND_IN_CONFIG.add(key)
    except TypeError as exc:
        logger.error(
            f"Error: Trying to update GUI with key {key} produced error: {exc}"
        )
        logger.debug("Trace:", exc_info=True)


def validate_email_addresses(window: sg.Window) -> Optional[Union[List[str], bool]]:
    """
    Chefs email against RFC 822 and returns list of good emails
    or false if bad emails exist, or none if no emails given
    """

    bad_emails = []
    good_emails = []
    for value in window.AllKeysDict:
        if isinstance(value, tuple) and value[0] == "-EMAIL-RECIPIENT-":
            index = value[1]
            recipient_email = window[("-EMAIL-RECIPIENT-ADDR-", index)].get()
            if recipient_email:
                if is_mail_address(recipient_email):
                    good_emails.append(recipient_email)
                else:
                    bad_emails.append(recipient_email)
    if bad_emails:
        popup_error(
            _t("config_gui.invalid_email_address") + f": {', '.join(bad_emails)}"
        )
        return False
    if good_emails:
        return good_emails
    return None


def update_config_dict(
    window: sg.Window,
    full_config: dict,
    object_type: str,
    object_name: str,
    values: dict,
    is_wizard: bool = False,
) -> dict:
    """
    Update full_config with keys from GUI
    keys should always have form section.name or section.subsection.name

    # WIP todo: only update visible items so we don't mess with settings that are not relevant / hidden
    """
    if object_type == "repos":
        object_group = full_config.g(f"{object_type}.{object_name}.repo_group")
        if not object_group:
            logger.error(
                f"Current repo {object_name} has no group. Cannot upgrade config"
            )
            return full_config
    else:
        object_group = None

    # With multiple column rows, we get values like ('BACKUP-TAG', '0'), ('BACKUP-TAG', '1') etc.
    # so we need to transform them back into lists

    for key, column_key in column_list_keys.items():
        values[key] = []
        for value in window.AllKeysDict:
            if isinstance(value, tuple) and value[0] == f"-{column_key}-":
                tag = window[value].get()
                if tag:  # Don't add empty tags
                    values[key].append(tag)

    # We also need some special treatment for email recipients since they have a specific format
    values["global_email.recipients"] = {
        "on_backup_success": [],
        "on_backup_failure": [],
        "on_operations_success": [],
        "on_operations_failure": [],
    }
    for value in window.AllKeysDict:
        if isinstance(value, tuple) and value[0] == "-EMAIL-RECIPIENT-":
            index = value[1]
            recipient_email = window[("-EMAIL-RECIPIENT-ADDR-", index)].get()
            if recipient_email:  # Don't add empty email addresses
                if values[("-EMAIL-ON-BACKUP-SUCCESS-", index)]:
                    values["global_email.recipients"]["on_backup_success"].append(
                        recipient_email
                    )
                if values[("-EMAIL-ON-BACKUP-FAILURE-", index)]:
                    values["global_email.recipients"]["on_backup_failure"].append(
                        recipient_email
                    )
                if values[("-EMAIL-ON-OPERATIONS-SUCCESS-", index)]:
                    values["global_email.recipients"]["on_operations_success"].append(
                        recipient_email
                    )
                if values[("-EMAIL-ON-OPERATIONS-FAILURE-", index)]:
                    values["global_email.recipients"]["on_operations_failure"].append(
                        recipient_email
                    )

    # We need to patch values since sg.Tree() only returns selected data from TreeData()
    # Hence we'll fill values with a list or a dict depending on our TreeData data structure
    # @simpleGUI: there should be a get_all_values() method or something
    list_tree_data_keys = [
        "backup_opts.paths",
        "backup_opts.pre_exec_commands",
        "backup_opts.post_exec_commands",
        "backup_opts.exclude_files",
        "backup_opts.exclude_patterns",
    ]

    for tree_data_key in list_tree_data_keys:
        if tree_data_key not in window.AllKeysDict and is_wizard:
            logger.debug(f"Wizard does not use tree data key {tree_data_key}")
            continue
        values[tree_data_key] = []
        # pylint: disable=E1101 (no-member)
        for node in window[tree_data_key].TreeData.tree_dict.values():
            if node.values:
                values[tree_data_key].append(node.values)

    dict_tree_data_keys = [
        "env.env_variables",
        "env.encrypted_env_variables",
        "monitoring.additional_labels",
    ]
    for tree_data_key in dict_tree_data_keys:
        if tree_data_key not in window.AllKeysDict and is_wizard:
            logger.debug(f"Wizard does not use tree data key {tree_data_key}")
            continue
        values[tree_data_key] = CommentedMap()
        # pylint: disable=E1101 (no-member)
        for key, node in window[tree_data_key].TreeData.tree_dict.items():
            if key and node.values:
                values[tree_data_key][key] = node.values[0]

    # Special treatment for env.encrypted_env_variables since they might contain an ENCRYPTED_DATA_PLACEHOLDER
    # We need to update the placeholder to the actual value if exists
    if "env.encrypted_env_variables" not in window.AllKeysDict and is_wizard:
        logger.debug("Wizard does not use env.encrypted_env_variables")
    else:
        for k, v in values["env.encrypted_env_variables"].items():
            if v == ENCRYPTED_DATA_PLACEHOLDER:
                values["env.encrypted_env_variables"][k] = full_config.g(
                    f"{object_type}.{object_name}.env.encrypted_env_variables.{k}"
                )

    # Now that we have dealt with data preparation, let's loop over the key, value sets
    for key, value in values.items():
        # Don't update placeholders ;)
        if value == ENCRYPTED_DATA_PLACEHOLDER:
            continue
        if not isinstance(key, str) or (
            isinstance(key, str)
            and ("." not in key and key not in ("repo_uri", "repo_group"))
        ):
            # Don't bother with keys that don't contain with "." since they're not in the YAML config file
            # but are most probably for GUI events
            # Still, we need to handle repo_uri and repo_group which do not have dot notations since they're root keys
            continue

        # Handle combo boxes first to transform translation into key
        if key in combo_boxes.keys():
            value = get_key_from_value(combo_boxes[key], value)
        # check whether we need to split into list
        elif not isinstance(value, bool) and not isinstance(value, list):
            # Try to convert ints and floats before committing
            if "." in value:
                try:
                    value = float(value)
                except ValueError:
                    pass
            else:
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    pass

        # Glue value and units back together for config file
        if key in (
            "backup_opts.minimum_backup_size_error",
            "backup_opts.exclude_files_larger_than",
            "repo_opts.upload_speed",
            "repo_opts.download_speed",
            "repo_opts.prune_max_unused",
            "repo_opts.prune_max_repack_size",
        ):
            if value:
                value = f"{value} {values[f'{key}_unit']}"

        # Don't update unit keys
        if key in (
            "backup_opts.minimum_backup_size_error_unit",
            "backup_opts.exclude_files_larger_than_unit",
            "repo_opts.upload_speed_unit",
            "repo_opts.download_speed_unit",
            "repo_opts.prune_max_unused_unit",
            "repo_opts.prune_max_repack_size_unit",
        ):
            continue
        # Don't bother with inheritance on global options and host identity
        if (
            key.startswith("global_options")
            or key.startswith("identity")
            or key.startswith("global_prometheus")
            or key.startswith("global_email")
            or key.startswith("global_healthchecksio")
            or key.startswith("global_zabbix")
            or key.startswith("global_webhooks")
        ):
            active_object_key = f"{key}"
            current_value = full_config.g(active_object_key)
        else:
            active_object_key = f"{object_type}.{object_name}.{key}"
            current_value = full_config.g(active_object_key)

            # Special case for nested retention_policy dict which may not exist, we need to create it
            if key.startswith("repo_opts.retention_policy"):
                if not full_config.g(
                    f"{object_type}.{object_name}.repo_opts.retention_policy"
                ):
                    full_config.s(
                        f"{object_type}.{object_name}.repo_opts.retention_policy",
                        CommentedMap(),
                    )

            if object_group:
                inheritance_key = f"groups.{object_group}.{key}"
                # If object is a list, check which values are inherited from group and remove them
                if isinstance(value, list):
                    inheritance_list = full_config.g(inheritance_key)
                    if inheritance_list:
                        for entry in inheritance_list:
                            if entry in value:
                                value.remove(entry)

                # check if value is inherited from group, and if so, delete it from repo config
                # Also add a foolproof test since people could add repo_group to a group config
                # We're not allowing recursive groups !
                if full_config.g(inheritance_key) == value and key != "repo_group":
                    full_config.d(active_object_key)
                    continue
                # we also need to compare inherited values with current values for BytesConverter values
                if key in (
                    "backup_opts.minimum_backup_size_error",
                    "backup_opts.exclude_files_larger_than",
                    "repo_opts.upload_speed",
                    "repo_opts.download_speed",
                    "repo_opts.prune_max_unused",
                    "repo_opts.prune_max_repack_size",
                ):
                    try:
                        if (
                            full_config.g(inheritance_key) not in (None, "")
                            and value not in (None, "")
                            and (
                                BytesConverter(full_config.g(inheritance_key)).bytes
                                == BytesConverter(value).bytes
                            )
                        ):
                            continue
                    except ValueError as exc:
                        logger.debug(f"BytesConverter could not convert value: {exc}")

        # Don't bother to update empty strings, empty lists and None
        # unless we have False, or 0, which or course need to be updated
        if not current_value and value in (None, "", []):
            continue
        # Don't bother to update values which haven't changed
        if current_value == value:
            continue

        try:
            full_config.s(active_object_key, value)
        except KeyError:
            parent_key = ".".join(active_object_key.split(".")[:-1])
            full_config.s(parent_key, CommentedMap())
            full_config.s(active_object_key, value)
    return full_config


def update_source_layout(window: sg.Window, source_type: str):
    if source_type == "stdin_from_command":
        window["-BACKUP-PATHS-"].update(visible=False)
        window["-BACKUP-STDIN-"].update(visible=True)
    elif source_type == "folder_list":
        window["-BACKUP-PATHS-"].update(visible=True)
        window["-BACKUP-STDIN-"].update(visible=False)
    elif source_type in ("files_from", "files_from_verbatim", "files_from_raw"):
        window["-BACKUP-PATHS-"].update(visible=True)
        window["-BACKUP-STDIN-"].update(visible=False)


## EVENT HANDLING LOGIC FOR MOST EVENTS ##


#### ADD ELEMENTS TO LIST
def add_email_recipient_row(
    window: sg.Window, recipient: str = None, notification_types: List[str] = None
):
    # No need for global variable for dicts
    # global COLUMN_LIST_COUNTERS

    COLUMN_LIST_COUNTERS["EMAIL-RECIPIENTS"] += 1
    window.extend_layout(
        window["-EMAIL-RECIPIENT-COLUMN-"],
        [
            npbackup.gui.common_gui.email_recipient_row(
                COLUMN_LIST_COUNTERS["EMAIL-RECIPIENTS"]
            )
        ],
    )
    window.refresh()
    if recipient:
        window[
            ("-EMAIL-RECIPIENT-ADDR-", COLUMN_LIST_COUNTERS["EMAIL-RECIPIENTS"])
        ].update(value=recipient)
    if notification_types:
        window[
            ("-EMAIL-ON-BACKUP-SUCCESS-", COLUMN_LIST_COUNTERS["EMAIL-RECIPIENTS"])
        ].update(value="on_backup_success" in notification_types)
        window[
            ("-EMAIL-ON-BACKUP-FAILURE-", COLUMN_LIST_COUNTERS["EMAIL-RECIPIENTS"])
        ].update(value="on_backup_failure" in notification_types)
        window[
            ("-EMAIL-ON-OPERATIONS-SUCCESS-", COLUMN_LIST_COUNTERS["EMAIL-RECIPIENTS"])
        ].update(value="on_operations_success" in notification_types)
        window[
            ("-EMAIL-ON-OPERATIONS-FAILURE-", COLUMN_LIST_COUNTERS["EMAIL-RECIPIENTS"])
        ].update(value="on_operations_failure" in notification_types)
    window["-EMAIL-RECIPIENT-COLUMN-"].contents_changed()
    return


def add_generic_row(
    window: sg.Window, column_key: str, value: str = None, inherited: bool = False
):
    # No need for global variable for dicts
    # global COLUMN_LIST_COUNTERS

    # Check if value already exists as column
    for key in window.AllKeysDict:
        if isinstance(key, tuple) and key[0] == f"-{column_key}-":
            if window[key].get() == value:
                # logger.debug(f"Value {value} already exists in column {column_key}, skipping")
                return

    # Check if actual column exists in GUI (wizard exclude sub window doesn't have those columns)
    if f"-{column_key}-COLUMN-" in window.AllKeysDict:
        COLUMN_LIST_COUNTERS[column_key] += 1

        window.extend_layout(
            window[f"-{column_key}-COLUMN-"],
            [
                npbackup.gui.common_gui.generic_row(
                    name=column_key,
                    index=COLUMN_LIST_COUNTERS[column_key],
                    size=(20, 1),
                    optional_prefix_object=sg.Text(_t("generic.tag").capitalize()),
                    inherited=inherited,
                )
            ],
        )
        window.refresh()
        if value:
            window[(f"-{column_key}-", COLUMN_LIST_COUNTERS[column_key])].update(
                value=value
            )
        window[f"-{column_key}-COLUMN-"].contents_changed()


def handle_gui_events(
    full_config: dict,
    window: sg.Window,
    event,
    values: dict = None,
    object_type: str = None,
    object_name: str = None,
    unencrypted: bool = False,
    is_wizard: bool = False,
):
    """
    Handles various GUI events for both config and wizard GUIs
    """
    # No need for global variable for dicts
    # global COLUMN_LIST_COUNTERS

    # Retention policy advanced settings show/hide
    if event == "-RETENTION-POLICY-ADVANCED-":
        window["-RETENTION-POLICY-ADVANCED-COLUMN-"].update(
            visible=not window["-RETENTION-POLICY-ADVANCED-COLUMN-"].visible
        )

    if event == "-RETENTION-POLICIES-":
        retention_policies = get_retention_policies_presets(full_config)
        if values["-RETENTION-POLICIES-"]:
            new_retention_policy = retention_policies.g(values["-RETENTION-POLICIES-"])
            full_config.s(
                f"{object_type}.{object_name}.repo_opts.retention_policy",
                new_retention_policy,
            )
            logger.debug(f"Selected retention policy: {new_retention_policy}")
            update_object_gui(
                window=window,
                full_config=full_config,
                object_type=object_type,
                object_name=object_name,
                unencrypted=False,  # WIP
                is_wizard=is_wizard,
            )

    # Add / remove elements from column
    # This part adds / removes new input elements into multirow columns
    # for lists like backup tags, backup paths, exclude patterns etc.

    # Extract column key from event name like -ADD-BACKUP-TAG- or REMOVE-BACKUP-TAG-ROW-
    if not isinstance(event, tuple) and event.startswith("-ADD-"):
        column_key = event.split("-ADD-")[1].rstrip("-")
    elif isinstance(event, tuple) and event[0].startswith("-REMOVE-ROW-"):
        column_key = event[0].split("-REMOVE-ROW-")[1].rstrip("-")
    else:
        column_key = None

    if column_key and column_key not in COLUMN_LIST_COUNTERS:
        logger.debug(f"Column key {column_key} not found in COLUMN_LIST_COUNTERS")
    else:
        if f"-ADD-{column_key}-" in event:
            add_generic_row(window, column_key)
            return
        if isinstance(event, tuple) and event[0] == f"-REMOVE-ROW-{column_key}-":
            if COLUMN_LIST_COUNTERS[column_key] > 0:
                if window[(f"inherited-{column_key}-", event[1])].visible:
                    popup_error(_t("config_gui.cannot_remove_group_inherited_settings"))
                    return
                # Empty the value before making it's surrounding column invisible
                window[(f"-{column_key}-", event[1])].update("")
                window[(f"-GENERIC-{column_key}-COLUMN-", event[1])].update(
                    visible=False
                )
            window.refresh()
            window[f"-{column_key}-COLUMN-"].contents_changed()
            return

    # Email recipient column
    if event == "-ADD-EMAIL-RECIPIENT-":
        add_email_recipient_row(window)
        return
    if isinstance(event, tuple) and event[0] == "-REMOVE-EMAIL-RECIPIENT-":
        if COLUMN_LIST_COUNTERS["EMAIL-RECIPIENTS"] > 0:
            window[("-EMAIL-RECIPIENT-ADDR-", event[1])].update("")
            window[("-EMAIL-RECIPIENT-", event[1])].update(visible=False)
        window.refresh()
        window["-EMAIL-RECIPIENT-COLUMN-"].contents_changed()
        return

    # Backup source related events
    if event in (
        "-ADD-SOURCE-MENU-",
        "--ADD-EXCLUDE-FILE--",
        "--ADD-EXCLUDE-FILE-MANUALLY--",
    ):
        node = None
        key = None
        tree = None
        icon = None
        if event == "--ADD-EXCLUDE-FILE--":
            key = "backup_opts.exclude_files"
            tree = exclude_files_tree
            node = values[event]
            icon, _ = get_icons_per_file(node)
        elif event == "--ADD-EXCLUDE-FILE-MANUALLY--":
            key = "backup_opts.exclude_files"
            tree = exclude_files_tree
            node = sg.popup_get_text(_t("generic.add_manually"))
            icon, _ = get_icons_per_file(node)
        elif event == "-ADD-SOURCE-MENU-":
            key = "backup_opts.paths"
            tree = backup_paths_tree
            if values["-ADD-SOURCE-MENU-"] == _t("generic.add_files"):
                sg.FileBrowse(_t("generic.add_files"), target="backup_opts.paths")
                node = sg.popup_get_file("Add files clicked", no_window=True)
                icon, _ = get_icons_per_file(node)
            elif values["-ADD-SOURCE-MENU-"] == _t("generic.add_folder"):
                node = sg.popup_get_folder("Add folder clicked", no_window=True)
                icon, _ = get_icons_per_file(node)
            elif values["-ADD-SOURCE-MENU-"] == _t("generic.add_system"):
                sg.popup("Add Windows system clicked", keep_on_top=True)
                # WIP we need to make backup_opts.source = kvm
                # WIP we need to check that only one source type is selected at once
                icon = SYSTEM_ICON
            elif values["-ADD-SOURCE-MENU-"] == _t("generic.add_hyper_v"):
                sg.popup("Add Hyper-V virtual machines clicked", keep_on_top=True)
                icon = HYPER_V_ICON
            elif values["-ADD-SOURCE-MENU-"] == _t("generic.add_kvm"):
                sg.popup("Add KVM virtual machines clicked", keep_on_top=True)
                icon = KVM_ICON
            elif values["-ADD-SOURCE-MENU-"] == _t("generic.add_manually"):
                node = sg.popup_get_text("Add path manually", no_titlebar=True)
                icon, _ = get_icons_per_file(node)
        if node and key and tree:
            # Check if node is ADD-PATH-FILES which can contain multiple elements separated by semicolon
            if ";" in node:
                for path in node.split(";"):
                    if tree.tree_dict.get(path):
                        tree.delete(path)
                    tree.insert("", path, path, path, icon=icon)
            else:
                if tree.tree_dict.get(node):
                    tree.delete(node)
                tree.insert("", node, node, node, icon=icon)
            window[key].update(values=tree)
        return

    if event == "-REMOVE-SOURCE-":
        selected_items = values["backup_opts.paths"]
        tree = backup_paths_tree
        for item in selected_items:
            tree.delete(item)
        window["backup_opts.paths"].update(values=tree)
        return

    # Make monitoring options visible / invisible
    if event in (
        "global_prometheus.enabled",
        "global_email.enabled",
        "global_healthchecksio.enabled",
        "global_zabbix.enabled",
        "global_webhooks.enabled",
    ):
        update_monitoring_visibility(window, values)
        return

    # Only show zabbix needed options
    if event in ("global_zabbix.method", "global_zabbix.authentication"):
        update_zabbix_option_visibility(window, values)
        return

    if event in (
        "--ADD-EXCLUDE-PATTERN--",
        "--ADD-PRE-EXEC-COMMAND--",
        "--ADD-POST-EXEC-COMMAND--",
        "--ADD-MONITORING-LABEL--",
        "--ADD-ENV-VARIABLE--",
        "--ADD-ENCRYPTED-ENV-VARIABLE--",
        "--ADD-S3-IDENTITY--",
        "--ADD-AZURE-IDENTITY--",
        "--ADD-B2-IDENTITY--",
        "--ADD-GCS-IDENTITY--",
        "--REMOVE-PATHS--",
        "--REMOVE-EXCLUDE-PATTERN--",
        "--REMOVE-EXCLUDE-FILE--",
        "--REMOVE-PRE-EXEC-COMMAND--",
        "--REMOVE-POST-EXEC-COMMAND--",
        "--REMOVE-MONITORING-LABEL--",
        "--REMOVE-ENV-VARIABLE--",
        "--REMOVE-ENCRYPTED-ENV-VARIABLE--",
    ):
        popup_text = None
        option_key = None
        if "PATHS" in event:
            option_key = "backup_opts.paths"
            tree = backup_paths_tree
        elif "EXCLUDE-PATTERN" in event:
            popup_text = _t("config_gui.enter_pattern")
            tree = exclude_patterns_tree
            option_key = "backup_opts.exclude_patterns"
        elif "EXCLUDE-FILE" in event:
            popup_text = None
            tree = exclude_files_tree
            option_key = "backup_opts.exclude_files"
        elif "PRE-EXEC-COMMAND" in event:
            popup_text = _t("config_gui.enter_command")
            tree = pre_exec_commands_tree
            option_key = "backup_opts.pre_exec_commands"
        elif "POST-EXEC-COMMAND" in event:
            popup_text = _t("config_gui.enter_command")
            tree = post_exec_commands_tree
            option_key = "backup_opts.post_exec_commands"
        elif "MONITORING-LABEL" in event:
            popup_text = _t("config_gui.enter_label")
            tree = monitoring_additional_labels_tree
            option_key = "monitoring.additional_labels"
        elif (
            "ENCRYPTED-ENV-VARIABLE" in event
            or "S3-IDENTITY--" in event
            or "AZURE-IDENTITY--" in event
            or "B2-IDENTITY--" in event
            or "GCS-IDENTITY--" in event
        ):
            tree = encrypted_env_variables_tree
            option_key = "env.encrypted_env_variables"
        elif "ENV-VARIABLE" in event:
            tree = env_variables_tree
            option_key = "env.env_variables"

        if event.startswith("--ADD-"):
            icon = TREE_ICON
            if "ENV-VARIABLE" in event or "ENCRYPTED-ENV-VARIABLE" in event:
                var_name = sg.popup_get_text(_t("config_gui.enter_var_name"))
                var_value = sg.popup_get_text(_t("config_gui.enter_var_value"))
                if var_name and var_value:
                    if tree.tree_dict.get(var_name):
                        tree.delete(var_name)
                    tree.insert("", var_name, var_name, [var_value], icon=icon)
                    # WIP add return here ?
            elif "MONITORING-LABEL" in event:
                var_name = sg.popup_get_text(_t("config_gui.enter_label_name"))
                var_value = sg.popup_get_text(_t("config_gui.enter_label_value"))
                if var_name and var_value:
                    if tree.tree_dict.get(var_name):
                        tree.delete(var_name)
                    tree.insert("", var_name, var_name, [var_value], icon=icon)
            elif (
                "S3-IDENTITY--" in event
                or "AZURE-IDENTITY--" in event
                or "B2-IDENTITY--" in event
                or "GCS-IDENTITY--" in event
            ):
                if "S3-IDENTITY--" in event:
                    var_names = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
                elif "AZURE-IDENTITY--" in event:
                    var_names = [
                        "AZURE_ACCOUNT_KEY",
                        "AZURE_ACCOUNT_SAS",
                        "AZURE_ACCOUNT_NAME",
                    ]
                elif "B2-IDENTITY--" in event:
                    var_names = ["B2_ACCOUNT_ID", "B2_ACCOUNT_KEY"]
                elif "GCS-IDENTITY--" in event:
                    var_names = [
                        "GOOGLE_PROJECT_ID",
                        "GOOGLE_APPLICATION_CREDENTIALS",
                    ]
                else:
                    popup_error("Bad identity given")
                    return
                for var_name in var_names:
                    var_value = sg.popup_get_text(var_name)
                    if var_value:
                        if tree.tree_dict.get(var_name):
                            tree.delete(var_name)
                        tree.insert("", var_name, var_name, [var_value], icon=icon)
                    else:
                        popup_error(_t("config_gui.value_cannot_be_empty"))
                        return
            else:
                node = sg.popup_get_text(popup_text)
                if node:
                    if tree.tree_dict.get(node):
                        tree.delete(node)
                    tree.insert("", node, node, node, icon=icon)
        if event.startswith("--REMOVE-"):
            for key in values[option_key]:
                if object_type != "groups" and tree.tree_dict[key].icon in (
                    INHERITED_TREE_ICON,
                    INHERITED_FILE_ICON,
                    INHERITED_FOLDER_ICON,
                ):
                    popup_error(
                        _t("config_gui.cannot_remove_group_inherited_settings"),
                    )
                    continue
                tree.delete(key)
        window[option_key].Update(values=tree)
        return

    if event == "-TEST-EMAIL-":
        # Mock repo_config
        mock_repo_config = CommentedMap()
        mock_repo_config.s("name", "Test repository")
        mock_metrics = {
            "npbackup_exec_state": 0,
            "npbackup_exec_time": 0,
            "operation": "email_test",
        }

        # Extract emails from current dir but do not inject them into full config since we're only testing
        good_emails = validate_email_addresses(window)
        if not good_emails:
            sg.popup(_t("config_gui.no_valid_email_addresses"), keep_on_top=True)
            return

        mock_full_config = deepcopy(full_config)
        mock_full_config.d("global_email.recipients.on_backup_success")
        mock_full_config.d("global_email.recipients.on_backup_failure")
        mock_full_config.d("global_email.recipients.on_operations_failure")
        mock_full_config.s("global_email.recipients.on_operations_success", good_emails)
        result = EmailMonitor(
            mock_repo_config,
            npbackup.configuration.get_monitoring_config(
                mock_repo_config, mock_full_config
            ),
        ).send_metrics(
            mock_metrics,
            operation="email_test",
            dry_run=False,
        )
        if result:
            sg.popup(_t("config_gui.test_email_success"), keep_on_top=True)
        else:
            sg.popup(_t("config_gui.test_email_failure"), keep_on_top=True)
        return

    if event == "backup_opts.source_type":
        source_type = get_key_from_value(
            combo_boxes["backup_opts.source_type"],
            values["backup_opts.source_type"],
        )
        update_source_layout(window, source_type)
        return


#### EVENT HANDLING FOR TASK CREATION ####


def create_scheduled_task(
    values: dict, full_config: dict, config_file: str
) -> Tuple[bool, dict]:
    """
    Read Task scheduler GUI entries and create a scheduled task accordingly
    """
    task_type = values["-TASK-TYPE-"]
    object_type, object_name = get_object_from_combo(values["-OBJECT-SELECT-TASKS-"])
    interval = values["-BACKUP-INTERVAL-"]
    interval_unit = get_key_from_value(
        combo_boxes["backup_interval_unit"], values["-BACKUP-INTERVAL-UNIT-"]
    )

    days = []
    for day in [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]:
        if values[f"-DAY-{day}-"]:
            days.append(day)

    # We also need to update the scheduling specific config values here
    if values["repo_opts.minimum_backup_age"]:
        try:
            minimum_backup_age = int(values["repo_opts.minimum_backup_age"])
            full_config.s(
                f"{object_type}.{object_name}.repo_opts.minimum_backup_age",
                minimum_backup_age,
            )
        except ValueError:
            logger.error("Bogus minimum backup age value, not updating config")
            return False, full_config
    else:
        minimum_backup_age = 0
    if values["repo_opts.random_delay_before_backup"]:
        try:
            random_delay_before_backup = int(
                values["repo_opts.random_delay_before_backup"]
            )
            full_config.s(
                f"{object_type}.{object_name}.repo_opts.random_delay_before_backup",
                random_delay_before_backup,
            )
        except ValueError:
            logger.error("Bogus random delay before backup value, not updating config")
            return False, full_config

    try:
        date_string = f'{values["-FIRST-BACKUP-DATE-"]} {str(values["-FIRST-BACKUP-HOUR-"]).zfill(2)}:{str(values["-FIRST-BACKUP-MINUTE-"]).zfill(2)}'
        start_date_time = datetime.strptime(date_string, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        logger.error(f"Invalid date format, not creating scheduled task: {exc}")
        return False, full_config

    run_as = values["-SCHEDULE-RUN-AS-"]
    if run_as in ["SYSTEM", "root"]:
        user_credentials = False
    else:
        user_credentials = get_user_and_password_for_run_as()

    result = npbackup.task.create_scheduled_task(
        config_file,
        task_type=task_type,
        object_type=object_type,
        object_name=object_name,
        user_credentials=user_credentials,
        start_date_time=start_date_time,
        interval=interval,
        interval_unit=interval_unit,
        days=days,
        force=minimum_backup_age == 0,
    )

    return result, full_config


@threaded
def read_existing_scheduled_tasks_threaded(
    config_file, full_config, operation: str = None
):
    """
    Wrapper to read scheduled tasks in a thread
    """
    return npbackup.task.read_existing_scheduled_tasks(
        config_file, full_config, operation
    )


def update_task_list(config_file: str, full_config: dict, window: sg.Window) -> dict:
    """
    Reads current scheduled tasks in a thread and updates scheduled task list
    """
    logger.debug("Reading existing scheduled tasks")
    thread = read_existing_scheduled_tasks_threaded(config_file, full_config)
    tasks = WaitWindow(
        thread, message=_t("config_gui.reading_tasks")
    ).wait_for_thread_result()
    # We need to define a special list for sg.Table to use
    task_list = []
    if tasks:
        for task in tasks:
            task_line = [
                task["task_type"],
                task["object_type"],
                task["object_name"],
                task["interval"],
                task["interval_unit"],
                task["start_date"],
                task["days_of_week"],
            ]
            task_list.append(task_line)
        window["-EXISTING-TASKS-"].update(values=task_list)
    else:
        tasks = []
    return tasks


def update_task_ui_for_object(
    full_config: dict, window: sg.Window, task: list, is_wizard: bool = False
):
    if not is_wizard:
        window["-TASK-TYPE-"].update(value=task["task_type"])
    window["-BACKUP-INTERVAL-"].update(value=task["interval"])
    window["-BACKUP-INTERVAL-UNIT-"].update(
        value=combo_boxes["backup_interval_unit"][task["interval_unit"]]
    )

    object_type = task["object_type"]
    object_name = task["object_name"]
    if not is_wizard:
        window["-OBJECT-SELECT-TASKS-"].update(
            value=create_object_name_for_combo(object_type, object_name)
        )

    window["-FIRST-BACKUP-DATE-"].update(value=task["start_date"].strftime("%Y-%m-%d"))
    window["-FIRST-BACKUP-HOUR-"].update(value=task["start_date"].strftime("%H"))
    window["-FIRST-BACKUP-MINUTE-"].update(value=task["start_date"].strftime("%M"))

    try:
        minimum_backup_age = full_config.g(
            f"{object_type}.{object_name}.repo_opts.minimum_backup_age"
        )
    except KeyError:
        minimum_backup_age = 0
    try:
        random_delay_before_backup = full_config.g(
            f"{object_type}.{object_name}.repo_opts.random_delay_before_backup"
        )
    except KeyError:
        random_delay_before_backup = 0
    window["repo_opts.minimum_backup_age"].update(value=minimum_backup_age)
    window["repo_opts.random_delay_before_backup"].update(
        value=random_delay_before_backup
    )

    for day in [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]:
        if day in task["days_of_week"]:
            window[f"-DAY-{day.lower()}-"].update(value=True)
        else:
            window[f"-DAY-{day.lower()}-"].update(value=False)


#### RETENTION POLICIES PRESETS CODE ####
def get_retention_policies_presets(full_config: dict) -> dict:
    try:
        retention_policies_presets = list(full_config.g("presets.retention_policies"))
    except Exception:
        # We might need to fallback to integrated presets in constants
        retention_policies_presets = npbackup.configuration.get_default_config().g(
            "presets.retention_policy"
        )

    # Translate retention policy names for display in combo box
    # Since we don't save the combo box content, we don't need the original naes
    translated_retention_policies_presets = CommentedMap()
    for policy_name, policy_values in retention_policies_presets.items():
        translated_retention_policies_presets[_t(f"config_gui.{policy_name}")] = (
            policy_values
        )
    return translated_retention_policies_presets


def retention_policy_preset_name(
    full_config: dict,
    object_type: str,
    object_name: str,
    retention_policies_presets: dict,
) -> Optional[str]:
    """
    Matches current retention policy against existing presets and returns the prest name if found
    """
    # Get current retention policy
    if object_type == "repos":
        object_config, _ = npbackup.configuration.get_repo_config(
            full_config, object_name
        )
    else:
        object_config = npbackup.configuration.get_group_config(
            full_config, object_name
        )

    current_retention_policy = object_config.g(f"repo_opts.retention_policy")
    if retention_policies_presets and current_retention_policy:
        # Let's compare only preset keys to determine if we're using a preset
        for policy_name, policy_values in (
            npbackup.configuration.get_default_config()
            .g("presets.retention_policy")
            .items()
        ):
            # Extract the key names we want to compare from presets
            policy_matches = True
            for key in policy_values.keys():
                if not current_retention_policy[key] == policy_values[key]:
                    policy_matches = False
                    break
            if policy_matches:
                return _t(f"config_gui.{policy_name}")
    return None
