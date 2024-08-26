#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.config"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024072301"


from typing import List, Tuple
import os
import re
import pathlib
from logging import getLogger
import FreeSimpleGUI as sg
import textwrap
from ruamel.yaml.comments import CommentedMap
import npbackup.configuration as configuration
from ofunctions.misc import get_key_from_value, BytesConverter
from npbackup.core.i18n_helper import _t
from npbackup.__version__ import IS_COMPILED
from npbackup.path_helper import CURRENT_DIR
from npbackup.__debug__ import _DEBUG, fmt_json
from resources.customization import (
    INHERITED_ICON,
    NON_INHERITED_ICON,
    FILE_ICON,
    FOLDER_ICON,
    INHERITED_FILE_ICON,
    INHERITED_FOLDER_ICON,
    TREE_ICON,
    INHERITED_TREE_ICON,
)
from npbackup.task import create_scheduled_task

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
        pass


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

    # Don't let SimpleGUI handle key errros since we might have new keys in config file
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
        },
        "backup_opts.priority": {
            "low": _t("config_gui.low"),
            "normal": _t("config_gui.normal"),
            "high": _t("config_gui.high"),
        },
        "permissions": {
            "backup": _t("config_gui.backup_perms"),
            "restore": _t("config_gui.restore_perms"),
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
                if object_name is None or object_name == "":
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
            update_object_gui(full_config, object_type, object_name, unencrypted=False)
            update_global_gui(full_config, unencrypted=False)
        return full_config, object_type, object_name

    def delete_object(full_config: dict, full_object_name: str) -> dict:
        object_type, object_name = get_object_from_combo(full_object_name)
        result = sg.PopupYesNo(
            _t("config_gui.are_you_sure_to_delete") + f" {object_type} {object_name} ?"
        )
        if result:
            full_config.d(f"{object_type}.{object_name}")
            update_object_gui(full_config, None, unencrypted=False)
            update_global_gui(full_config, unencrypted=False)
        return full_config

    def update_object_selector(
        object_name: str = None, object_type: str = None
    ) -> None:
        object_list = get_objects()
        if not object_name or not object_type:
            object = object_list[0]
        else:
            # We need to remove the "s" and the end if we want our comobox name to be usable later
            object = f"{object_type.rstrip('s').capitalize()}: {object_name}"

        window["-OBJECT-SELECT-"].Update(values=object_list)
        window["-OBJECT-SELECT-"].Update(value=object)

    def get_object_from_combo(combo_value: str) -> Tuple[str, str]:
        """
        Extracts selected object from combobox
        Returns object type and name
        """
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
                f"Could not obtain object_type and object_name from {combo_value}"
            )

        return object_type, object_name

    def update_gui_values(key, value, inherited, object_type, unencrypted):
        """
        Update gui values depending on their type
        This not called directly, but rather from update_object_gui which calls iter_over_config which calls this function
        """
        nonlocal backup_paths_tree
        nonlocal tags_tree
        nonlocal exclude_files_tree
        nonlocal exclude_patterns_tree
        nonlocal pre_exec_commands_tree
        nonlocal post_exec_commands_tree
        nonlocal global_prometheus_labels_tree
        nonlocal env_variables_tree
        nonlocal encrypted_env_variables_tree

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
                "update_manager_password",
            ) or key.startswith("prometheus.additional_labels"):
                return
            if key == "permissions":
                window["current_permissions"].Update(combo_boxes["permissions"][value])
                return
            if key == "manager_password":
                if value:
                    window["manager_password_set"].Update(_t("generic.yes"))
                else:
                    window["manager_password_set"].Update(_t("generic.no"))
                return

            # NPF-SEC-00009
            # Don't show sensible info unless unencrypted requested
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
                        window[key].Update(value=value)
                return

            # Update tree objects
            if key == "backup_opts.paths":
                if value:
                    for val in value:
                        if pathlib.Path(val).is_dir():
                            if object_type != "groups" and inherited[val]:
                                icon = INHERITED_FOLDER_ICON
                            else:
                                icon = FOLDER_ICON
                        else:
                            if object_type != "groups" and inherited[val]:
                                icon = INHERITED_FILE_ICON
                            else:
                                icon = FILE_ICON
                        backup_paths_tree.insert("", val, val, val, icon=icon)
                    window["backup_opts.paths"].update(values=backup_paths_tree)
                return
            elif key in (
                "backup_opts.tags",
                "backup_opts.pre_exec_commands",
                "backup_opts.post_exec_commands",
                "backup_opts.exclude_files",
                "backup_opts.exclude_patterns",
                "repo_opts.retention_policy.tags",
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
                elif key == "repo_opts.retention_policy.tags":
                    tree = retention_policy_tags_tree
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
            ):
                # We don't need a better split here since the value string comes from BytesConverter
                # which always provides "0 MiB" or "5 KB" etc.
                if value is not None:
                    unit = None
                    try:
                        matches = re.search(r"(\d+(?:\.\d+)?)\s*(\w*)", value)
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
                return

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
            logger.error(f"Key {key} has no GUI equivalent")
            logger.debug("Trace:", exc_info=True)
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
    ):
        """
        Reload current object configuration settings to GUI
        """
        nonlocal backup_paths_tree
        nonlocal tags_tree
        nonlocal exclude_files_tree
        nonlocal exclude_patterns_tree
        nonlocal retention_policy_tags_tree
        nonlocal pre_exec_commands_tree
        nonlocal post_exec_commands_tree
        nonlocal env_variables_tree
        nonlocal encrypted_env_variables_tree

        # Load fist available repo or group if none given
        if not object_name:
            object_type, object_name = get_object_from_combo(get_objects()[0])

        # First we need to clear the whole GUI to reload new values
        for key in window.AllKeysDict:
            # We only clear config keys, wihch have '.' separator
            if "." in str(key) and not "inherited" in str(key):
                if isinstance(window[key], sg.Tree):
                    window[key].Update(sg.TreeData())
                else:
                    window[key]("")

        # We also need to clear tree objects
        backup_paths_tree = sg.TreeData()
        tags_tree = sg.TreeData()
        exclude_patterns_tree = sg.TreeData()
        exclude_files_tree = sg.TreeData()
        retention_policy_tags_tree = sg.TreeData()
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

        else:
            object_config = None
            config_inheritance = None
            logger.error(f"Bogus object {object_type}.{object_name}")

        # Now let's iter over the whole config object and update keys accordingly
        iter_over_config(
            object_config, config_inheritance, object_type, unencrypted, None
        )

    def update_global_gui(full_config, unencrypted: bool = False):
        nonlocal global_prometheus_labels_tree

        global_config = CommentedMap()

        global_prometheus_labels_tree = sg.TreeData()

        # Only update global options gui with identified global keys
        for key in full_config.keys():
            if key in ("identity", "global_prometheus", "global_options"):
                global_config.s(key, full_config.g(key))
        iter_over_config(global_config, None, "group", unencrypted, None)

    def update_config_dict(full_config, object_type, object_name, values: dict) -> dict:
        """
        Update full_config with keys from GUI
        keys should always have form section.name or section.subsection.name
        """
        if object_type == "repos":
            object_group = full_config.g(f"{object_type}.{object_name}.repo_group")
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
            "repo_opts.retention_policy.tags",
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

        for key, value in values.items():
            # Don't update placeholders ;)
            if value == ENCRYPTED_DATA_PLACEHOLDER:
                continue
            if not isinstance(key, str) or (
                isinstance(key, str)
                and (not "." in key and not key in ("repo_uri", "repo_group"))
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
            ):
                value = f"{value} {values[f'{key}_unit']}"

            # Don't update unit keys
            if key in (
                "backup_opts.minimum_backup_size_error_unit",
                "backup_opts.exclude_files_larger_than_unit",
                "repo_opts.upload_speed_unit",
                "repo_opts.download_speed_unit",
            ):
                continue

            # Don't bother with inheritance on global options and host identity
            if (
                key.startswith("global_options")
                or key.startswith("identity")
                or key.startswith("global_prometheus")
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
                    # check if value is inherited from group
                    if full_config.g(inheritance_key) == value:
                        continue
                    # we also need to compare inherited values with current values for BytesConverter values
                    if key in (
                        "backup_opts.minimum_backup_size_error",
                        "backup_opts.exclude_files_larger_than",
                        "repo_opts.upload_speed",
                        "repo_opts.download_speed",
                    ):
                        if (
                            full_config.g(inheritance_key) is not None
                            and value is not None
                            and (
                                BytesConverter(full_config.g(inheritance_key)).bytes
                                == BytesConverter(value).bytes
                            )
                        ):
                            continue

            # Don't bother to update empty strings, empty lists and None
            if not current_value and not value:
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
                    manager_password,
                    key="-MANAGER-PASSWORD-",
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

        window = sg.Window(_t("config_gui.permissions"), layout, keep_on_top=True)
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
                # Transform translet permission value into key
                permission = get_key_from_value(
                    combo_boxes["permissions"], values["permissions"]
                )
                full_config.s(f"{object_type}.{object_name}.permissions", permission)
                full_config.s(
                    f"{object_type}.{object_name}.manager_password",
                    values["-MANAGER-PASSWORD-"],
                )
                full_config.s(
                    f"{object_type}.{object_name}.update_manager_password", True
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
                ),
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
                sg.Input(visible=False, key="--ADD-PATHS-FILE--", enable_events=True),
                sg.FilesBrowse(_t("generic.add_files"), target="--ADD-PATHS-FILE--"),
                sg.Input(visible=False, key="--ADD-PATHS-FOLDER--", enable_events=True),
                sg.FolderBrowse(
                    _t("generic.add_folder"), target="--ADD-PATHS-FOLDER--"
                ),
                sg.Button(_t("generic.add_manually"), key="--ADD-PATHS-MANUALLY--"),
                sg.Button(_t("generic.remove_selected"), key="--REMOVE-PATHS--"),
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
                sg.Input(key="repo_uri", size=(95, 1)),
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
            [sg.Button(_t("config_gui.set_permissions"), key="--SET-PERMISSIONS--")],
            [
                sg.Text(_t("config_gui.repo_group"), size=(40, 1)),
                sg.Image(NON_INHERITED_ICON, pad=1),
                sg.Combo(
                    values=configuration.get_group_list(full_config), key="repo_group"
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
            [sg.HorizontalSeparator()],
            [
                sg.Column(
                    [
                        [sg.Button("+", key="--ADD-RETENTION-TAG--", size=(3, 1))],
                        [sg.Button("-", key="--REMOVE-RETENTION-TAG--", size=(3, 1))],
                    ],
                    pad=0,
                ),
                sg.Column(
                    [
                        [
                            sg.Tree(
                                sg.TreeData(),
                                key="repo_opts.retention_policy.tags",
                                headings=[],
                                col0_heading=_t("config_gui.keep_tags"),
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
                sg.Text(
                    _t("config_gui.suggested_encrypted_env_variables"), size=(40, 1)
                ),
            ],
            [
                sg.Multiline(
                    "\
AWS:                  AWS_ACCESS_KEY_ID  AWS_SECRET_ACCESS_KEY\n\
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
        Returns layout for global options that can't be overrided by group / repo settings
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
                sg.Text(_t("config_gui.instance"), size=(40, 1)),
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
                    _t("config_gui.create_object"), key="-OBJECT-CREATE-", size=(28, 1)
                ),
                sg.Button(
                    _t("config_gui.delete_object"), key="-OBJECT-DELETE-", size=(28, 1)
                ),
                sg.Button(_t("generic.cancel"), key="--CANCEL--", size=(13, 1)),
                sg.Button(_t("generic.accept"), key="--ACCEPT--", size=(13, 1)),
            ]
        ]

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
                sg.Text(_t("config_gui.create_backup_scheduled_task_every"), size=(40, 1)),
                sg.Input(key="scheduled_task_interval", size=(4, 1)),
                sg.Text(_t("generic.minutes"), size=(10, 1)),
                sg.Button(_t("generic.create"), key="create_backup_interval_task"),
            ],
            [
                sg.Text(_t("config_gui.create_backup_scheduled_task_at"), size=(40, 1)),
                sg.Input(key="scheduled_task_hour", size=(4, 1)),
                sg.Text(_t("generic.hours"), size=(10, 1)),
                sg.Input(key="scheduled_task_minute", size=(4, 1)),
                sg.Text(_t("generic.minutes"), size=(10, 1)),
                sg.Button(_t("generic.create"), key="create_backup_daily_task"),
            ],
            [
                sg.HorizontalSeparator(),
            ],
            [
                sg.Text(_t("config_gui.create_housekeeping_scheduled_task_at"), size=(40, 1)),
                sg.Input(key="scheduled_task_hour", size=(4, 1)),
                sg.Text(_t("generic.hours"), size=(10, 1)),
                sg.Input(key="scheduled_task_minute", size=(4, 1)),
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
        "Configuration",
        config_layout(),
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

    backup_paths_tree = sg.TreeData()
    tags_tree = sg.TreeData()
    exclude_patterns_tree = sg.TreeData()
    exclude_files_tree = sg.TreeData()
    retention_policy_tags_tree = sg.TreeData()
    pre_exec_commands_tree = sg.TreeData()
    post_exec_commands_tree = sg.TreeData()
    global_prometheus_labels_tree = sg.TreeData()
    env_variables_tree = sg.TreeData()
    encrypted_env_variables_tree = sg.TreeData()

    # Update gui with first default object (repo or group)
    update_object_gui(full_config, unencrypted=False)
    update_global_gui(full_config, unencrypted=False)

    # These contain object name/type so on object change we can update the current object before loading new one
    current_object_type = None
    current_object_name = None

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

        if event == "-OBJECT-SELECT-":
            # Update full_config with current object before updating
            full_config = update_config_dict(
                full_config, current_object_type, current_object_name, values
            )
            current_object_type, current_object_name = object_type, object_name
            update_object_gui(
                full_config, current_object_type, current_object_name, unencrypted=False
            )
            update_global_gui(full_config, unencrypted=False)
            continue
        if event == "-OBJECT-DELETE-":
            full_config = delete_object(full_config, values["-OBJECT-SELECT-"])
            update_object_selector()
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
                # We need to update full_config with current GUI values before using modifying it
                full_config = update_config_dict(
                    full_config, current_object_type, current_object_name, values
                )
                full_config = set_permissions(
                    full_config,
                    object_type=current_object_type,
                    object_name=current_object_name,
                )
                update_object_gui(
                    full_config,
                    current_object_type,
                    current_object_name,
                    unencrypted=False,
                )
                update_global_gui(full_config, unencrypted=False)
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
                icon = FILE_ICON
            elif event == "--ADD-PATHS-FOLDER--":
                key = "backup_opts.paths"
                tree = backup_paths_tree
                node = values[event]
                icon = FOLDER_ICON
            elif event == "--ADD-PATHS-MANUALLY--":
                key = "backup_opts.paths"
                tree = backup_paths_tree
                node = sg.PopupGetText(_t("generic.add_manually"))
                if node and os.path.exists(node) and os.path.isdir(node):
                    icon = FOLDER_ICON
                else:
                    icon = FILE_ICON
            elif event == "--ADD-EXCLUDE-FILE-MANUALLY--":
                key = "backup_opts.exclude_files"
                tree = exclude_files_tree
                node = sg.PopupGetText(_t("generic.add_manually"))
                icon = FILE_ICON
            if tree and node:
                tree.insert("", node, node, node, icon=icon)
                window[key].update(values=tree)
            continue
        if event in (
            "--ADD-BACKUP-TAG--",
            "--ADD-EXCLUDE-PATTERN--",
            "--ADD-RETENTION-TAG--",
            "--ADD-PRE-EXEC-COMMAND--",
            "--ADD-POST-EXEC-COMMAND--",
            "--ADD-PROMETHEUS-LABEL--",
            "--ADD-ENV-VARIABLE--",
            "--ADD-ENCRYPTED-ENV-VARIABLE--",
            "--REMOVE-PATHS--",
            "--REMOVE-BACKUP-TAG--",
            "--REMOVE-EXCLUDE-PATTERN--",
            "--REMOVE-EXCLUDE-FILE--",
            "--REMOVE-RETENTION-TAG--",
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
            elif "RETENTION-TAG" in event:
                popup_text = _t("config_gui.enter_tag")
                tree = retention_policy_tags_tree
                option_key = "repo_opts.retention_policy.tags"
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
            elif "ENCRYPTED-ENV-VARIABLE" in event:
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
                        tree.insert("", var_name, var_name, [var_value], icon=icon)
                elif "PROMETHEUS-LABEL" in event:
                    var_name = sg.PopupGetText(_t("config_gui.enter_label_name"))
                    var_value = sg.PopupGetText(_t("config_gui.enter_label_value"))
                    if var_name and var_value:
                        tree.insert("", var_name, var_name, [var_value], icon=icon)
                else:
                    node = sg.PopupGetText(popup_text)
                    if node:
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
                logger.info("Configuration saved successfully.")
                break
            sg.PopupError(_t("config_gui.cannot_save_configuration"), keep_on_top=True)
            logger.info("Could not save configuration")
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
                update_object_gui(
                    full_config,
                    current_object_type,
                    current_object_name,
                    unencrypted=True,
                )
                update_global_gui(full_config, unencrypted=True)
            continue
        if event in ("create_backup_interval_task", "create_backup_daily_task", "create_housekeeping_daily_task"):
            try:
                if event == "create_housekeeping_daily_task":
                    type = "housekeeping"
                else:
                    type = "backup"
                result = create_scheduled_task(
                    config_file,
                    type=type,
                    values["scheduled_task_interval"],
                    values["scheduled_task_hour"],
                    values["scheduled_task_minute"],
                )
                if result:
                    sg.Popup(_t("config_gui.scheduled_task_creation_success"))
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
    window.close()
    return full_config
