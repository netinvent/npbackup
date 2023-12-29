#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.config"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023121701"


from typing import List
import os
from logging import getLogger
import PySimpleGUI as sg
from ruamel.yaml.comments import CommentedMap
import npbackup.configuration as configuration
from ofunctions.misc import get_key_from_value
from npbackup.core.i18n_helper import _t
from npbackup.path_helper import CURRENT_EXECUTABLE
from npbackup.customization import INHERITANCE_ICON

if os.name == "nt":
    from npbackup.windows.task import create_scheduled_task

logger = getLogger()


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
        "compression": {
            "auto": _t("config_gui.auto"),
            "max": _t("config_gui.max"),
            "off": _t("config_gui.off"),
        },
        "source_type": {
            "folder_list": _t("config_gui.folder_list"),
            "files_from": _t("config_gui.files_from"),
            "files_from_verbatim": _t("config_gui.files_from_verbatim"),
            "files_from_raw": _t("config_gui.files_from_raw"),
        },
        "priority": {
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

    def get_object_from_combo(combo_value: str) -> (str, str):
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
        if key == "backup_admin_password":
            return
        if key in ("repo_uri", "repo_group"):
            if object_type == "group":
                window[key].Disabled = True
            else:
                window[key].Disabled = False
        try:
            # Don't show sensible info unless unencrypted requested
            if not unencrypted:
                if key in configuration.ENCRYPTED_OPTIONS:
                    try:
                        if value is None or value == "":
                            return
                        if not str(value).startswith(configuration.ID_STRING):
                            value = ENCRYPTED_DATA_PLACEHOLDER
                    except (KeyError, TypeError):
                        pass

            if isinstance(value, list):
                value = "\n".join(value)
            if key in combo_boxes:
                window[key].Update(combo_boxes[key][value])
            else:
                window[key].Update(value)

            # Enable inheritance icon when needed
            inheritance_key = f"inherited.{key}"
            if inheritance_key in window.AllKeysDict:
                window[inheritance_key].update(visible=inherited)

        except KeyError:
            logger.error(f"No GUI equivalent for key {key}.")
        except TypeError as exc:
            logger.error(f"Error: {exc} for key {key}.")

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
            # Special case where env is a dict but we should pass it directly as it to update_gui_values
            if isinstance(object_config, dict):
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
        # Load fist available repo or group if none given
        if not object_name:
            object_name = get_objects()[0]

        # First we need to clear the whole GUI to reload new values
        for key in window.AllKeysDict:
            # We only clear config keys, wihch have '.' separator
            if "." in str(key) and not "inherited" in str(key):
                window[key]("")

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

    def update_global_gui(full_config, unencrypted=False):
        global_config = CommentedMap()

        # Only update global options gui with identified global keys
        for key in full_config.keys():
            if key in ("identity", "global_options"):
                global_config.s(key, full_config.g(key))
        iter_over_config(global_config, None, "group", unencrypted, None)

    def update_config_dict(full_config, values):
        """
        Update full_config with keys from
        """
        # TODO
        return
        object_type, object_name = get_object_from_combo(values["-OBJECT-SELECT-"])
        for key, value in values.items():
            if value == ENCRYPTED_DATA_PLACEHOLDER:
                continue
            if not isinstance(key, str) or (isinstance(key, str) and not "." in key):
                # Don't bother with keys that don't contain with "." since they're not in the YAML config file
                # but are most probably for GUI events
                continue
            # Handle combo boxes first to transform translation into key
            if key in combo_boxes:
                value = get_key_from_value(combo_boxes[key], value)
            # check whether we need to split into list
            elif not isinstance(value, bool):
                result = value.split("\n")
                if len(result) > 1:
                    value = result
                else:
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
            # Create section if not exists
            active_object_key = f"{object_type}s.{object_name}.{key}"
            print("ACTIVE KEY", active_object_key)
            if not full_config.g(active_object_key):
                full_config.s(active_object_key, CommentedMap())

            full_config.s(active_object_key, value)
        return full_config
        # TODO: Do we actually save every modified object or just the last ?
        # TDOO: also save global options

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
                sg.Combo(permissions, default_value=default_perm, key="-PERMISSIONS-"),
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
                # sg.Button(_t("generic.change"), key="--CHANGE-MANAGER-PASSWORD--")
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
                if len(values["-MANAGER-PASSWORD-"]) < 8:
                    sg.PopupError(
                        _t("config_gui.manager_password_too_short"), keep_on_top=True
                    )
                    continue
                if not values["-PERMISSIONS-"] in permissions:
                    sg.PopupError(_t("generic.bogus_data_given"), keep_on_top=True)
                    continue
                repo_config.s("permissions", values["-PERMISSIONS-"])
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
                sg.Text(_t("config_gui.compression"), size=(40, 1)),
                sg.pin(
                    sg.Image(
                        INHERITANCE_ICON,
                        key="inherited.backup_opts.compression",
                        tooltip=_t("config_gui.group_inherited"),
                    )
                ),
                sg.Combo(
                    list(combo_boxes["compression"].values()),
                    key="backup_opts.compression",
                    size=(48, 1),
                ),
            ],
            [
                sg.Text(
                    f"{_t('config_gui.backup_paths')}\n({_t('config_gui.one_per_line')})",
                    size=(40, 2),
                ),
                sg.pin(
                    sg.Image(
                        INHERITANCE_ICON,
                        expand_x=True,
                        expand_y=True,
                        key="inherited.backup_opts.paths",
                        tooltip=_t("config_gui.group_inherited"),
                    )
                ),
                sg.Multiline(key="backup_opts.paths", size=(48, 4)),
            ],
            [
                sg.Text(_t("config_gui.source_type"), size=(40, 1)),
                sg.pin(
                    sg.Image(
                        INHERITANCE_ICON,
                        expand_x=True,
                        expand_y=True,
                        key="inherited.backup_opts.source_type",
                        tooltip=_t("config_gui.group_inherited"),
                    )
                ),
                sg.Combo(
                    list(combo_boxes["source_type"].values()),
                    key="backup_opts.source_type",
                    size=(48, 1),
                ),
            ],
            [
                sg.Text(
                    "{}\n({})".format(
                        _t("config_gui.use_fs_snapshot"), _t("config_gui.windows_only")
                    ),
                    size=(40, 2),
                ),
                sg.pin(
                    sg.Image(
                        INHERITANCE_ICON,
                        expand_x=True,
                        expand_y=True,
                        key="inherited.backup_opts.use_fs_snapshot",
                        tooltip=_t("config_gui.group_inherited"),
                    )
                ),
                sg.Checkbox("", key="backup_opts.use_fs_snapshot", size=(41, 1)),
            ],
            [
                sg.Text(
                    "{}\n({})".format(
                        _t("config_gui.ignore_cloud_files"),
                        _t("config_gui.windows_only"),
                    ),
                    size=(40, 2),
                ),
                sg.Checkbox("", key="backup_opts.ignore_cloud_files", size=(41, 1)),
            ],
            [
                sg.Text(
                    f"{_t('config_gui.exclude_patterns')}\n({_t('config_gui.one_per_line')})",
                    size=(40, 2),
                ),
                sg.Multiline(key="backup_opts.exclude_patterns", size=(48, 4)),
            ],
            [
                sg.Text(
                    f"{_t('config_gui.exclude_files')}\n({_t('config_gui.one_per_line')})",
                    size=(40, 2),
                ),
                sg.Multiline(key="backup_opts.exclude_files", size=(48, 4)),
            ],
            [
                sg.Text(
                    "{}\n({})".format(
                        _t("config_gui.exclude_case_ignore"),
                        _t("config_gui.windows_always"),
                    ),
                    size=(40, 2),
                ),
                sg.Checkbox("", key="backup_opts.exclude_case_ignore", size=(41, 1)),
            ],
            [
                sg.Text(_t("config_gui.exclude_cache_dirs"), size=(40, 1)),
                sg.Checkbox("", key="backup_opts.exclude_caches", size=(41, 1)),
            ],
            [
                sg.Text(_t("config_gui.one_file_system"), size=(40, 1)),
                sg.Checkbox("", key="backup_opts.one_file_system", size=(41, 1)),
            ],
            [
                sg.Text(
                    f"{_t('config_gui.pre_exec_commands')}\n({_t('config_gui.one_per_line')})",
                    size=(40, 2),
                ),
                sg.Multiline(key="backup_opts.pre_exec_commands", size=(48, 4)),
            ],
            [
                sg.Text(_t("config_gui.maximum_exec_time"), size=(40, 1)),
                sg.Input(key="backup_opts.pre_exec_timeout", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.exec_failure_is_fatal"), size=(40, 1)),
                sg.Checkbox(
                    "", key="backup_opts.pre_exec_failure_is_fatal", size=(41, 1)
                ),
            ],
            [
                sg.Text(
                    f"{_t('config_gui.post_exec_commands')}\n({_t('config_gui.one_per_line')})",
                    size=(40, 2),
                ),
                sg.Multiline(key="backup_opts.post_exec_commands", size=(48, 4)),
            ],
            [
                sg.Text(_t("config_gui.maximum_exec_time"), size=(40, 1)),
                sg.Input(key="backup_opts.post_exec_timeout", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.exec_failure_is_fatal"), size=(40, 1)),
                sg.Checkbox(
                    "", key="backup_opts.post_exec_failure_is_fatal", size=(41, 1)
                ),
            ],
            [
                sg.Text(
                    f"{_t('config_gui.tags')}\n({_t('config_gui.one_per_line')})",
                    size=(40, 2),
                ),
                sg.Multiline(key="backup_opts.tags", size=(48, 4)),
            ],
            [
                sg.Text(_t("config_gui.backup_priority"), size=(40, 1)),
                sg.Combo(
                    list(combo_boxes["priority"].values()),
                    key="backup_opts.priority",
                    size=(48, 1),
                ),
            ],
            [
                sg.Text(_t("config_gui.additional_parameters"), size=(40, 1)),
                sg.Input(key="backup_opts.additional_parameters", size=(50, 1)),
            ],
            [
                sg.Text(
                    _t("config_gui.additional_backup_only_parameters"), size=(40, 1)
                ),
                sg.Input(
                    key="backup_opts.additional_backup_only_parameters", size=(50, 1)
                ),
            ],
        ]

        repo_col = [
            [
                sg.Text(_t("config_gui.backup_repo_uri"), size=(40, 1)),
                sg.Input(key="repo_uri", size=(50, 1)),
            ],
            [sg.Button(_t("config_gui.set_permissions"), key="--SET-PERMISSIONS--")],
            [
                sg.Text(_t("config_gui.repo_group"), size=(40, 1)),
                sg.Input(key="repo_group", size=(50, 1)),
            ],
            [
                sg.Text(
                    "{}\n({})".format(
                        _t("config_gui.minimum_backup_age"), _t("generic.minutes")
                    ),
                    size=(40, 2),
                ),
                sg.Input(key="repo_opts.minimum_backup_age", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.backup_repo_password"), size=(40, 1)),
                sg.Input(key="repo_opts.repo_password", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.backup_repo_password_command"), size=(40, 1)),
                sg.Input(key="repo_opts.repo_password_command", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.upload_speed"), size=(40, 1)),
                sg.Input(key="repo_opts.upload_speed", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.download_speed"), size=(40, 1)),
                sg.Input(key="repo_opts.download_speed", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.backend_connections"), size=(40, 1)),
                sg.Input(key="repo_opts.backend_connections", size=(50, 1)),
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
                sg.Text(_t("config_gui.keep"), size=(30, 1)),
                sg.Input(key="repo_opts.retention_strategy.hourly", size=(3, 1)),
                sg.Text(_t("config_gui.hourly"), size=(20, 1)),
            ],
            [
                sg.Text(_t("config_gui.keep"), size=(30, 1)),
                sg.Input(key="repo_opts.retention_strategy.daily", size=(3, 1)),
                sg.Text(_t("config_gui.daily"), size=(20, 1)),
            ],
            [
                sg.Text(_t("config_gui.keep"), size=(30, 1)),
                sg.Input(key="repo_opts.retention_strategy.weekly", size=(3, 1)),
                sg.Text(_t("config_gui.weekly"), size=(20, 1)),
            ],
            [
                sg.Text(_t("config_gui.keep"), size=(30, 1)),
                sg.Input(key="repo_opts.retention_strategy.monthly", size=(3, 1)),
                sg.Text(_t("config_gui.monthly"), size=(20, 1)),
            ],
            [
                sg.Text(_t("config_gui.keep"), size=(30, 1)),
                sg.Input(key="repo_opts.retention_strategy.yearly", size=(3, 1)),
                sg.Text(_t("config_gui.yearly"), size=(20, 1)),
            ],
        ]

        prometheus_col = [
            [sg.Text(_t("config_gui.available_variables"))],
            [
                sg.Text(_t("config_gui.enable_prometheus"), size=(40, 1)),
                sg.Checkbox("", key="prometheus.metrics", size=(41, 1)),
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
                sg.Text(
                    f"{_t('config_gui.additional_labels')}\n({_t('config_gui.one_per_line')}\n{_t('config_gui.format_equals')})",
                    size=(40, 3),
                ),
                sg.Multiline(key="prometheus.additional_labels", size=(48, 3)),
            ],
        ]

        env_col = [
            [
                sg.Text(
                    f"{_t('config_gui.env_variables')}\n({_t('config_gui.one_per_line')}\n{_t('config_gui.format_equals')})",
                    size=(40, 3),
                ),
                sg.Multiline(key="env.env_variables", size=(48, 5)),
            ],
            [
                sg.Text(
                    f"{_t('config_gui.encrypted_env_variables')}\n({_t('config_gui.one_per_line')}\n{_t('config_gui.format_equals')})",
                    size=(40, 3),
                ),
                sg.Multiline(key="env.encrypted_env_variables", size=(48, 5)),
            ],
        ]

        object_list = get_objects()
        object_selector = [
            [
                sg.Text(_t("config_gui.select_object")),
                sg.Combo(
                    object_list,
                    default_value=object_list[0],
                    key="-OBJECT-SELECT-",
                    enable_events=True,
                ),
            ]
        ]

        tab_group_layout = [
            [
                sg.Tab(
                    _t("config_gui.backup"),
                    [
                        [
                            sg.Column(
                                backup_col,
                                scrollable=True,
                                vertical_scroll_only=True,
                                size=(700, 450),
                            )
                        ]
                    ],
                    font="helvetica 16",
                    key="--tab-backup--",
                    element_justification="L",
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.backup_destination"),
                    [
                        [
                            sg.Column(
                                repo_col,
                                scrollable=True,
                                vertical_scroll_only=True,
                                size=(700, 450),
                            )
                        ]
                    ],
                    font="helvetica 16",
                    key="--tab-repo--",
                    element_justification="L",
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.prometheus_config"),
                    prometheus_col,
                    font="helvetica 16",
                    key="--tab-prometheus--",
                    element_justification="L",
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.environment_variables"),
                    env_col,
                    font="helvetica 16",
                    key="--tab-env--",
                    element_justification="L",
                )
            ],
        ]

        _layout = [
            [sg.Column(object_selector, element_justification="L")],
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
                    element_justification="L",
                )
            ],
            [
                sg.Tab(
                    _t("generic.options"),
                    global_options_col,
                    font="helvetica 16",
                    key="--tab-global-options--",
                    element_justification="L",
                )
            ],
            [
                sg.Tab(
                    _t("generic.scheduled_task"),
                    scheduled_task_col,
                    font="helvetica 16",
                    key="--tab-global-scheduled_task--",
                    element_justification="L",
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
                sg.Button(_t("config_gui.create_object"), key="-OBJECT-CREATE-"),
                sg.Button(_t("config_gui.delete_object"), key="-OBJECT-DELETE-"),
                sg.Button(_t("generic.cancel"), key="--CANCEL--"),
                sg.Button(_t("generic.accept"), key="--ACCEPT--"),
            ]
        ]

        tab_group_layout = [
            [
                sg.Tab(
                    _t("config_gui.repo_group_config"),
                    object_layout(),
                    key="--repo-group-config--",
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.global_config"),
                    global_options_layout(),
                    key="--global-config--",
                )
            ],
        ]

        _global_layout = [
            [
                sg.TabGroup(
                    tab_group_layout, enable_events=True, key="--configtabgroup--"
                )
            ],
            [sg.Push(), sg.Column(buttons, element_justification="L")],
        ]
        return _global_layout

    right_click_menu = ["", [_t("config_gui.show_decrypted")]]
    window = sg.Window(
        "Configuration",
        config_layout(),
        size=(800, 600),
        text_justification="C",
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

    # Update gui with first default object (repo or group)
    update_object_gui(get_objects()[0], unencrypted=False)
    update_global_gui(full_config, unencrypted=False)

    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--CANCEL--"):
            break
        if event == "-OBJECT-SELECT-":
            try:
                update_config_dict(full_config, values)
                update_object_gui(values["-OBJECT-SELECT-"], unencrypted=False)
                update_global_gui(full_config, unencrypted=False)
            except AttributeError:
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
            object_type, object_name = get_object_from_combo(values["-OBJECT-SELECT-"])
            manager_password = configuration.get_manager_password(
                full_config, object_name
            )
            if ask_manager_password(manager_password):
                full_config = set_permissions(full_config, values["-OBJECT-SELECT-"])
            continue
        if event == "--ACCEPT--":
            if (
                not values["repo_opts.repo_password"]
                and not values["repo_opts.repo_password_command"]
            ):
                sg.PopupError(_t("config_gui.repo_password_cannot_be_empty"))
                continue
            full_config = update_config_dict(full_config, values)
            result = configuration.save_config(config_file, full_config)
            if result:
                sg.Popup(_t("config_gui.configuration_saved"), keep_on_top=True)
                logger.info("Configuration saved successfully.")
                break
            sg.PopupError(
                _t("config_gui.cannot_save_configuration"), keep_on_top=True
            )
            logger.info("Could not save configuration")
        if event == _t("config_gui.show_decrypted"):
            object_type, object_name = get_object_from_combo(values["-OBJECT-SELECT-"])
            manager_password = configuration.get_manager_password(
                full_config, object_name
            )
            if ask_manager_password(manager_password):
                update_object_gui(values["-OBJECT-SELECT-"], unencrypted=True)
                update_global_gui(full_config, unencrypted=True)
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
    window.close()
    return full_config
