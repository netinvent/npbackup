#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.config"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025061301"


from typing import List, Tuple
import os
import re
from logging import getLogger
import FreeSimpleGUI as sg
import textwrap
from datetime import datetime, timezone
from ruamel.yaml.comments import CommentedMap
from npbackup import configuration
from ofunctions.misc import get_key_from_value, BytesConverter
from npbackup.core.i18n_helper import _t
from npbackup.core.metrics import send_metrics_mail
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
)
from npbackup.task import create_scheduled_task
from npbackup.gui.helpers import quick_close_simplegui_window

logger = getLogger()


# Monkeypatching SimpleGUI
# @SimpleGUI: Why is there no delete method for TreeData ?
def delete(self, key):
    if key == "":
        return False
    try:
        node = self.tree_dict[key]
        key_list = [
            key,
        ]
        parent_node = self.tree_dict[node.parent]
        parent_node.children.remove(node)
        while key_list != []:
            temp = []
            for item in key_list:
                temp += self.tree_dict[item].children
                del self.tree_dict[item]
            key_list = temp
        return True
    except KeyError:
        return False


sg.TreeData.delete = delete


ENCRYPTED_DATA_PLACEHOLDER = "<{}>".format(_t("config_gui.encrypted_data"))


def ask_manager_password(manager_password: str) -> bool:
    if manager_password:
        if sg.PopupGetText(
            _t("config_gui.set_manager_password"), password_char="*"
        ) == str(manager_password):
            return True
        sg.PopupError(_t("config_gui.wrong_password"), keep_on_top=True)
        return False
    return True


