#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.config"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024041501"


from typing import List, Tuple
import os
import pathlib
from logging import getLogger
import PySimpleGUI as sg
import textwrap
from ruamel.yaml.comments import CommentedMap
import npbackup.configuration as configuration
from ofunctions.misc import get_key_from_value
from npbackup.core.i18n_helper import _t
from npbackup.path_helper import CURRENT_EXECUTABLE
from npbackup.customization import (
    INHERITED_ICON,
    NON_INHERITED_ICON,
    FILE_ICON,
    FOLDER_ICON,
    INHERITED_FILE_ICON,
    INHERITED_FOLDER_ICON,
    TREE_ICON,
    INHERITED_TREE_ICON,
)

if os.name == "nt":
    from npbackup.windows.task import create_scheduled_task

logger = getLogger()


# Monkeypatching PySimpleGUI
# @PySimpleGUI: Why is there no delete method for TreeData ?
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


def ask_manager_password(manager_password: str) -> bool:
    if manager_password:
        if sg.PopupGetText(
            _t("config_gui.set_manager_password"), password_char="*"
        ) == str(manager_password):
            return True
        sg.PopupError(_t("config_gui.wrong_password"))
        return False
    return True


def config_gui(full_config: dict, config_file: str):
    logger.info("Launching configuration GUI")

    # Don't let PySimpleGUI handle key errros since we might have new keys in config file
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

    ENCRYPTED_DATA_PLACEHOLDER = "<{}>".format(_t("config_gui.encrypted_data"))

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
                object_type = values["-OBJECT-TYPE-"]
                object_name = values["-OBJECT-NAME-"]
                if object_type == "repo":
                    if full_config.g(f"repos.{object_name}"):
                        sg.PopupError(
                            _t("config_gui.repo_already_exists"), keep_on_top=True
                        )
                        continue
                    full_config.s(f"repos.{object_name}", CommentedMap())
                elif object_type == "group":
                    if full_config.g(f"groups.{object_name}"):
                        sg.PopupError(
                            _t("config_gui.group_already_exists"), keep_on_top=True
                        )
                        continue
                    full_config.s(f"groups.{object_name}", CommentedMap())
                else:
                    raise ValueError("Bogus object type given")
        window.close()
        update_object_gui(None, unencrypted=False)
        return full_config

    def delete_object(full_config: dict, object_name: str) -> dict:
        object_type, object_name = get_object_from_combo(object_name)
        result = sg.PopupYesNo(
            _t("config_gui.are_you_sure_to_delete") + f" {object_type} {object_name} ?"
        )
        if result:
            full_config.d(f"{object_type}s.{object_name}")
            update_object_gui(None, unencrypted=False)
        return full_config

    def update_object_selector() -> None:
        objects = get_objects()
        window["-OBJECT-SELECT-"].Update(objects)
        window["-OBJECT-SELECT-"].Update(value=objects[0])

    def get_object_from_combo(combo_value: str) -> Tuple[str, str]:
        """
        Extracts selected object from combobox
        Returns object type and name
        """

        if combo_value.startswith("Repo: "):
            object_type = "repo"
            object_name = combo_value[len("Repo: ") :]
        elif combo_value.startswith("Group: "):
            object_type = "group"
            object_name = combo_value[len("Group: ") :]
        return object_type, object_name

    def update_gui_values(key, value, inherited, object_type, unencrypted):
        """
        Update gui values depending on their type
        """
        nonlocal backup_paths_tree
        nonlocal tags_tree
        nonlocal exclude_files_tree
        nonlocal exclude_patterns_tree
        nonlocal pre_exec_commands_tree
        nonlocal post_exec_commands_tree
        nonlocal prometheus_labels_tree
        nonlocal env_variables_tree
        nonlocal encrypted_env_variables_tree

        if key in ("repo_uri", "repo_group"):
            if object_type == "group":
                window[key].Disabled = True
            else:
                window[key].Disabled = False

        try:
            # Don't bother to update repo name
            # Also permissions / manager_password are in a separate gui
            if key in (
                "name",
                "permissions",
                "manager_password",
                "__current_manager_password",
                "is_protected",
            ):
                return
            # Don't show sensible info unless unencrypted requested
            if not unencrypted:
                # Use last part of key only
                if key in configuration.ENCRYPTED_OPTIONS:
                    try:
                        if value is None or value == "":
                            return
                        if isinstance(value, dict):
                            for k in value.keys():
                                value[k] = ENCRYPTED_DATA_PLACEHOLDER
                        elif not str(value).startswith(configuration.ID_STRING):
                            value = ENCRYPTED_DATA_PLACEHOLDER
                    except (KeyError, TypeError):
                        pass

            # Update tree objects
            if key == "backup_opts.paths":
                for val in value:
                    if pathlib.Path(val).is_dir():
                        if object_type != "group" and inherited[val]:
                            icon = INHERITED_FOLDER_ICON
                        else:
                            icon = FOLDER_ICON
                    else:
                        if object_type != "group" and inherited[val]:
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
                "prometheus.additional_labels",
                "env.env_variables",
                "env.encrypted_env_variables",
            ):
                if key == "backup_opts.tags":
                    tree = tags_tree
                if key == "backup_opts.pre_exec_commands":
                    tree = pre_exec_commands_tree
                if key == "backup_opts.post_exec_commands":
                    tree = post_exec_commands_tree
                if key == "backup_opts.exclude_files":
                    tree = exclude_files_tree
                if key == "backup_opts.exclude_patterns":
                    tree = exclude_patterns_tree
                if key == "prometheus.additional_labels":
                    tree = prometheus_labels_tree
                if key == "env.env_variables":
                    tree = env_variables_tree
                if key == "env.encrypted_env_variables":
                    tree = encrypted_env_variables_tree

                if isinstance(value, dict):
                    for var_name, var_value in value.items():
                        if object_type != "group" and inherited[var_name]:
                            icon = INHERITED_TREE_ICON
                        else:
                            icon = TREE_ICON
                        tree.insert("", var_name, var_name, var_value, icon=icon)
                else:
                    for val in value:
                        if isinstance(val, dict):
                            for var_name, var_value in val.items():
                                if object_type != "group" and inherited[var_name]:
                                    icon = INHERITED_TREE_ICON
                                else:
                                    icon = TREE_ICON
                                tree.insert(
                                    "", var_name, var_name, var_value, icon=icon
                                )
                        else:
                            if object_type != "group" and inherited[val]:
                                icon = INHERITED_TREE_ICON
                            else:
                                icon = TREE_ICON
                            tree.insert("", val, val, val, icon=icon)
                window[key].Update(values=tree)
                return

            # Update units into separate value and unit combobox
            if key in (
                "backup_opts.minimum_backup_size_error",
                "backup_opts.exclude_files_larger_than",
                "repo_opts.upload_speed",
                "repo_opts.download_speed",
            ):
                value, unit = value.split(" ")
                window[f"{key}_unit"].Update(unit)

            if isinstance(value, list):
                value = "\n".join(value)

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
            logger.error(f"No GUI equivalent for key {key}.")
            logger.debug("Trace:", exc_info=True)
        except TypeError as exc:
            logger.error(f"Error: {exc} for key {key}.")
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

    def update_object_gui(object_name=None, unencrypted=False):
        nonlocal backup_paths_tree
        nonlocal tags_tree
        nonlocal exclude_files_tree
        nonlocal exclude_patterns_tree
        nonlocal pre_exec_commands_tree
        nonlocal post_exec_commands_tree
        nonlocal prometheus_labels_tree
        nonlocal env_variables_tree
        nonlocal encrypted_env_variables_tree

        # Load fist available repo or group if none given
        if not object_name:
            object_name = get_objects()[0]

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
        pre_exec_commands_tree = sg.TreeData()
        post_exec_commands_tree = sg.TreeData()
        prometheus_labels_tree = sg.TreeData()
        env_variables_tree = sg.TreeData()
        encrypted_env_variables_tree = sg.TreeData()

        object_type, object_name = get_object_from_combo(object_name)

        if object_type == "repo":
            object_config, config_inheritance = configuration.get_repo_config(
                full_config, object_name, eval_variables=False
            )

            # Enable settings only valid for repos
            window["repo_uri"].Update(visible=True)
            window["--SET-PERMISSIONS--"].Update(visible=True)

        if object_type == "group":
            object_config = configuration.get_group_config(
                full_config, object_name, eval_variables=False
            )
            config_inheritance = None

            # Disable settings only valid for repos
            window["repo_uri"].Update(visible=False)
            window["--SET-PERMISSIONS--"].Update(visible=False)

        # Now let's iter over the whole config object and update keys accordingly
        iter_over_config(
            object_config, config_inheritance, object_type, unencrypted, None
        )

    def update_global_gui(full_config, unencrypted: bool = False):
        global_config = CommentedMap()

        # Only update global options gui with identified global keys
        for key in full_config.keys():
            if key in ("identity", "global_options"):
                global_config.s(key, full_config.g(key))
        iter_over_config(global_config, None, "group", unencrypted, None)

    def update_config_dict(full_config, object_type, object_name, values: dict) -> dict:
        """
        Update full_config with keys from GUI
        keys should always have form section.name or section.subsection.name
        """
        if object_type == "repo":
            object_group = full_config.g(f"repos.{object_name}.repo_group")
        else:
            object_group = None
        for key, value in values.items():
            # Don't update placeholders ;)
            # TODO exclude encrypted env vars
            if value == ENCRYPTED_DATA_PLACEHOLDER:
                continue
            if not isinstance(key, str) or (isinstance(key, str) and not "." in key):
                # Don't bother with keys that don't contain with "." since they're not in the YAML config file
                # but are most probably for GUI events
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
                    except ValueError:
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
            if key.startswith("global_options") or key.startswith("identity"):
                active_object_key = f"{key}"
                current_value = full_config.g(active_object_key)
            else:
                active_object_key = f"{object_type}s.{object_name}.{key}"
                current_value = full_config.g(active_object_key)

                if object_group:
                    inheritance_key = f"groups.{object_group}.{key}"
                    # If object is a list, check which values are inherited from group and remove them
                    if isinstance(value, list):  # WIP # TODO
                        inheritance_list = full_config.g(inheritance_key)
                        if inheritance_list:
                            for entry in inheritance_list:
                                if entry in value:
                                    value.remove(entry)
                    # check if value is inherited from group
                    if full_config.g(inheritance_key) == value:
                        continue

                    if object_group:
                        inherited = full_config.g(inheritance_key)
                    else:
                        inherited = False

            # Don't bother to update empty strings, empty lists and None
            if not current_value and not value:
                continue
            # Don't bother to update values which haven't changed
            if current_value == value:
                continue

            # Finally, update the config dictionary
            if object_type == "group":
                print(f"UPDATING {active_object_key} curr={current_value} new={value}")
            else:
                print(
                    f"UPDATING {active_object_key} curr={current_value} inherited={inherited} new={value}"
                )
            full_config.s(active_object_key, value)
        return full_config

    def set_permissions(full_config: dict, object_name: str) -> dict:
        """
        Sets repo wide repo_uri / password / permissions
        """
        object_type, object_name = get_object_from_combo(object_name)
        if object_type == "group":
            sg.PopupError(_t("config_gui.permissions_only_for_repos"))
            return full_config
        repo_config, _ = configuration.get_repo_config(
            full_config, object_name, eval_variables=False
        )
        permissions = list(combo_boxes["permissions"].values())
        default_perm = repo_config.g("permissions")
        if not default_perm:
            default_perm = permissions[-1]
        manager_password = repo_config.g("manager_password")

        layout = [
            [
                sg.Text(_t("config_gui.permissions"), size=(40, 1)),
                sg.Combo(permissions, default_value=default_perm, key="permissions"),
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
                # sg.Button(_t("generic.change"), key="--CHANGE-MANAGER-PASSWORD--") # TODO
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
                # TODO: Check password strength in a better way than this ^^
                if len(values["-MANAGER-PASSWORD-"]) < 8:
                    sg.PopupError(
                        _t("config_gui.manager_password_too_short"), keep_on_top=True
                    )
                    continue
                if not values["permissions"] in permissions:
                    sg.PopupError(_t("generic.bogus_data_given"), keep_on_top=True)
                    continue
                # Transform translet permission value into key
                permission = get_key_from_value(
                    combo_boxes["permissions"], values["permissions"]
                )
                repo_config.s("permissions", permission)
                repo_config.s("manager_password", values["-MANAGER-PASSWORD-"])
                break
        window.close()
        full_config.s(f"repos.{object_name}", repo_config)
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
                                    [sg.Button("+", key="--ADD-TAG--", size=(3, 1))],
                                    [sg.Button("-", key="--REMOVE-TAG--", size=(3, 1))],
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
                                key="inherited.backup_opts.fs_snapshot",
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
                sg.Text(
                    _t("config_gui.exclude_files_larger_than"),
                    size=(40, 1),
                ),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.exclude_files_larger_than",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
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
                    key="inherited.backup_opts.execute_even_on_backup_error",
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
                sg.Text(_t("config_gui.backup_repo_password_command"), size=(40, 1)),
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
            [sg.Button(_t("config_gui.set_permissions"), key="--SET-PERMISSIONS--")],
            [
                sg.Text(_t("config_gui.repo_group"), size=(40, 1)),
                sg.Combo(values=[], key="repo_group"),  # TODO
            ],
            [
                sg.Text(
                    _t("config_gui.minimum_backup_age"),
                    size=(40, 2),
                ),
                sg.Input(key="repo_opts.minimum_backup_age", size=(8, 1)),
                sg.Text(_t("generic.minutes")),
            ],
            [
                sg.Text(_t("config_gui.upload_speed"), size=(40, 1)),
                sg.Input(key="repo_opts.upload_speed", size=(8, 1)),
                sg.Combo(
                    byte_units,
                    default_value=byte_units[3],
                    key="repo_opts.upload_speed_unit",
                ),
            ],
            [
                sg.Text(_t("config_gui.download_speed"), size=(40, 1)),
                sg.Input(key="repo_opts.download_speed", size=(8, 1)),
                sg.Combo(
                    byte_units,
                    default_value=byte_units[3],
                    key="repo_opts.download_speed_unit",
                ),
            ],
            [
                sg.Text(_t("config_gui.backend_connections"), size=(40, 1)),
                sg.Input(key="repo_opts.backend_connections", size=(8, 1)),
            ],
            [sg.HorizontalSeparator()],
            [sg.Text(_t("config_gui.retention_policy"))],
            [
                sg.Text(_t("config_gui.optional_ntp_server_uri"), size=(40, 1)),
                sg.Input(
                    key="repo_opts.retention_strategy.ntp_time_server", size=(50, 1)
                ),
            ],
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
                                key="inherited.repo_opts.retention_strategy.hourly",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="repo_opts.retention_strategy.hourly", size=(3, 1)
                            ),
                            sg.Text(_t("config_gui.hourly"), size=(20, 1)),
                        ],
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.repo_opts.retention_strategy.daily",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="repo_opts.retention_strategy.daily", size=(3, 1)
                            ),
                            sg.Text(_t("config_gui.daily"), size=(20, 1)),
                        ],
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.repo_opts.retention_strategy.weekly",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="repo_opts.retention_strategy.weekly", size=(3, 1)
                            ),
                            sg.Text(_t("config_gui.weekly"), size=(20, 1)),
                        ],
                    ]
                ),
                sg.Column(
                    [
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.repo_opts.retention_strategy.monthly",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="repo_opts.retention_strategy.monthly", size=(3, 1)
                            ),
                            sg.Text(_t("config_gui.monthly"), size=(20, 1)),
                        ],
                        [
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.repo_opts.retention_strategy.yearly",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(
                                key="repo_opts.retention_strategy.yearly", size=(3, 1)
                            ),
                            sg.Text(_t("config_gui.yearly"), size=(20, 1)),
                        ],
                    ]
                ),
            ],
        ]

        prometheus_col = [
            [sg.Text(_t("config_gui.available_variables"))],
            [
                sg.Checkbox(
                    _t("config_gui.enable_prometheus"),
                    key="prometheus.metrics",
                    size=(41, 1),
                ),
            ],
            [
                sg.Text(_t("config_gui.job_name"), size=(40, 1)),
                sg.Input(key="prometheus.backup_job", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.metrics_destination"), size=(40, 1)),
                sg.Input(key="prometheus.destination", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.no_cert_verify"), size=(40, 1)),
                sg.Checkbox("", key="prometheus.no_cert_verify", size=(41, 1)),
            ],
            [
                sg.Text(_t("config_gui.metrics_username"), size=(40, 1)),
                sg.Input(key="prometheus.http_username", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.metrics_password"), size=(40, 1)),
                sg.Input(key="prometheus.http_password", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.instance"), size=(40, 1)),
                sg.Input(key="prometheus.instance", size=(50, 1)),
            ],
            [
                sg.Text(_t("generic.group"), size=(40, 1)),
                sg.Input(key="prometheus.group", size=(50, 1)),
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
                                key="prometheus.additional_labels",
                                headings=[],
                                col0_heading=_t("config_gui.additional_labels"),
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
                sg.Text(_t("config_gui.additional_parameters"), size=(40, 1)),
            ],
            [
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.backup_opts.additional_parameters",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="backup_opts.additional_parameters", size=(50, 1)),
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

        scheduled_task_col = [
            [
                sg.Text(_t("config_gui.create_scheduled_task_every")),
                sg.Input(key="scheduled_task_interval", size=(4, 1)),
                sg.Text(_t("generic.minutes")),
                sg.Button(_t("generic.create"), key="create_task"),
            ],
            [sg.Text(_t("config_gui.scheduled_task_explanation"))],
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
                    _t("generic.scheduled_task"),
                    scheduled_task_col,
                    font="helvetica 16",
                    key="--tab-global-scheduled_task--",
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
    )

    backup_paths_tree = sg.TreeData()
    tags_tree = sg.TreeData()
    exclude_patterns_tree = sg.TreeData()
    exclude_files_tree = sg.TreeData()
    pre_exec_commands_tree = sg.TreeData()
    post_exec_commands_tree = sg.TreeData()
    prometheus_labels_tree = sg.TreeData()
    env_variables_tree = sg.TreeData()
    encrypted_env_variables_tree = sg.TreeData()

    # Update gui with first default object (repo or group)
    update_object_gui(get_objects()[0], unencrypted=False)
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
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--CANCEL--"):
            break

        # We need to patch values since sg.Tree() only returns selected data from TreeData()
        # @PysimpleGUI: there should be a get_all_values() method or something
        tree_data_keys = [
            "backup_opts.paths",
            "backup_opts.tags",
            "backup_opts.pre_exec_commands",
            "backup_opts.post_exec_commands",
            "backup_opts.exclude_files",
            "backup_opts.exclude_patterns",
            "prometheus.additional_labels",
            "env.env_variables",
            "env.encrypted_env_variables",
        ]
        for tree_data_key in tree_data_keys:
            values[tree_data_key] = []
            for node in window[tree_data_key].TreeData.tree_dict.values():
                if node.values:
                    values[tree_data_key].append(node.values)

        if event == "-OBJECT-SELECT-":
            # Update full_config with current object before updating
            full_config = update_config_dict(
                full_config, current_object_type, current_object_name, values
            )
            current_object_type, current_object_name = object_type, object_name
            update_object_gui(values["-OBJECT-SELECT-"], unencrypted=False)
            update_global_gui(full_config, unencrypted=False)
            continue
        if event == "-OBJECT-DELETE-":
            full_config = delete_object(full_config, values["-OBJECT-SELECT-"])
            update_object_selector()
            continue
        if event == "-OBJECT-CREATE-":
            full_config = create_object(full_config)
            update_object_selector()
            continue
        if event == "--SET-PERMISSIONS--":
            manager_password = configuration.get_manager_password(
                full_config, object_name
            )
            if ask_manager_password(manager_password):
                full_config = set_permissions(full_config, values["-OBJECT-SELECT-"])
            continue
        if event in (
            "--ADD-PATHS-FILE--",
            "--ADD-PATHS-FOLDER--",
            "--ADD-EXCLUDE-FILE--",
        ):
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
            tree.insert("", node, node, node, icon=icon)
            window[key].update(values=tree)
            continue
        if event in (
            "--ADD-TAG--",
            "--ADD-EXCLUDE-PATTERN--",
            "--ADD-PRE-EXEC-COMMAND--",
            "--ADD-POST-EXEC-COMMAND--",
            "--ADD-PROMETHEUS-LABEL--",
            "--ADD-ENV-VARIABLE--",
            "--ADD-ENCRYPTED-ENV-VARIABLE--",
            "--REMOVE-PATHS--",
            "--REMOVE-TAG--",
            "--REMOVE-EXCLUDE-PATTERN--",
            "--REMOVE-EXCLUDE-FILE--",
            "--REMOVE-PRE-EXEC-COMMAND--",
            "--REMOVE-POST-EXEC-COMMAND--",
            "--REMOVE-PROMETHEUS-LABEL--",
            "--REMOVE-ENV-VARIABLE--",
            "--REMOVE-ENCRYPTED-ENV-VARIABLE--",
        ):
            if "PATHS" in event:
                option_key = "backup_opts.paths"
                tree = backup_paths_tree
            elif "TAG" in event:
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
                tree = prometheus_labels_tree
                option_key = "prometheus.additional_labels"
            elif "ENCRYPTED-ENV-VARIABLE" in event:
                tree = encrypted_env_variables_tree
                option_key = "env.encrypted_env_variables"
            elif "ENV-VARIABLE" in event:
                tree = env_variables_tree
                option_key = "env.env_variables"

            if event.startswith("--ADD-"):
                icon = TREE_ICON
                if "ENV-VARIABLE" in event:
                    var_name = sg.PopupGetText(_t("config_gui.enter_var_name"))
                    var_value = sg.PopupGetText(_t("config_gui.enter_var_value"))
                    if var_name and var_value:
                        tree.insert("", var_name, var_name, var_value, icon=icon)
                else:
                    node = sg.PopupGetText(popup_text)
                    if node:
                        tree.insert("", node, node, node, icon=icon)
            if event.startswith("--REMOVE-"):
                for key in values[option_key]:
                    if object_type != "group" and tree.tree_dict[key].icon in (
                        INHERITED_TREE_ICON,
                        INHERITED_FILE_ICON,
                        INHERITED_FOLDER_ICON,
                    ):
                        sg.PopupError(
                            _t("config_gui.cannot_remove_group_inherited_settings")
                        )
                        continue
                    tree.delete(key)
            window[option_key].Update(values=tree)
            continue
        if event == "--ACCEPT--":
            if (
                not values["repo_opts.repo_password"]
                and not values["repo_opts.repo_password_command"]
            ):
                sg.PopupError(_t("config_gui.repo_password_cannot_be_empty"))
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
            if ask_manager_password(manager_password):
                update_object_gui(values["-OBJECT-SELECT-"], unencrypted=True)
                update_global_gui(full_config, unencrypted=True)
            continue
        if event == "create_task":
            if os.name == "nt":
                result = create_scheduled_task(
                    CURRENT_EXECUTABLE, values["scheduled_task_interval"]
                )
                if result:
                    sg.Popup(_t("config_gui.scheduled_task_creation_success"))
                else:
                    sg.PopupError(_t("config_gui.scheduled_task_creation_failure"))
            else:
                sg.PopupError(_t("config_gui.scheduled_task_creation_failure"))
            continue
    window.close()
    return full_config