def config_gui(full_config: dict, config_file: str):
    logger.info("Launching configuration GUI")

    # Don't let SimpleGUI handle key errors since we might have new keys in config file
    sg.set_options(
        suppress_raise_key_errors=True,
        suppress_error_popups=True,
        suppress_key_guessing=True,
    )

    combo_boxes = {
        "backup_opts.compression": {
            "auto": _t("config_gui.auto"),
            "max": _t("config_gui.max"),
            "off": _t("config_gui.off"),
        },
        "backup_opts.source_type": {
            "folder_list": _t("config_gui.folder_list"),
            "files_from": _t("config_gui.files_from"),
            "files_from_verbatim": _t("config_gui.files_from_verbatim"),
            "files_from_raw": _t("config_gui.files_from_raw"),
            "stdin_from_command": _t("config_gui.stdin_from_command"),
        },
        "backup_opts.priority": {
            "low": _t("config_gui.low"),
            "normal": _t("config_gui.normal"),
            "high": _t("config_gui.high"),
        },
        "permissions": {
            "backup": _t("config_gui.backup_perms"),
            "restore": _t("config_gui.restore_perms"),
            "restore_only": _t("config_gui.restore_only_perms"),
            "full": _t("config_gui.full_perms"),
        },
    }

    byte_units = ["B", "KB", "KiB", "MB", "MiB", "GB", "GiB", "TB", "TiB", "PB", "PiB"]

    def get_objects() -> List[str]:
        """
        Adds repos and groups in a list for combobox
        """
        object_list = []
        for repo in configuration.get_repo_list(full_config):
            object_list.append(f"Repo: {repo}")
        for group in configuration.get_group_list(full_config):
            object_list.append(f"Group: {group}")
        return object_list

    def create_object(full_config: dict) -> dict:
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

        window = sg.Window(
            _t("config_gui.create_object"), layout=layout, keep_on_top=True
        )
        while True:
            event, values = window.read()
            if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--CANCEL--"):
                break
            if event == "--ACCEPT--":
                object_type = (
                    "groups" if values["-OBJECT-TYPE-"] == "group" else "repos"
                )
                object_name = values["-OBJECT-NAME-"]
                if object_name is None or object_name == "" or "." in object_name:
                    sg.PopupError(
                        _t("config_gui.object_name_cannot_be_empty"), keep_on_top=True
                    )
                    continue
                if object_name == "__all__":
                    sg.PopupError(
                        _t("config_gui.object_name_cannot_be_all"), keep_on_top=True
                    )
                    continue
                if object_type == "repos":
                    if full_config.g(f"{object_type}.{object_name}"):
                        sg.PopupError(
                            _t("config_gui.repo_already_exists"), keep_on_top=True
                        )
                        continue
                    full_config.s(f"{object_type}.{object_name}", CommentedMap())
                    full_config.s(
                        f"{object_type}.{object_name}",
                        configuration.get_default_repo_config(),
                    )
                    break
                elif object_type == "groups":
                    if full_config.g(f"{object_type}.{object_name}"):
                        sg.PopupError(
                            _t("config_gui.group_already_exists"), keep_on_top=True
                        )
                        continue
                    full_config.s(
                        f"{object_type}.{object_name}",
                        configuration.get_default_group_config(),
                    )
                    break
                else:
                    raise ValueError("Bogus object type given")
        window.close()
        if object_type and object_name:
            full_config = update_object_gui(
                full_config, object_type, object_name, unencrypted=False
            )
            update_global_gui(full_config, unencrypted=False)
        return full_config, object_type, object_name

    def delete_object(full_config: dict, full_object_name: str) -> dict:
        object_type, object_name = get_object_from_combo(full_object_name)
        if not object_type and not object_name:
            sg.popup_error(_t("config_gui.no_object_to_delete"), keep_on_top=True)
            return full_config
        result = sg.popup_yes_no(
            _t("config_gui.are_you_sure_to_delete") + f" {object_type} {object_name} ?"
        )
        if result == "Yes":
            full_config.d(f"{object_type}.{object_name}")
            full_config = update_object_gui(full_config, None, unencrypted=False)
            update_global_gui(full_config, unencrypted=False)
        return full_config

    def update_object_selector(
        object_name: str = None, object_type: str = None
    ) -> Tuple[str, str]:
        object_list = get_objects()
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
        window["-OBJECT-SELECT-TASKS-"].Update(values=object_list)
        window["-OBJECT-SELECT-TASKS-"].Update(value=obj)

        return get_object_from_combo(obj)

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
            logger.error(
                f"Could not obtain object_type and object_name from {combo_value}"
            )
        return object_type, object_name

    def get_icons_per_file(file_path: str) -> Tuple[str, bytes]:
        """
        Get icons depending on file/folder existing paths
        """
        try:
            if not file_path:
                icon = MISSING_FILE_ICON
                inherited_icon = INHERITED_MISSING_FILE_ICON
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
            elif os.path.islink(file_path):
                icon = SYMLINK_ICON
                inherited_icon = INHERITED_SYMLINK_ICON
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

    def update_source_layout(source_type: str):
        if source_type == "stdin_from_command":
            window["backup_opts.paths"].update(visible=False)
            window["--ADD-PATHS-FILE-BUTTON--"].update(visible=False)
            window["--ADD-PATHS-FOLDER-BUTTON--"].update(visible=False)
            window["--ADD-PATHS-MANUALLY--"].update(visible=False)
            window["--REMOVE-PATHS--"].update(visible=False)
            window["backup_opts.stdin_from_command"].update(visible=True)
            window["inherited.backup_opts.stdin_from_command"].update(visible=True)
            window["text_stdin_from_command"].update(visible=True)
            window["backup_opts.stdin_filename"].update(visible=True)
            window["inherited.backup_opts.stdin_filename"].update(visible=True)
            window["text_stdin_filename"].update(visible=True)
        elif source_type == "folder_list":
            window["backup_opts.paths"].update(visible=True)
            window["--ADD-PATHS-FILE-BUTTON--"].update(visible=True)
            window["--ADD-PATHS-FOLDER-BUTTON--"].update(visible=True)
            window["--ADD-PATHS-MANUALLY--"].update(visible=True)
            window["--REMOVE-PATHS--"].update(visible=True)
            window["backup_opts.stdin_from_command"].update(visible=False)
            window["inherited.backup_opts.stdin_from_command"].update(visible=False)
            window["text_stdin_from_command"].update(visible=False)
            window["backup_opts.stdin_filename"].update(visible=False)
            window["inherited.backup_opts.stdin_filename"].update(visible=False)
            window["text_stdin_filename"].update(visible=False)
        elif source_type in ("files_from", "files_from_verbatim", "files_from_raw"):
            window["backup_opts.paths"].update(visible=True)
            window["--ADD-PATHS-FILE-BUTTON--"].update(visible=True)
            window["--ADD-PATHS-FOLDER-BUTTON--"].update(visible=False)
            window["--ADD-PATHS-MANUALLY--"].update(visible=True)
            window["--REMOVE-PATHS--"].update(visible=True)
            window["backup_opts.stdin_from_command"].update(visible=False)
            window["inherited.backup_opts.stdin_from_command"].update(visible=False)
            window["text_stdin_from_command"].update(visible=False)
            window["backup_opts.stdin_filename"].update(visible=False)
            window["inherited.backup_opts.stdin_filename"].update(visible=False)
            window["text_stdin_filename"].update(visible=False)

    def update_gui_values(key, value, inherited, object_type, unencrypted):
        """
        Update gui values depending on their type
        This not called directly, but rather from update_object_gui which calls iter_over_config which calls this function
        """
        # Do not redefine those variables here since they're not modified, fixes flake8 F824
        # nonlocal BAD_KEYS_FOUND_IN_CONFIG

        # nonlocal backup_paths_tree
        # nonlocal tags_tree
        # nonlocal exclude_files_tree
        # nonlocal exclude_patterns_tree
        # nonlocal pre_exec_commands_tree
        # nonlocal post_exec_commands_tree
        # nonlocal global_prometheus_labels_tree
        # nonlocal env_variables_tree
        # nonlocal encrypted_env_variables_tree

        try:
            # Don't bother to update repo name
            # Also permissions / manager_password are in a separate gui
            # Also, don't update global prometheus options here but in global options
            if key in (
                "name",
                "is_protected",
                "prometheus.metrics",
                "prometheus.destination",
                "prometheus.instance",
                "prometheus.http_username",
                "prometheus.http_password",
                "prometheus.no_cert_verify",
                "current_manager_password",
            ) or key.startswith("prometheus.additional_labels"):
                return
            # Note that keys with "new" must be processed after "current" keys
            # This will happen automatically since adding new values are at the end of the config
            if key in ("permissions", "new_permissions"):
                # So we need to represent no permission as full in GUI
                if value is None:
                    value = "full"
                window["current_permissions"].Update(combo_boxes["permissions"][value])
                return
            if key in ("manager_password", "new_manager_password"):
                if value:
                    window["manager_password_set"].Update(_t("generic.yes"))
                    window["--SET-PERMISSIONS--"].Update(button_color="green")
                else:
                    window["manager_password_set"].Update(_t("generic.no"))
                    window["--SET-PERMISSIONS--"].Update(button_color="red")
                return
            # Since FreeSimpleGUI does not allow to suppress the debugger anymore in v5.1.0, we need to handle KeyError
            if key not in window.AllKeysDict:
                raise KeyError

            # NPF-SEC-00009
            # Don't show sensitive info unless unencrypted requested
            if not unencrypted:
                # Use last part of key only
                if key in configuration.ENCRYPTED_OPTIONS:
                    try:
                        if isinstance(value, dict):
                            for k in value.keys():
                                value[k] = ENCRYPTED_DATA_PLACEHOLDER
                        elif value is not None and not str(value).startswith(
                            configuration.ID_STRING
                        ):
                            value = ENCRYPTED_DATA_PLACEHOLDER
                    except (KeyError, TypeError):
                        pass

            if key in ("repo_uri", "repo_group"):
                if object_type == "groups":
                    window[key].Disabled = True
                    window[key].Update(value=None)
                else:
                    window[key].Disabled = False
                    # Update the combo group selector
                    if value is None:
                        window[key].Update(value="")
                    else:
                        # Update possible values for repo group combobox after a new group is created
                        if key == "repo_group":
                            window[key].Update(
                                values=configuration.get_group_list(full_config)
                            )
                        window[key].Update(value=value)
                return

            # Update tree objects
            if key == "backup_opts.paths":
                if value:
                    for val in value:
                        icon, inherited_icon = get_icons_per_file(val)

                        if object_type != "groups" and inherited[val]:
                            backup_paths_tree.insert(
                                "", val, val, val, icon=inherited_icon
                            )
                        else:
                            backup_paths_tree.insert("", val, val, val, icon=icon)
                    window["backup_opts.paths"].update(values=backup_paths_tree)
                return
            elif key in (
                "backup_opts.tags",
                "backup_opts.pre_exec_commands",
                "backup_opts.post_exec_commands",
                "backup_opts.exclude_files",
                "backup_opts.exclude_patterns",
                "repo_opts.retention_policy.keep_tags",
                "repo_opts.retention_policy.apply_tags",
            ):
                if key == "backup_opts.tags":
                    tree = tags_tree
                elif key == "backup_opts.pre_exec_commands":
                    tree = pre_exec_commands_tree
                elif key == "backup_opts.post_exec_commands":
                    tree = post_exec_commands_tree
                elif key == "backup_opts.exclude_files":
                    tree = exclude_files_tree
                elif key == "backup_opts.exclude_patterns":
                    tree = exclude_patterns_tree
                elif key == "repo_opts.retention_policy.keep_tags":
                    tree = retention_policy_keep_tags_tree
                elif key == "repo_opts.retention_policy.apply_on_tags":
                    tree = retention_policy_apply_on_tags_tree
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
                        logger.error(rf"Bgous configuration value for {key}: {value}")
                return

            if key in (
                "env.env_variables",
                "env.encrypted_env_variables",
                "global_prometheus.additional_labels",
            ):
                if key == "env.env_variables":
                    tree = env_variables_tree
                if key == "env.encrypted_env_variables":
                    tree = encrypted_env_variables_tree
                if key == "global_prometheus.additional_labels":
                    tree = global_prometheus_labels_tree

                if value:
                    if isinstance(value, dict):
                        for skey, val in value.items():
                            if (
                                object_type != "groups"
                                and inherited
                                and inherited[skey]
                            ):
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

        except KeyError:
            msg = f"{_t('config_gui.key_error')}: {key}"
            sg.PopupError(msg)
            logger.error(msg)
            logger.debug("Trace:", exc_info=True)
            BAD_KEYS_FOUND_IN_CONFIG.add(key)
        except TypeError as exc:
            logger.error(
                f"Error: Trying to update GUI with key {key} produced error: {exc}"
            )
            logger.debug("Trace:", exc_info=True)

    def iter_over_config(
        object_config: dict,
        config_inheritance: dict = None,
        object_type: str = None,
        unencrypted: bool = False,
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
                "global_prometheus.additional_labels",
            ):
                for key in object_config.keys():
                    if root_key:
                        _iter_over_config(
                            object_config[key], root_key=f"{root_key}.{key}"
                        )
                    else:
                        _iter_over_config(object_config[key], root_key=f"{key}")
            else:
                if config_inheritance:
                    inherited = config_inheritance.g(root_key)
                else:
                    inherited = False
                update_gui_values(
                    root_key,
                    base_object.g(root_key),
                    inherited,
                    object_type,
                    unencrypted,
                )

        _iter_over_config(object_config, root_key)

    def update_object_gui(
        full_config: dict,
        object_type: str = None,
        object_name: str = None,
        unencrypted: bool = False,
    ) -> dict:
        """
        Reload current object configuration settings to GUI
        """
        nonlocal backup_paths_tree
        nonlocal tags_tree
        nonlocal exclude_files_tree
        nonlocal exclude_patterns_tree
        nonlocal retention_policy_keep_tags_tree
        nonlocal retention_policy_apply_on_tags_tree
        nonlocal pre_exec_commands_tree
        nonlocal post_exec_commands_tree
        nonlocal env_variables_tree
        nonlocal encrypted_env_variables_tree

        # Load fist available repo or group if none given
        if not object_name:
            try:
                object_type, object_name = get_object_from_combo(get_objects()[0])
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
        tags_tree = sg.TreeData()
        exclude_patterns_tree = sg.TreeData()
        exclude_files_tree = sg.TreeData()
        retention_policy_keep_tags_tree = sg.TreeData()
        retention_policy_apply_on_tags_tree = sg.TreeData()
        pre_exec_commands_tree = sg.TreeData()
        post_exec_commands_tree = sg.TreeData()
        env_variables_tree = sg.TreeData()
        encrypted_env_variables_tree = sg.TreeData()

        if object_type == "repos":
            object_config, config_inheritance = configuration.get_repo_config(
                full_config, object_name, eval_variables=False
            )

            # Enable settings only valid for repos
            window["repo_uri"].Update(visible=True)
            window["--SET-PERMISSIONS--"].Update(visible=True)
            window["current_permissions"].Update(visible=True)
            window["manager_password_set"].Update(visible=True)
            window["repo_group"].Update(visible=True)

        elif object_type == "groups":
            object_config = configuration.get_group_config(
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
            object_config, config_inheritance, object_type, unencrypted, None
        )

        # Special case when no source type is set
        if window["backup_opts.source_type"].Get() == "":
            window["backup_opts.source_type"].Update(
                value=combo_boxes["backup_opts.source_type"]["folder_list"]
            )
        source_type = get_key_from_value(
            combo_boxes["backup_opts.source_type"],
            window["backup_opts.source_type"].Get(),
        )
        update_source_layout(source_type)

        if BAD_KEYS_FOUND_IN_CONFIG:
            answer = sg.popup_yes_no(
                _t("config_gui.delete_bad_keys")
                + f": {','.join(BAD_KEYS_FOUND_IN_CONFIG)}",
                keep_on_top=True,
            )
            if answer == "Yes":
                for key in BAD_KEYS_FOUND_IN_CONFIG:
                    full_key_path = f"{object_type}.{object_name}.{key}"
                    logger.info(f"Deleting bogus key {full_key_path}")
                    full_config.d(full_key_path)
        return full_config

    def update_global_gui(full_config, unencrypted: bool = False):
        nonlocal global_prometheus_labels_tree

        global_config = CommentedMap()

        global_prometheus_labels_tree = sg.TreeData()

        # Only update global options gui with identified global keys
        for key in full_config.keys():
            if key in (
                "identity",
                "global_prometheus",
                "global_email",
                "global_options",
            ):
                global_config.s(key, full_config.g(key))
        iter_over_config(global_config, None, "group", unencrypted, None)

    def update_config_dict(full_config, object_type, object_name, values: dict) -> dict:
        """
        Update full_config with keys from GUI
        keys should always have form section.name or section.subsection.name
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

        # We need to patch values since sg.Tree() only returns selected data from TreeData()
        # Hence we'll fill values with a list or a dict depending on our TreeData data structure
        # @simpleGUI: there should be a get_all_values() method or something
        list_tree_data_keys = [
            "backup_opts.paths",
            "backup_opts.tags",
            "backup_opts.pre_exec_commands",
            "backup_opts.post_exec_commands",
            "backup_opts.exclude_files",
            "backup_opts.exclude_patterns",
            "repo_opts.retention_policy.keep_tags",
            "repo_opts.retention_policy.apply_on_tags",
        ]
        for tree_data_key in list_tree_data_keys:
            values[tree_data_key] = []
            # pylint: disable=E1101 (no-member)
            for node in window[tree_data_key].TreeData.tree_dict.values():
                if node.values:
                    values[tree_data_key].append(node.values)

        dict_tree_data_keys = [
            "env.env_variables",
            "env.encrypted_env_variables",
            "global_prometheus.additional_labels",
        ]
        for tree_data_key in dict_tree_data_keys:
            values[tree_data_key] = CommentedMap()
            # pylint: disable=E1101 (no-member)
            for key, node in window[tree_data_key].TreeData.tree_dict.items():
                if key and node.values:
                    values[tree_data_key][key] = node.values[0]

        # Special treatment for env.encrypted_env_variables since they might contain an ENCRYPTED_DATA_PLACEHOLDER
        # We need to update the placeholder to the actual value if exists
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
                            logger.debug(
                                f"BytesConverter could not convert value: {exc}"
                            )

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

        # Remove injected global prometheus config
        for prom_key in (
            "metrics",
            "destination",
            "additional_labels",
            "instance",
            "http_username",
            "http_password",
            "no_cert_verify",
        ):
            full_config.d(f"repos.{object_name}.prometheus.{prom_key}")
        return full_config

    def set_permissions(full_config: dict, object_type: str, object_name: str) -> dict:
        """
        Sets repo wide repo_uri / password / permissions
        """
        if object_type == "groups":
            sg.PopupError(_t("config_gui.permissions_only_for_repos"), keep_on_top=True)
            return full_config
        permissions = list(combo_boxes["permissions"].values())
        current_perm = full_config.g(f"{object_type}.{object_name}.permissions")
        if not current_perm:
            # So we need to represent no permission as full in GUI, so if not set, let's take highest permission
            current_perm = permissions[-1]
        else:
            current_perm = combo_boxes["permissions"][current_perm]
        manager_password = full_config.g(
            f"{object_type}.{object_name}.manager_password"
        )

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

        window = sg.Window(_t("config_gui.permissions"), layout, keep_on_top=True)
        window.finalize()
        # Stupid fix because using window update method will fill input with "0" if False is given
        window["-MANAGER-PASSWORD-"].Update(
            manager_password if manager_password else ""
        )
        while True:
            event, values = window.read()
            if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--CANCEL--"):
                break
            if event == "--ACCEPT--":
                if not values["-MANAGER-PASSWORD-"]:
                    sg.PopupError(
                        _t("config_gui.setting_permissions_requires_manager_password"),
                        keep_on_top=True,
                    )
                    continue
                # Courtesy of https://uibakery.io/regex-library/password-regex-python
                if not re.findall(
                    r"^(?=.*?[A-Z])(?=.*?[a-z])(?=.*?[0-9]).{8,}$",
                    values["-MANAGER-PASSWORD-"],
                ):
                    sg.PopupError(
                        _t("config_gui.manager_password_too_simple"), keep_on_top=True
                    )
                    continue
                if not values["permissions"] in permissions:
                    sg.PopupError(_t("generic.bogus_data_given"), keep_on_top=True)
                    continue
                # Transform translated permission value into key
                permission = get_key_from_value(
                    combo_boxes["permissions"], values["permissions"]
                )
                full_config.s(
                    f"{object_type}.{object_name}.new_permissions", permission
                )
                full_config.s(
                    f"{object_type}.{object_name}.new_manager_password",
                    values["-MANAGER-PASSWORD-"],
                )
                break
            if event == "--SUPPRESS-PASSWORD--":
                full_config.s(f"{object_type}.{object_name}.new_permissions", "full")
                full_config.s(
                    f"{object_type}.{object_name}.new_manager_password", False
                )
                break
        window.close()
        return full_config

    def object_layout() -> List[list]:
        """
        Returns the GUI layout depending on the object type
        """
        backup_col = [
            [
                sg.Text(
                    textwrap.fill(f"{_t('config_gui.backup_paths')}"),
                    size=(None, None),
                    expand_x=True,
                ),
                sg.Text(
                    textwrap.fill(f"{_t('config_gui.source_type')}"),
                    size=(None, None),
                    expand_x=True,
                    justification="R",
                ),
                sg.Combo(
                    list(combo_boxes["backup_opts.source_type"].values()),
                    key="backup_opts.source_type",
                    size=(48, 1),
                    enable_events=True,
                ),
            ],
            [
                sg.Input(visible=False, key="--ADD-PATHS-FILE--", enable_events=True),
                sg.FilesBrowse(
                    _t("generic.add_files"),
                    target="--ADD-PATHS-FILE--",
                    key="--ADD-PATHS-FILE-BUTTON--",
                ),
                sg.Input(visible=False, key="--ADD-PATHS-FOLDER--", enable_events=True),
                sg.FolderBrowse(
                    _t("generic.add_folder"),
                    target="--ADD-PATHS-FOLDER--",
                    key="--ADD-PATHS-FOLDER-BUTTON--",
                ),
                sg.Button(_t("generic.add_manually"), key="--ADD-PATHS-MANUALLY--"),
                sg.Button(_t("generic.remove_selected"), key="--REMOVE-PATHS--"),
            ],
            [
                sg.Tree(
                    sg.TreeData(),
                    key="backup_opts.paths",
                    headings=[],
                    col0_heading=_t("generic.paths"),
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Text(
                    _t("config_gui.stdin_from_command"),
                    key="text_stdin_from_command",
                    visible=False,
                )
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.stdin_from_command",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                    visible=False,
                ),
                sg.Input(
                    key="backup_opts.stdin_from_command", size=(100, 1), visible=False
                ),
            ],
            [
                sg.Text(
                    _t("config_gui.stdin_filename"),
                    key="text_stdin_filename",
                    visible=False,
                )
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.stdin_filename",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                    visible=False,
                ),
                sg.Input(
                    key="backup_opts.stdin_filename", size=(100, 1), visible=False
                ),
            ],
            [
                sg.Column(
                    [
                        [
                            sg.Text(_t("config_gui.compression"), size=(20, None)),
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.backup_opts.compression",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Combo(
                                list(combo_boxes["backup_opts.compression"].values()),
                                key="backup_opts.compression",
                                size=(20, 1),
                                pad=0,
                            ),
                        ],
                        [
                            sg.Text(_t("config_gui.backup_priority"), size=(20, 1)),
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.backup_opts.priority",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Combo(
                                list(combo_boxes["backup_opts.priority"].values()),
                                key="backup_opts.priority",
                                size=(20, 1),
                                pad=0,
                            ),
                        ],
                        [
                            sg.Column(
                                [
                                    [
                                        sg.Button(
                                            "+", key="--ADD-BACKUP-TAG--", size=(3, 1)
                                        )
                                    ],
                                    [
                                        sg.Button(
                                            "-",
                                            key="--REMOVE-BACKUP-TAG--",
                                            size=(3, 1),
                                        )
                                    ],
                                ],
                                pad=0,
                                size=(40, 80),
                            ),
                            sg.Column(
                                [
                                    [
                                        sg.Tree(
                                            sg.TreeData(),
                                            key="backup_opts.tags",
                                            headings=[],
                                            col0_heading="Tags",
                                            col0_width=30,
                                            num_rows=3,
                                            expand_x=True,
                                            expand_y=True,
                                        )
                                    ]
                                ],
                                pad=0,
                                size=(300, 80),
                            ),
                        ],
                    ],
                    pad=0,
                ),
                sg.Column(
                    [
                        [
                            sg.Text(
                                _t("config_gui.minimum_backup_size_error"), size=(40, 2)
                            ),
                        ],
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.backup_opts.minimum_backup_size_error",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="backup_opts.minimum_backup_size_error", size=(8, 1)
                            ),
                            sg.Combo(
                                byte_units,
                                default_value=byte_units[3],
                                key="backup_opts.minimum_backup_size_error_unit",
                            ),
                        ],
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.backup_opts.use_fs_snapshot",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Checkbox(
                                textwrap.fill(
                                    f'{_t("config_gui.use_fs_snapshot")}', width=34
                                ),
                                key="backup_opts.use_fs_snapshot",
                                size=(40, 1),
                                pad=0,
                            ),
                        ],
                    ]
                ),
            ],
            [
                sg.Text(
                    _t("config_gui.additional_backup_only_parameters"), size=(40, 1)
                ),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.additional_backup_only_parameters",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(
                    key="backup_opts.additional_backup_only_parameters", size=(100, 1)
                ),
            ],
            [
                sg.Text(
                    _t("config_gui.additional_restore_only_parameters"), size=(40, 1)
                ),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.additional_restore_only_parameters",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(
                    key="backup_opts.additional_restore_only_parameters", size=(100, 1)
                ),
            ],
        ]

        exclusions_col = [
            [
                sg.Column(
                    [
                        [sg.Button("+", key="--ADD-EXCLUDE-PATTERN--", size=(3, 1))],
                        [sg.Button("-", key="--REMOVE-EXCLUDE-PATTERN--", size=(3, 1))],
                    ],
                    pad=0,
                ),
                sg.Column(
                    [
                        [
                            sg.Tree(
                                sg.TreeData(),
                                key="backup_opts.exclude_patterns",
                                headings=[],
                                col0_heading=_t("config_gui.exclude_patterns"),
                                num_rows=4,
                                expand_x=True,
                                expand_y=True,
                            )
                        ]
                    ],
                    pad=0,
                    expand_x=True,
                ),
            ],
            [sg.HSeparator()],
            [
                sg.Column(
                    [
                        [
                            sg.Input(
                                visible=False,
                                key="--ADD-EXCLUDE-FILE--",
                                enable_events=True,
                            ),
                            sg.FilesBrowse(
                                "+", target="--ADD-EXCLUDE-FILE--", size=(3, 1)
                            ),
                        ],
                        [
                            sg.Button(
                                "M", key="--ADD-EXCLUDE-FILE-MANUALLY--", size=(3, 1)
                            )
                        ],
                        [sg.Button("-", key="--REMOVE-EXCLUDE-FILE--", size=(3, 1))],
                    ],
                    pad=0,
                ),
                sg.Column(
                    [
                        [
                            sg.Tree(
                                sg.TreeData(),
                                key="backup_opts.exclude_files",
                                headings=[],
                                col0_heading=_t("config_gui.exclude_files"),
                                num_rows=4,
                                expand_x=True,
                                expand_y=True,
                            )
                        ]
                    ],
                    pad=0,
                    expand_x=True,
                ),
            ],
            [sg.HSeparator()],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.exclude_files_larger_than",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Text(
                    _t("config_gui.exclude_files_larger_than"),
                    size=(40, 1),
                ),
                sg.Input(key="backup_opts.exclude_files_larger_than", size=(8, 1)),
                sg.Combo(
                    byte_units,
                    default_value=byte_units[3],
                    key="backup_opts.exclude_files_larger_than_unit",
                ),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.ignore_cloud_files",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Checkbox(
                    f'{_t("config_gui.ignore_cloud_files")} ({_t("config_gui.windows_only")})',
                    key="backup_opts.ignore_cloud_files",
                    size=(None, 1),
                ),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.excludes_case_ignore",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Checkbox(
                    f'{_t("config_gui.excludes_case_ignore")} ({_t("config_gui.windows_always")})',
                    key="backup_opts.excludes_case_ignore",
                    size=(None, 1),
                ),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.exclude_caches",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Checkbox(
                    _t("config_gui.exclude_cache_dirs"),
                    key="backup_opts.exclude_caches",
                    size=(None, 1),
                ),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.one_file_system",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Checkbox(
                    _t("config_gui.one_file_system"),
                    key="backup_opts.one_file_system",
                    size=(None, 1),
                ),
            ],
        ]

        pre_post_col = [
            [
                sg.Column(
                    [
                        [sg.Button("+", key="--ADD-PRE-EXEC-COMMAND--", size=(3, 1))],
                        [
                            sg.Button(
                                "-", key="--REMOVE-PRE-EXEC-COMMAND--", size=(3, 1)
                            )
                        ],
                    ],
                    pad=0,
                ),
                sg.Column(
                    [
                        [
                            sg.Tree(
                                sg.TreeData(),
                                key="backup_opts.pre_exec_commands",
                                headings=[],
                                col0_heading=_t("config_gui.pre_exec_commands"),
                                num_rows=4,
                                expand_x=True,
                                expand_y=True,
                            )
                        ]
                    ],
                    pad=0,
                    expand_x=True,
                ),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.pre_exec_per_command_timeout",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Text(_t("config_gui.maximum_exec_time"), size=(40, 1)),
                sg.Input(key="backup_opts.pre_exec_per_command_timeout", size=(8, 1)),
                sg.Text(_t("generic.seconds")),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.pre_exec_failure_is_fatal",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Checkbox(
                    _t("config_gui.exec_failure_is_fatal"),
                    key="backup_opts.pre_exec_failure_is_fatal",
                    size=(41, 1),
                ),
            ],
            [sg.HorizontalSeparator()],
            [
                sg.Column(
                    [
                        [sg.Button("+", key="--ADD-POST-EXEC-COMMAND--", size=(3, 1))],
                        [
                            sg.Button(
                                "-", key="--REMOVE-POST-EXEC-COMMAND--", size=(3, 1)
                            )
                        ],
                    ],
                    pad=0,
                ),
                sg.Column(
                    [
                        [
                            sg.Tree(
                                sg.TreeData(),
                                key="backup_opts.post_exec_commands",
                                headings=[],
                                col0_heading=_t("config_gui.post_exec_commands"),
                                num_rows=4,
                                expand_x=True,
                                expand_y=True,
                            )
                        ]
                    ],
                    pad=0,
                    expand_x=True,
                ),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.post_exec_per_command_timeout",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Text(_t("config_gui.maximum_exec_time"), size=(40, 1)),
                sg.Input(key="backup_opts.post_exec_per_command_timeout", size=(8, 1)),
                sg.Text(_t("generic.seconds")),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.post_exec_failure_is_fatal",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Checkbox(
                    _t("config_gui.exec_failure_is_fatal"),
                    key="backup_opts.post_exec_failure_is_fatal",
                    size=(41, 1),
                ),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.post_exec_execute_even_on_backup_error",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Checkbox(
                    _t("config_gui.execute_even_on_backup_error"),
                    key="backup_opts.post_exec_execute_even_on_backup_error",
                    size=(41, 1),
                ),
            ],
        ]

        repo_col = [
            [
                sg.Text(_t("config_gui.backup_repo_uri"), size=(40, 1)),
            ],
            [
                sg.Image(NON_INHERITED_ICON, pad=1),
                sg.Input(key="repo_uri", size=(95, 1), enable_events=True),
            ],
            [
                sg.Text(
                    _t("config_gui.repo_uri_cloud_hint"),
                    key="repo_uri_cloud_hint",
                    visible=False,
                )
            ],
            [
                sg.Text(_t("config_gui.backup_repo_password"), size=(40, 1)),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.repo_password",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="repo_opts.repo_password", size=(95, 1)),
            ],
            [
                sg.Text(_t("config_gui.backup_repo_password_command"), size=(95, 1)),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.repo_password_command",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="repo_opts.repo_password_command", size=(95, 1)),
            ],
            [
                sg.Text(_t("config_gui.current_permissions"), size=(40, 1)),
                sg.Image(NON_INHERITED_ICON, pad=1),
                sg.Text("Default", key="current_permissions", size=(25, 1)),
            ],
            [
                sg.Text(_t("config_gui.manager_password_set"), size=(40, 1)),
                sg.Image(NON_INHERITED_ICON, pad=1),
                sg.Text(_t("generic.no"), key="manager_password_set", size=(25, 1)),
            ],
            [
                sg.Text(" ", size=(40, 1)),
                sg.Image(NON_INHERITED_ICON, pad=1),
                sg.Button(
                    _t("config_gui.set_permissions"),
                    key="--SET-PERMISSIONS--",
                    size=(35, 1),
                    button_color="red",
                ),
            ],
            [
                sg.Text(_t("config_gui.repo_group"), size=(40, 1)),
                sg.Image(NON_INHERITED_ICON, pad=1),
                sg.Combo(
                    values=configuration.get_group_list(full_config),
                    key="repo_group",
                    enable_events=True,
                ),
            ],
            [
                sg.Text(
                    _t("config_gui.minimum_backup_age"),
                    size=(40, 2),
                ),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.minimum_backup_age",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="repo_opts.minimum_backup_age", size=(8, 1)),
                sg.Text(_t("generic.minutes")),
            ],
            [
                sg.Text(
                    _t("config_gui.random_delay_before_backup"),
                    size=(40, 2),
                ),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.random_delay_before_backup",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="repo_opts.random_delay_before_backup", size=(8, 1)),
                sg.Text(_t("generic.minutes")),
            ],
            [
                sg.Text(_t("config_gui.upload_speed"), size=(40, 1)),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.upload_speed",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="repo_opts.upload_speed", size=(8, 1)),
                sg.Combo(
                    byte_units,
                    default_value=byte_units[3],
                    key="repo_opts.upload_speed_unit",
                ),
            ],
            [
                sg.Text(_t("config_gui.download_speed"), size=(40, 1)),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.download_speed",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="repo_opts.download_speed", size=(8, 1)),
                sg.Combo(
                    byte_units,
                    default_value=byte_units[3],
                    key="repo_opts.download_speed_unit",
                ),
            ],
            [
                sg.Text(_t("config_gui.backend_connections"), size=(40, 1)),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.backend_connections",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="repo_opts.backend_connections", size=(8, 1)),
            ],
        ]

        retention_col = [
            [
                sg.Column(
                    [
                        [
                            sg.Text(_t("config_gui.keep"), size=(30, 1)),
                        ]
                    ]
                ),
                sg.Column(
                    [
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.repo_opts.retention_policy.last",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="repo_opts.retention_policy.last", size=(3, 1)
                            ),
                            sg.Text(_t("config_gui.last"), size=(20, 1)),
                        ],
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.repo_opts.retention_policy.hourly",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="repo_opts.retention_policy.hourly", size=(3, 1)
                            ),
                            sg.Text(_t("config_gui.hourly"), size=(20, 1)),
                        ],
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.repo_opts.retention_policy.daily",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="repo_opts.retention_policy.daily", size=(3, 1)
                            ),
                            sg.Text(_t("config_gui.daily"), size=(20, 1)),
                        ],
                    ],
                ),
                sg.Column(
                    [
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.repo_opts.retention_policy.weekly",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="repo_opts.retention_policy.weekly", size=(3, 1)
                            ),
                            sg.Text(_t("config_gui.weekly"), size=(20, 1)),
                        ],
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.repo_opts.retention_policy.monthly",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="repo_opts.retention_policy.monthly", size=(3, 1)
                            ),
                            sg.Text(_t("config_gui.monthly"), size=(20, 1)),
                        ],
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.repo_opts.retention_policy.yearly",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="repo_opts.retention_policy.yearly", size=(3, 1)
                            ),
                            sg.Text(_t("config_gui.yearly"), size=(20, 1)),
                        ],
                    ]
                ),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.retention_policy.keep_within",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Checkbox(
                    _t("config_gui.keep_within"),
                    key="repo_opts.retention_policy.keep_within",
                    size=(100, 1),
                ),
            ],
            [sg.Text(_t("config_gui.policiy_group_by"))],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.retention_policy.group_by_host",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Checkbox(
                    _t("config_gui.group_by_host"),
                    key="repo_opts.retention_policy.group_by_host",
                ),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.retention_policy.group_by_paths",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Checkbox(
                    _t("config_gui.group_by_paths"),
                    key="repo_opts.retention_policy.group_by_paths",
                ),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.retention_policy.group_by_tags",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Checkbox(
                    _t("config_gui.group_by_tags"),
                    key="repo_opts.retention_policy.group_by_tags",
                ),
            ],
            [sg.Text(_t("config_gui.policiy_group_by_explanation"))],
            [sg.HorizontalSeparator()],
            [
                sg.Column(
                    [
                        [sg.Button("+", key="--ADD-RETENTION-KEEP-TAG--", size=(3, 1))],
                        [
                            sg.Button(
                                "-", key="--REMOVE-RETENTION-KEEP-TAG--", size=(3, 1)
                            )
                        ],
                    ],
                    pad=0,
                ),
                sg.Column(
                    [
                        [
                            sg.Tree(
                                sg.TreeData(),
                                key="repo_opts.retention_policy.keep_tags",
                                headings=[],
                                col0_heading=_t("config_gui.keep_tags"),
                                num_rows=3,
                                expand_x=True,
                                expand_y=True,
                            )
                        ]
                    ],
                    pad=0,
                    expand_x=True,
                ),
                sg.Column(
                    [
                        [
                            sg.Button(
                                "+", key="--ADD-RETENTION-APPLY-ON-TAG--", size=(3, 1)
                            )
                        ],
                        [
                            sg.Button(
                                "-",
                                key="--REMOVE-RETENTION-APPLY-ON-TAG--",
                                size=(3, 1),
                            )
                        ],
                    ],
                    pad=0,
                ),
                sg.Column(
                    [
                        [
                            sg.Tree(
                                sg.TreeData(),
                                key="repo_opts.retention_policy.apply_on_tags",
                                headings=[],
                                col0_heading=_t("config_gui.apply_on_tags"),
                                num_rows=3,
                                expand_x=True,
                                expand_y=True,
                            )
                        ]
                    ],
                    pad=0,
                    expand_x=True,
                ),
            ],
            [sg.HorizontalSeparator()],
            [],
            [sg.HorizontalSeparator()],
            [
                sg.Text(
                    _t("config_gui.post_backup_housekeeping_percent_chance"),
                    size=(40, 1),
                ),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.post_backup_housekeeping_percent_chance",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(
                    key="backup_opts.post_backup_housekeeping_percent_chance",
                    size=(8, 1),
                ),
            ],
            [
                sg.Text(
                    _t(
                        "config_gui.post_backup_housekeeping_percent_chance_explanation"
                    ),
                    size=(100, 1),
                ),
            ],
            [
                sg.Text(
                    _t("config_gui.post_backup_housekeeping_interval"),
                    size=(40, 1),
                ),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.post_backup_housekeeping_interval",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(
                    key="backup_opts.post_backup_housekeeping_interval",
                    size=(8, 1),
                ),
            ],
            [
                sg.Text(
                    _t("config_gui.post_backup_housekeeping_interval_explanation"),
                    size=(100, 1),
                ),
            ],
            [sg.HorizontalSeparator()],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.retention_policy.ntp_server",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Text(_t("config_gui.optional_ntp_server_uri"), size=(40, 1)),
                sg.Input(key="repo_opts.retention_policy.ntp_server", size=(50, 1)),
            ],
            [sg.HorizontalSeparator()],
            [
                sg.Text(_t("config_gui.prune_max_unused"), size=(40, 1)),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.prune_max_unused",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="repo_opts.prune_max_unused", size=(8, 1)),
                sg.Combo(
                    byte_units + ["%"],
                    default_value=byte_units[3],
                    key="repo_opts.prune_max_unused_unit",
                ),
            ],
            [
                sg.Text(_t("config_gui.prune_max_unused_explanation"), size=(100, 1)),
            ],
            [
                sg.Text(_t("config_gui.prune_max_repack_size"), size=(40, 1)),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.prune_max_repack_size",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="repo_opts.prune_max_repack_size", size=(8, 1)),
                sg.Combo(
                    byte_units,
                    default_value=byte_units[3],
                    key="repo_opts.prune_max_repack_size_unit",
                ),
            ],
            [
                sg.Text(
                    _t("config_gui.prune_max_repack_size_explanation"), size=(100, 1)
                ),
            ],
        ]

        prometheus_col = [
            [sg.Text(_t("config_gui.available_variables"))],
            [
                sg.Text(_t("config_gui.job_name"), size=(40, 1)),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.prometheus.backup_job",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="prometheus.backup_job", size=(50, 1)),
            ],
            [
                sg.Text(_t("generic.group"), size=(40, 1)),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.prometheus.group",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="prometheus.group", size=(50, 1)),
            ],
        ]

        env_col = [
            [
                sg.Column(
                    [
                        [sg.Button("+", key="--ADD-ENV-VARIABLE--", size=(3, 1))],
                        [sg.Button("-", key="--REMOVE-ENV-VARIABLE--", size=(3, 1))],
                    ],
                    pad=0,
                ),
                sg.Column(
                    [
                        [
                            sg.Tree(
                                sg.TreeData(),
                                key="env.env_variables",
                                headings=[_t("generic.value")],
                                col0_heading=_t("config_gui.env_variables"),
                                col0_width=1,
                                auto_size_columns=True,
                                justification="L",
                                num_rows=4,
                                expand_x=True,
                                expand_y=True,
                            )
                        ]
                    ],
                    pad=0,
                    expand_x=True,
                ),
            ],
            [
                sg.Column(
                    [
                        [
                            sg.Button(
                                "+", key="--ADD-ENCRYPTED-ENV-VARIABLE--", size=(3, 1)
                            )
                        ],
                        [
                            sg.Button(
                                "-",
                                key="--REMOVE-ENCRYPTED-ENV-VARIABLE--",
                                size=(3, 1),
                            )
                        ],
                    ],
                    pad=0,
                ),
                sg.Column(
                    [
                        [
                            sg.Tree(
                                sg.TreeData(),
                                key="env.encrypted_env_variables",
                                headings=[_t("generic.value")],
                                col0_heading=_t("config_gui.encrypted_env_variables"),
                                col0_width=1,
                                auto_size_columns=True,
                                justification="L",
                                num_rows=4,
                                expand_x=True,
                                expand_y=True,
                            )
                        ]
                    ],
                    pad=0,
                    expand_x=True,
                ),
            ],
            [
                sg.Text(_t("config_gui.add_identity")),
                sg.Button("S3", key="--ADD-S3-IDENTITY--"),
                sg.Button("Azure", key="--ADD-AZURE-IDENTITY--"),
                sg.Button("B2", key="--ADD-B2-IDENTITY--"),
                sg.Button("Google Cloud Storage", key="--ADD-GCS-IDENTITY--"),
            ],
            [
                sg.Text(
                    _t("config_gui.suggested_encrypted_env_variables"), size=(40, 1)
                ),
            ],
            [
                sg.Multiline(
                    "\
AWS / S3:             AWS_ACCESS_KEY_ID  AWS_SECRET_ACCESS_KEY\n\
AZURE:                AZURE_ACCOUNT_KEY  AZURE_ACCOUNT_SAS  AZURE_ACCOUNT_NAME\n\
B2:                   B2_ACCOUNT_ID      B2_ACCOUNT_KEY\n\
Google Cloud storage: GOOGLE_PROJECT_ID  GOOGLE_APPLICATION_CREDENTIALS\n\
",
                    size=(80, 4),
                    disabled=True,
                    font=("Courier", 12),
                    no_scrollbar=True,
                ),
            ],
            [
                sg.Text(_t("config_gui.additional_parameters"), size=(40, 1)),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.additional_parameters",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="backup_opts.additional_parameters", size=(100, 1)),
            ],
        ]

        object_list = get_objects()
        object_selector = [
            [
                sg.Text(_t("config_gui.select_object")),
                sg.Combo(
                    object_list,
                    default_value=object_list[0] if object_list else None,
                    key="-OBJECT-SELECT-",
                    enable_events=True,
                ),
            ]
        ]

        tab_group_layout = [
            [
                sg.Tab(
                    _t("config_gui.backup"),
                    backup_col,
                    font="helvetica 16",
                    key="--tab-backup--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.backup_destination"),
                    repo_col,
                    font="helvetica 16",
                    key="--tab-repo--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.exclusions"),
                    exclusions_col,
                    font="helvetica 16",
                    key="--tab-exclusions--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.retention_policy"),
                    retention_col,
                    font="helvetica 16",
                    key="--tab-retention--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.pre_post"),
                    pre_post_col,
                    font="helvetica 16",
                    key="--tab-hooks--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.prometheus_config"),
                    prometheus_col,
                    font="helvetica 16",
                    key="--tab-prometheus--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.env_variables"),
                    env_col,
                    font="helvetica 16",
                    key="--tab-env--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
        ]

        _layout = [
            [
                sg.Column(
                    object_selector,
                )
            ],
            [
                sg.TabGroup(
                    tab_group_layout, enable_events=True, key="--object-tabgroup--"
                )
            ],
        ]
        return _layout

    def global_options_layout():
        """ "
        Returns layout for global options that can't be overridden by group / repo settings
        """
        identity_col = [
            [sg.Text(_t("config_gui.available_variables_id"))],
            [
                sg.Text(_t("config_gui.machine_id"), size=(40, 1)),
                sg.Input(key="identity.machine_id", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.machine_group"), size=(40, 1)),
                sg.Input(key="identity.machine_group", size=(50, 1)),
            ],
        ]
        global_options_col = [
            [sg.Text(_t("config_gui.available_variables"))],
            [
                sg.Text(_t("config_gui.auto_upgrade"), size=(40, 1)),
                sg.Checkbox("", key="global_options.auto_upgrade", size=(41, 1)),
            ],
            [
                sg.Text(_t("config_gui.auto_upgrade_server_url"), size=(40, 1)),
                sg.Input(key="global_options.auto_upgrade_server_url", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.auto_upgrade_server_username"), size=(40, 1)),
                sg.Input(
                    key="global_options.auto_upgrade_server_username", size=(50, 1)
                ),
            ],
            [
                sg.Text(_t("config_gui.auto_upgrade_server_password"), size=(40, 1)),
                sg.Input(
                    key="global_options.auto_upgrade_server_password", size=(50, 1)
                ),
            ],
            [
                sg.Text(_t("config_gui.auto_upgrade_percent_chance"), size=(40, 1)),
                sg.Input(
                    key="global_options.auto_upgrade_percent_chance", size=(50, 1)
                ),
            ],
            [
                sg.Text(_t("config_gui.auto_upgrade_interval"), size=(40, 1)),
                sg.Input(key="global_options.auto_upgrade_interval", size=(50, 1)),
            ],
            [
                sg.Text(_t("generic.identity"), size=(40, 1)),
                sg.Input(key="global_options.auto_upgrade_host_identity", size=(50, 1)),
            ],
            [
                sg.Text(_t("generic.group"), size=(40, 1)),
                sg.Input(key="global_options.auto_upgrade_group", size=(50, 1)),
            ],
            [sg.HorizontalSeparator()],
            [
                sg.Text(_t("config_gui.full_concurrency"), size=(40, 1)),
                sg.Checkbox("", key="global_options.full_concurrency", size=(41, 1)),
            ],
            [
                sg.Text(_t("config_gui.repo_aware_concurrency"), size=(40, 1)),
                sg.Checkbox(
                    "", key="global_options.repo_aware_concurrency", size=(41, 1)
                ),
            ],
        ]

        global_prometheus_col = [
            [sg.Text(_t("config_gui.available_variables"))],
            [
                sg.Checkbox(
                    _t("config_gui.enable_prometheus"),
                    key="global_prometheus.metrics",
                    size=(41, 1),
                ),
            ],
            [
                sg.Text(_t("config_gui.metrics_destination"), size=(40, 1)),
                sg.Input(key="global_prometheus.destination", size=(50, 1)),
            ],
            [
                sg.Text("", size=(40, 1)),
                sg.Text(
                    "Ex: /var/lib/node_exporter/textfile_collector/npbackup.prom",
                    size=(50, 1),
                ),
            ],
            [
                sg.Text("", size=(40, 1)),
                sg.Text(
                    "Ex: https://push.domain.tld/metrics/job/${BACKUP_JOB}",
                    size=(50, 1),
                ),
            ],
            [
                sg.Text(_t("config_gui.no_cert_verify"), size=(40, 1)),
                sg.Checkbox("", key="global_prometheus.no_cert_verify", size=(41, 1)),
            ],
            [
                sg.Text(_t("config_gui.metrics_username"), size=(40, 1)),
                sg.Input(key="global_prometheus.http_username", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.metrics_password"), size=(40, 1)),
                sg.Input(key="global_prometheus.http_password", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.prometheus_instance"), size=(40, 1)),
                sg.Input(key="global_prometheus.instance", size=(50, 1)),
            ],
            [
                sg.Column(
                    [
                        [sg.Button("+", key="--ADD-PROMETHEUS-LABEL--", size=(3, 1))],
                        [
                            sg.Button(
                                "-", key="--REMOVE-PROMETHEUS-LABEL--", size=(3, 1)
                            )
                        ],
                    ],
                    pad=0,
                ),
                sg.Column(
                    [
                        [
                            sg.Tree(
                                sg.TreeData(),
                                key="global_prometheus.additional_labels",
                                headings=[_t("generic.value")],
                                col0_heading=_t("config_gui.additional_labels"),
                                col0_width=1,
                                auto_size_columns=True,
                                justification="L",
                                num_rows=4,
                                expand_x=True,
                                expand_y=True,
                            )
                        ]
                    ],
                    pad=0,
                    expand_x=True,
                ),
            ],
        ]

        global_email_col = [
            [sg.Text(_t("config_gui.available_variables"))],
            [
                sg.Checkbox(
                    _t("config_gui.enable_email_notifications"),
                    key="global_email.enable",
                    size=(41, 1),
                ),
            ],
            [
                sg.Text(_t("config_gui.email_instance"), size=(40, 1)),
                sg.Input(key="global_email.instance", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.smtp_server"), size=(40, 1)),
                sg.Input(key="global_email.smtp_server", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.smtp_port"), size=(40, 1)),
                sg.Input(key="global_email.smtp_port", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.smtp_security"), size=(40, 1)),
                sg.Combo(
                    ["None", "ssl", "tls"],
                    key="global_email.smtp_security",
                    size=(50, 1),
                ),
            ],
            [
                sg.Text(_t("config_gui.smtp_username"), size=(40, 1)),
                sg.Input(key="global_email.smtp_username", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.smtp_password"), size=(40, 1)),
                sg.Input(key="global_email.smtp_password", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.sender"), size=(40, 1)),
                sg.Input(key="global_email.sender", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.recipients"), size=(40, 1)),
                sg.Input(key="global_email.recipients", size=(50, 1)),
            ],
            [
                sg.Checkbox(
                    _t("config_gui.email_on_backup_success"),
                    key="global_email.on_backup_success",
                    size=(41, 1),
                ),
            ],
            [
                sg.Checkbox(
                    _t("config_gui.email_on_backup_failure"),
                    key="global_email.on_backup_failure",
                    size=(41, 1),
                ),
            ],
            [
                sg.Checkbox(
                    _t("config_gui.email_on_operations_success"),
                    key="global_email.on_operations_success",
                    size=(41, 1),
                ),
            ],
            [
                sg.Checkbox(
                    _t("config_gui.email_on_operations_failure"),
                    key="global_email.on_operations_failure",
                    size=(41, 1),
                ),
            ],
            [
                sg.Button(
                    _t("config_gui.test_email"), key="--TEST-EMAIL--", size=(20, 1)
                )
            ],
        ]

        tab_group_layout = [
            [
                sg.Tab(
                    _t("config_gui.machine_identification"),
                    identity_col,
                    font="helvetica 16",
                    key="--tab-global-identification--",
                )
            ],
            [
                sg.Tab(
                    _t("generic.options"),
                    global_options_col,
                    font="helvetica 16",
                    key="--tab-global-options--",
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.prometheus_config"),
                    global_prometheus_col,
                    font="helvetica 16",
                    key="--tab-global-prometheus--",
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.email_config"),
                    global_email_col,
                    font="helvetica 16",
                    key="--tab-global-email--",
                )
            ],
        ]

        _layout = [
            [
                sg.TabGroup(
                    tab_group_layout, enable_events=True, key="--global-tabgroup--"
                )
            ],
        ]
        return _layout

    def config_layout() -> List[list]:
        buttons = [
            [
                sg.Push(),
                sg.Button(
                    _t("config_gui.add_object"), key="-OBJECT-CREATE-", size=(28, 1)
                ),
                sg.Button(
                    _t("config_gui.delete_object"), key="-OBJECT-DELETE-", size=(28, 1)
                ),
                sg.Button(_t("generic.cancel"), key="--CANCEL--", size=(13, 1)),
                sg.Button(_t("generic.accept"), key="--ACCEPT--", size=(13, 1)),
            ]
        ]

        object_list = get_objects()
        scheduled_task_col = [
            [
                sg.Text(
                    textwrap.fill(
                        f"{_t('config_gui.scheduled_task_explanation')}", width=120
                    ),
                    size=(100, 4),
                )
            ],
            [
                sg.Text(_t("config_gui.select_object")),
                sg.Combo(
                    object_list,
                    default_value=object_list[0] if object_list else None,
                    key="-OBJECT-SELECT-TASKS-",
                    enable_events=True,
                ),
            ],
            [
                sg.Text(
                    _t("config_gui.create_backup_scheduled_task_every"), size=(40, 1)
                ),
                sg.Input("15", key="scheduled_backup_task_interval", size=(4, 1)),
                sg.Text(_t("generic.minutes"), size=(10, 1)),
                sg.Button(_t("generic.create"), key="create_backup_interval_task"),
            ],
            [
                sg.Text(_t("config_gui.create_backup_scheduled_task_at"), size=(40, 1)),
                sg.Input("22", key="scheduled_backup_task_hour", size=(4, 1)),
                sg.Text(_t("generic.hours"), size=(10, 1)),
                sg.Input("00", key="scheduled_backup_task_minute", size=(4, 1)),
                sg.Text(_t("generic.minutes"), size=(10, 1)),
                sg.Button(_t("generic.create"), key="create_backup_daily_task"),
            ],
            [
                sg.HorizontalSeparator(),
            ],
            [
                sg.Text(
                    _t("config_gui.create_housekeeping_scheduled_task_at"), size=(40, 1)
                ),
                sg.Input("22", key="scheduled_housekeeping_task_hour", size=(4, 1)),
                sg.Text(_t("generic.hours"), size=(10, 1)),
                sg.Input("00", key="scheduled_housekeeping_task_minute", size=(4, 1)),
                sg.Text(_t("generic.minutes"), size=(10, 1)),
                sg.Button(_t("generic.create"), key="create_housekeeping_daily_task"),
            ],
        ]

        tab_group_layout = [
            [
                sg.Tab(
                    _t("config_gui.repo_group_config"),
                    object_layout(),
                    key="--repo-group-config--",
                    expand_x=True,
                    expand_y=True,
                    pad=0,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.global_config"),
                    global_options_layout(),
                    key="--global-config--",
                    expand_x=True,
                    expand_y=True,
                    pad=0,
                )
            ],
            [
                sg.Tab(
                    _t("generic.scheduled_task"),
                    scheduled_task_col,
                    font="helvetica 16",
                    key="--tab-global-scheduled_task--",
                )
            ],
        ]

        _global_layout = [
            [
                sg.TabGroup(
                    tab_group_layout,
                    enable_events=True,
                    key="--configtabgroup--",
                    expand_x=True,
                    expand_y=True,
                    pad=0,
                )
            ],
            [
                sg.Push(),
                sg.Column(
                    buttons,
                ),
            ],
        ]
        return _global_layout

    right_click_menu = ["", [_t("config_gui.show_decrypted")]]
    window = sg.Window(
        title="Configuration",
        layout=config_layout(),
        # size=(800, 650),
        auto_size_text=True,
        auto_size_buttons=False,
        no_titlebar=False,
        grab_anywhere=True,
        keep_on_top=False,
        alpha_channel=1.0,
        default_button_element_size=(16, 1),
        right_click_menu=right_click_menu,
        finalize=True,
        enable_close_attempted_event=True,
    )

    # Init fresh config objects
    BAD_KEYS_FOUND_IN_CONFIG = set()
    backup_paths_tree = sg.TreeData()
    tags_tree = sg.TreeData()
    exclude_patterns_tree = sg.TreeData()
    exclude_files_tree = sg.TreeData()
    retention_policy_keep_tags_tree = sg.TreeData()
    retention_policy_apply_on_tags_tree = sg.TreeData()
    pre_exec_commands_tree = sg.TreeData()
    post_exec_commands_tree = sg.TreeData()
    global_prometheus_labels_tree = sg.TreeData()
    env_variables_tree = sg.TreeData()
    encrypted_env_variables_tree = sg.TreeData()

    # Update gui with first default object (repo or group)
    full_config = update_object_gui(full_config, unencrypted=False)
    update_global_gui(full_config, unencrypted=False)

    # These contain object name/type so on object change we can update the current object before loading new one
    current_object_type = None
    current_object_name = None

    if config_file:
        window.set_title(f"Configuration - {config_file}")

    while True:
        event, values = window.read()
        # Get object type for various delete operations
        object_type, object_name = get_object_from_combo(values["-OBJECT-SELECT-"])
        if not current_object_type and not current_object_name:
            current_object_type, current_object_name = object_type, object_name
        if event in (
            sg.WIN_CLOSED,
            sg.WIN_X_EVENT,
            "--CANCEL--",
            "-WINDOW CLOSE ATTEMPTED-",
        ):
            break

        if event in ("-OBJECT-SELECT-", "repo_group"):
            # Update full_config with current object before updating
            full_config = update_config_dict(
                full_config, current_object_type, current_object_name, values
            )
            current_object_type, current_object_name = object_type, object_name
            full_config = update_object_gui(
                full_config, current_object_type, current_object_name, unencrypted=False
            )
            update_global_gui(full_config, unencrypted=False)
            continue
        if event == "-OBJECT-DELETE-":
            object_type, object_name = get_object_from_combo(values["-OBJECT-SELECT-"])
            # if object_type == "repos" and object_name == "default":
            #    sg.popup_error(_t("config_gui.cannot_delete_default_repo"))
            #    continue
            # if object_type == "groups" and object_name == "default_group":
            #    sg.popup_error(_t("config_gui.cannot_delete_default_group"))
            #    continue
            full_config = delete_object(full_config, values["-OBJECT-SELECT-"])
            current_object_type, current_object_name = update_object_selector()
            continue
        if event == "-OBJECT-CREATE-":
            full_config, _object_type, _object_name = create_object(full_config)
            if _object_type and _object_name:
                object_type = _object_type
                object_name = _object_name
                update_object_selector(object_name, object_type)
                current_object_type = object_type
                current_object_name = object_name
            continue
        if event == "--SET-PERMISSIONS--":
            manager_password = configuration.get_manager_password(
                full_config, object_name
            )
            if not manager_password or ask_manager_password(manager_password):
                # We need to update full_config with current GUI values before using or modifying it
                full_config = update_config_dict(
                    full_config, current_object_type, current_object_name, values
                )
                full_config = set_permissions(
                    full_config,
                    object_type=current_object_type,
                    object_name=current_object_name,
                )
                full_config = update_object_gui(
                    full_config,
                    current_object_type,
                    current_object_name,
                    unencrypted=False,
                )
                update_global_gui(full_config, unencrypted=False)
            continue
        if event == "backup_opts.source_type":
            source_type = get_key_from_value(
                combo_boxes["backup_opts.source_type"],
                values["backup_opts.source_type"],
            )
            update_source_layout(source_type)
            continue
        if event in (
            "--ADD-PATHS-FILE--",
            "--ADD-PATHS-FOLDER--",
            "--ADD-PATHS-MANUALLY--",
            "--ADD-EXCLUDE-FILE--",
            "--ADD-EXCLUDE-FILE-MANUALLY--",
        ):
            tree = None
            node = None
            icon = None
            key = None
            if event in ("--ADD-PATHS-FILE--", "--ADD-EXCLUDE-FILE--"):
                if event == "--ADD-PATHS-FILE--":
                    key = "backup_opts.paths"
                    tree = backup_paths_tree
                if event == "--ADD-EXCLUDE-FILE--":
                    key = "backup_opts.exclude_files"
                    tree = exclude_files_tree
                node = values[event]
                icon, _ = get_icons_per_file(node)
            elif event == "--ADD-PATHS-FOLDER--":
                key = "backup_opts.paths"
                tree = backup_paths_tree
                node = values[event]
                icon, _ = get_icons_per_file(node)
            elif event == "--ADD-PATHS-MANUALLY--":
                key = "backup_opts.paths"
                tree = backup_paths_tree
                node = sg.PopupGetText(_t("generic.add_manually"))
                icon, _ = get_icons_per_file(node)
            elif event == "--ADD-EXCLUDE-FILE-MANUALLY--":
                key = "backup_opts.exclude_files"
                tree = exclude_files_tree
                node = sg.PopupGetText(_t("generic.add_manually"))
                icon = FILE_ICON
            if tree and node:
                # Check if node is ADD-PATH-FILES which can contain multiple elements separated by semicolon
                if key == "backup_opts.paths" and ";" in node:
                    for path in node.split(";"):
                        tree.insert("", path, path, path, icon=icon)
                else:
                    tree.insert("", node, node, node, icon=icon)
                window[key].update(values=tree)
            continue
        if event in (
            "--ADD-BACKUP-TAG--",
            "--ADD-EXCLUDE-PATTERN--",
            "--ADD-RETENTION-KEEP-TAG--",
            "--ADD-RETENTION-APPLY-ON-TAG--",
            "--ADD-PRE-EXEC-COMMAND--",
            "--ADD-POST-EXEC-COMMAND--",
            "--ADD-PROMETHEUS-LABEL--",
            "--ADD-ENV-VARIABLE--",
            "--ADD-ENCRYPTED-ENV-VARIABLE--",
            "--ADD-S3-IDENTITY--",
            "--ADD-AZURE-IDENTITY--",
            "--ADD-B2-IDENTITY--",
            "--ADD-GCS-IDENTITY--",
            "--REMOVE-PATHS--",
            "--REMOVE-BACKUP-TAG--",
            "--REMOVE-EXCLUDE-PATTERN--",
            "--REMOVE-EXCLUDE-FILE--",
            "--REMOVE-RETENTION-KEEP-TAG--",
            "--REMOVE-RETENTION-APPLY-ON-TAG--",
            "--REMOVE-PRE-EXEC-COMMAND--",
            "--REMOVE-POST-EXEC-COMMAND--",
            "--REMOVE-PROMETHEUS-LABEL--",
            "--REMOVE-ENV-VARIABLE--",
            "--REMOVE-ENCRYPTED-ENV-VARIABLE--",
        ):
            popup_text = None
            option_key = None
            if "PATHS" in event:
                option_key = "backup_opts.paths"
                tree = backup_paths_tree
            elif "BACKUP-TAG" in event:
                popup_text = _t("config_gui.enter_tag")
                tree = tags_tree
                option_key = "backup_opts.tags"
            elif "EXCLUDE-PATTERN" in event:
                popup_text = _t("config_gui.enter_pattern")
                tree = exclude_patterns_tree
                option_key = "backup_opts.exclude_patterns"
            elif "EXCLUDE-FILE" in event:
                popup_text = None
                tree = exclude_files_tree
                option_key = "backup_opts.exclude_files"
            elif "RETENTION-KEEP-TAG" in event:
                popup_text = _t("config_gui.enter_tag")
                tree = retention_policy_keep_tags_tree
                option_key = "repo_opts.retention_policy.keep_tags"
            elif "RETENTION-APPLY-ON-TAG" in event:
                popup_text = _t("config_gui.enter_tag")
                tree = retention_policy_apply_on_tags_tree
                option_key = "repo_opts.retention_policy.apply_on_tags"
            elif "PRE-EXEC-COMMAND" in event:
                popup_text = _t("config_gui.enter_command")
                tree = pre_exec_commands_tree
                option_key = "backup_opts.pre_exec_commands"
            elif "POST-EXEC-COMMAND" in event:
                popup_text = _t("config_gui.enter_command")
                tree = post_exec_commands_tree
                option_key = "backup_opts.post_exec_commands"
            elif "PROMETHEUS-LABEL" in event:
                popup_text = _t("config_gui.enter_label")
                tree = global_prometheus_labels_tree
                option_key = "global_prometheus.additional_labels"
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
                    var_name = sg.PopupGetText(_t("config_gui.enter_var_name"))
                    var_value = sg.PopupGetText(_t("config_gui.enter_var_value"))
                    if var_name and var_value:
                        if tree.tree_dict.get(var_name):
                            tree.delete(var_name)
                        tree.insert("", var_name, var_name, [var_value], icon=icon)
                elif "PROMETHEUS-LABEL" in event:
                    var_name = sg.PopupGetText(_t("config_gui.enter_label_name"))
                    var_value = sg.PopupGetText(_t("config_gui.enter_label_value"))
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
                        sg.popup_error("Bad identity given")
                        break
                    for var_name in var_names:
                        var_value = sg.PopupGetText(var_name)
                        if var_value:
                            if tree.tree_dict.get(var_name):
                                tree.delete(var_name)
                            tree.insert("", var_name, var_name, [var_value], icon=icon)
                        else:
                            sg.Popup_error(_t("config_gui.value_cannot_be_empty"))
                            break
                else:
                    node = sg.PopupGetText(popup_text)
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
                        sg.PopupError(
                            _t("config_gui.cannot_remove_group_inherited_settings"),
                            keep_on_top=True,
                        )
                        continue
                    tree.delete(key)
            window[option_key].Update(values=tree)
            continue
        if event == "--TEST-EMAIL--":
            repo_config, _ = configuration.get_repo_config(
                full_config, object_name, eval_variables=False
            )
            if send_metrics_mail(
                repo_config=repo_config,
                operation="test_email",
                restic_result=None,
                operation_success=True,
                backup_too_small=False,
                exec_state=0,
                date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            ):
                sg.Popup(_t("config_gui.test_email_success"), keep_on_top=True)
            else:
                sg.Popup(_t("config_gui.test_email_failure"), keep_on_top=True)
            # WIP
            continue
        if event == "--ACCEPT--":
            if object_type != "groups" and not values["repo_uri"]:
                sg.PopupError(
                    _t("config_gui.repo_uri_cannot_be_empty"), keep_on_top=True
                )
                continue
            full_config = update_config_dict(
                full_config, current_object_type, current_object_name, values
            )
            result = configuration.save_config(config_file, full_config)
            if result:
                sg.Popup(_t("config_gui.configuration_saved"), keep_on_top=True)
                break
            sg.PopupError(_t("config_gui.cannot_save_configuration"), keep_on_top=True)
            continue
        if event == _t("config_gui.show_decrypted"):
            manager_password = configuration.get_manager_password(
                full_config, object_name
            )
            # NPF-SEC-00009
            env_manager_password = os.environ.get("NPBACKUP_MANAGER_PASSWORD", None)
            if not manager_password:
                sg.PopupError(
                    _t("config_gui.no_manager_password_defined"), keep_on_top=True
                )
                continue
            if (
                env_manager_password and env_manager_password == manager_password
            ) or ask_manager_password(manager_password):
                full_config = update_object_gui(
                    full_config,
                    current_object_type,
                    current_object_name,
                    unencrypted=True,
                )
                update_global_gui(full_config, unencrypted=True)
            continue
        if event in (
            "create_backup_interval_task",
            "create_backup_daily_task",
            "create_housekeeping_daily_task",
        ):
            object_type, object_name = get_object_from_combo(
                values["-OBJECT-SELECT-TASKS-"]
            )
            if object_type == "groups":
                task_repo_group = object_name
                task_repo_name = None
            else:
                task_repo_name = object_name
                task_repo_group = None

            try:
                interval = None
                hour = None
                minute = None
                if event == "create_housekeeping_daily_task":
                    task_type = "housekeeping"
                    hour = values["scheduled_housekeeping_task_hour"]
                    minute = values["scheduled_housekeeping_task_minute"]
                else:
                    task_type = "backup"
                    if event == "create_backup_interval_task":
                        interval = values["scheduled_backup_task_interval"]
                    else:
                        hour = values["scheduled_backup_task_hour"]
                        minute = values["scheduled_backup_task_minute"]

                result = create_scheduled_task(
                    config_file=config_file,
                    task_type=task_type,
                    repo=task_repo_name,
                    group=task_repo_group,
                    interval_minutes=interval,
                    hour=hour,
                    minute=minute,
                )
                if result:
                    sg.Popup(
                        _t("config_gui.scheduled_task_creation_success"),
                        keep_on_top=True,
                    )
                else:
                    sg.PopupError(
                        _t("config_gui.scheduled_task_creation_failure"),
                        keep_on_top=True,
                    )
            except ValueError as exc:
                sg.PopupError(
                    _t("config_gui.scheduled_task_creation_failure") + f": {exc}",
                    keep_on_top=True,
                )
            continue
        if event == "repo_uri":
            for cloud_provider in ["s3", "azure", "b2", "gs"]:
                if values["repo_uri"].startswith(cloud_provider + ":"):
                    window["repo_uri_cloud_hint"].Update(visible=True)
                    break
                else:
                    window["repo_uri_cloud_hint"].Update(visible=False)

    # Closing this window takes ages
    window.hide()
    quick_close_simplegui_window(window)
    return full_config
