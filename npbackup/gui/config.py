#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.config"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023121401"


from typing import List
import os
from logging import getLogger
from copy import deepcopy
import PySimpleGUI as sg
import npbackup.configuration as configuration
from ofunctions.misc import get_key_from_value
from npbackup.core.i18n_helper import _t
from npbackup.path_helper import CURRENT_EXECUTABLE
from npbackup.core.nuitka_helper import IS_COMPILED

if os.name == "nt":
    from npbackup.windows.task import create_scheduled_task

logger = getLogger()


def ask_backup_admin_password(config_dict) -> bool:
    try:
        backup_admin_password = config_dict["options"]["backup_admin_password"]
    except KeyError:
        backup_admin_password = None
    if backup_admin_password:
        if sg.PopupGetText(
            _t("config_gui.enter_backup_admin_password"), password_char="*"
        ) == str(backup_admin_password):
            return True
        sg.PopupError(_t("config_gui.wrong_password"))
        return False
    else:
        sg.PopupError(_t("config_gui.no_backup_admin_password_set"))
        return False


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
    
    
    def get_object_from_combo(combo_value: str) -> (str, str):
        """
        Extracts selected object from combobox
        Returns object type and name
        """

        if combo_value.startswith("Repo: "):
            object_type = "repo"
            object_name = combo_value[len("Repo: "):]
        elif combo_value.startswith("Group: "):
            object_type = "group"
            object_name = combo_value[len("Group: "):]
        return object_type, object_name

    
    def update_gui_values(key, value, inherited, object_type, unencrypted):
        """
        Update gui values depending on their type
        """
        if key == "backup_admin_password":
            return
        if key == "repo_uri":
            if object_type == "group":
                window[key].Disabled = True
            else:
                window[key].Disabled = False
        try:
            # Don't show sensible info unless unencrypted requested
            if not unencrypted:
                if key in configuration.ENCRYPTED_OPTIONS:
                    try:
                        if (
                            value is None
                            or value == ""
                        ):
                            return
                        if not str(value).startswith(
                            configuration.ID_STRING
                        ):
                            value = ENCRYPTED_DATA_PLACEHOLDER
                    except (KeyError, TypeError):
                        pass

            if isinstance(value, list):
                value = "\n".join(value)
            if key in combo_boxes:
                window[key].Update(combo_boxes[key][value])
            else:
                window[key].Update(value)

            # Set inheritance on 
            inheritance_key = f'inherited.{key}'
            if inheritance_key in window.AllKeysDict:
                window[f'inherited.{key}'].update(visible=True if inherited else False)

        except KeyError:
            logger.error(f"No GUI equivalent for key {key}.")
        except TypeError as exc:
            logger.error(f"Error: {exc} for key {key}.")

    def iter_over_config(object_config: dict, config_inheritance: dict = None, object_type: str = None, unencrypted: bool = False, root_key: str =''):
        """
        Iter over a dict while retaining the full key path to current object
        """
        base_object = object_config

        def _iter_over_config(object_config: dict, root_key=''):
            # Special case where env is a dict but we should pass it directly as it to update_gui_values
            if isinstance(object_config, dict):
                for key in object_config.keys():
                    if root_key:
                        _iter_over_config(object_config[key], root_key=f'{root_key}.{key}')
                    else:
                        _iter_over_config(object_config[key], root_key=f'{key}')
            else:
                if config_inheritance:
                    inherited = config_inheritance.g(root_key)
                else:
                    inherited = False
                update_gui_values(root_key, base_object.g(root_key), inherited, object_type, unencrypted)
        _iter_over_config(object_config, root_key)

    def update_object_gui(object_name = None, unencrypted=False):
        # Load fist available repo or group if none given
        if not object_name:
            object_name = get_objects()[0]

        # First we need to clear the whole GUI to reload new values
        for key in window.AllKeysDict:
            # We only clear config keys, wihch have '.' separator
            if  "." in str(key):
                window[key]('')
        
        object_type, object_name = get_object_from_combo(object_name)
        if object_type == 'repo':
            object_config, config_inheritance = configuration.get_repo_config(full_config, object_name, eval_variables=False)
        if object_type == 'group':
            object_config = configuration.get_group_config(full_config, object_name, eval_variables=False)


        # Now let's iter over the whole config object and update keys accordingly
        iter_over_config(object_config, config_inheritance, object_type, unencrypted, None)

    def update_global_gui(full_config, unencrypted=False):
        # TODO
        return
        global_config = deepcopy(full_config)

        # Only update global options gui with identified global keys
        for key in global_config.keys():
            if key not in ('identity', 'global_prometheus', 'global_options'):
                global_config.pop(key)
        print(global_config)
            
        iter_over_config(global_config, None, None, unencrypted, None)


    def update_config_dict(values, full_config):
        for key, value in values.items():
            if value == ENCRYPTED_DATA_PLACEHOLDER:
                continue
            if not isinstance(key, str) or (isinstance(key, str) and not '.' in key):
                # Don't bother with keys that don't contain with "."
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
            if key not in full_config.keys():
                full_config[key] = {}

            full_config.s(key, value)
        return full_config


    def object_layout(object_type: str = "repo") -> List[list]:
        """
        Returns the GUI layout depending on the object type
        """
        backup_col = [
            [
                sg.Text(_t("config_gui.compression"), size=(40, 1)),
                sg.Combo(
                    list(combo_boxes["compression"].values()),
                    key="backup_opts.compression",
                    size=(48, 1),
                ),
            ],
            [
                sg.Text(
                    "{}\n({})".format(
                        _t("config_gui.backup_paths"), _t("config_gui.one_per_line")
                    ),
                    size=(40, 2),
                ),
                sg.Multiline(key="backup_opts.paths", size=(48, 4)),
            ],
            [
                sg.Text(_t("config_gui.source_type"), size=(40, 1)),
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
                sg.Text("inherited", key="inherited.backup_opts.use_fs_snapshot", visible=False),
                sg.Checkbox("", key="backup_opts.use_fs_snapshot", size=(41, 1)),
            ],
            [
                sg.Text(
                    "{}\n({})".format(
                        _t("config_gui.ignore_cloud_files"), _t("config_gui.windows_only")
                    ),
                    size=(40, 2),
                ),
                sg.Checkbox("", key="backup_opts.ignore_cloud_files", size=(41, 1)),
            ],
            [
                sg.Text(
                    "{}\n({})".format(
                        _t("config_gui.exclude_patterns"), _t("config_gui.one_per_line")
                    ),
                    size=(40, 2),
                ),
                sg.Multiline(key="backup_opts.exclude_patterns", size=(48, 4)),
            ],
            [
                sg.Text(
                    "{}\n({})".format(
                        _t("config_gui.exclude_files"), _t("config_gui.one_per_line")
                    ),
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
                sg.Text(_t("config_gui.pre_exec_command"), size=(40, 1)),
                sg.Input(key="backup_opts.pre_exec_command", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.maximum_exec_time"), size=(40, 1)),
                sg.Input(key="backup_opts.pre_exec_timeout", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.exec_failure_is_fatal"), size=(40, 1)),
                sg.Checkbox("", key="backup_opts.pre_exec_failure_is_fatal", size=(41, 1)),
            ],
            [
                sg.Text(_t("config_gui.post_exec_command"), size=(40, 1)),
                sg.Input(key="backup_opts.post_exec_command", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.maximum_exec_time"), size=(40, 1)),
                sg.Input(key="backup_opts.post_exec_timeout", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.exec_failure_is_fatal"), size=(40, 1)),
                sg.Checkbox("", key="backup_opts.post_exec_failure_is_fatal", size=(41, 1)),
            ],
            [
                sg.Text(
                    "{}\n({})".format(_t("config_gui.tags"), _t("config_gui.one_per_line")),
                    size=(40, 2),
                ),
                sg.Multiline(key="backup_opts.tags", size=(48, 2)),
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
                sg.Text(_t("config_gui.additional_backup_only_parameters"), size=(40, 1)),
                sg.Input(key="backup_opts.additional_backup_only_parameters", size=(50, 1)),
            ],
        ]

        repo_col = [
            [
                sg.Text(_t("config_gui.backup_repo_uri"), size=(40, 1)),
                sg.Input(key="repo_uri", size=(50, 1)),
            ],
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
            [
                sg.Text(_t("config_gui.enter_backup_admin_password"), size=(40, 1)),
                sg.Input(key="backup_admin_password", size=(50, 1), password_char="*"),
            ],
            [sg.Button(_t("generic.change"), key="change_backup_admin_password")],
            [sg.HorizontalSeparator()],
            [sg.Text(_t("config_gui.retention_policy"))],
            [
                sg.Text(_t("config_gui.custom_time_server_url"), size=(40, 1)),
                sg.Input(key="repo_opts.retention_strategy.custom_time_server", size=(50, 1)),
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
                    "{}\n({}\n{})".format(
                        _t("config_gui.additional_labels"),
                        _t("config_gui.one_per_line"),
                        _t("config_gui.format_equals"),
                    ),
                    size=(40, 3),
                ),
                sg.Multiline(key="prometheus.additional_labels", size=(48, 3)),
            ],
        ]

        env_col = [
            [
                sg.Text(
                    "{}\n({}\n{})".format(
                        _t("config_gui.environment_variables"),
                        _t("config_gui.one_per_line"),
                        _t("config_gui.format_equals"),
                    ),
                    size=(40, 3),
                ),
                sg.Multiline(key="env.env_variables", size=(48, 5)),
            ],
            [
                sg.Text(
                    "{}\n({}\n{})".format(
                        _t("config_gui.encrypted_environment_variables"),
                        _t("config_gui.one_per_line"),
                        _t("config_gui.format_equals"),
                    ),
                    size=(40, 3),
                ),
                sg.Multiline(key="env.encrypted_env_variables", size=(48, 5)),
            ],
        ]

        object_list = get_objects()
        object_selector = [
            [
            sg.Text(_t("config_gui.select_object")), sg.Combo(object_list, default_value=object_list[0], key='-OBJECT-', enable_events=True)
            ]
        ]

        tab_group_layout = [
            [
                sg.Tab(
                    _t("config_gui.backup"),
                    [[sg.Column(backup_col, scrollable=True, vertical_scroll_only=True)]],
                    font="helvetica 16",
                    key="--tab-backup--",
                    element_justification="L",
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.backup_destination"),
                    repo_col,
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
            [sg.Column(object_selector, element_justification='L')],
            [sg.TabGroup(tab_group_layout, enable_events=True, key="--object-tabgroup--")],
        ]
        return _layout


    def global_options_layout():
        """"
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

        prometheus_col = [
            [sg.Text(_t("config_gui.available_variables"))],
            [
                sg.Text(_t("config_gui.enable_prometheus"), size=(40, 1)),
                sg.Checkbox("", key="global_prometheus.metrics", size=(41, 1)),
            ],
            [
                sg.Text(_t("config_gui.job_name"), size=(40, 1)),
                sg.Input(key="global_prometheus.backup_job", size=(50, 1)),
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
                sg.Text(_t("generic.group"), size=(40, 1)),
                sg.Input(key="global_prometheus.group", size=(50, 1)),
            ],
            [
                sg.Text(
                    "{}\n({}\n{})".format(
                        _t("config_gui.additional_labels"),
                        _t("config_gui.one_per_line"),
                        _t("config_gui.format_equals"),
                    ),
                    size=(40, 3),
                ),
                sg.Multiline(key="global_prometheus.additional_labels", size=(48, 3)),
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
                sg.Input(key="global_options.auto_upgrade_server_username", size=(50, 1)),
            ],
            [
                sg.Text(_t("config_gui.auto_upgrade_server_password"), size=(40, 1)),
                sg.Input(key="global_options.auto_upgrade_server_password", size=(50, 1)),
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
            [sg.HorizontalSeparator()]
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
                    _t("config_gui.prometheus_config"),
                    prometheus_col,
                    font="helvetica 16",
                    key="--tab-global-prometheus--",
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
            [sg.TabGroup(tab_group_layout, enable_events=True, key="--global-tabgroup--")],
        ]
        return _layout
    

    def config_layout() -> List[list]:

        buttons = [
            [
                sg.Push(),
                sg.Button(_t("generic.accept"), key="accept"),
                sg.Button(_t("generic.cancel"), key="cancel"),
            ]
        ]
        
        tab_group_layout = [
            [sg.Tab(_t("config_gui.repo_group_config"), object_layout(), key="--repo-group-config--")],
            [sg.Tab(_t("config_gui.global_config"), global_options_layout(), key="--global-config--")]
        ]

        _global_layout = [
            [sg.TabGroup(tab_group_layout, enable_events=True, key="--configtabgroup--")],
            [sg.Column(buttons, element_justification="L")],
            [sg.Button("trololo")]
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
        default_button_element_size=(12, 1),
        right_click_menu=right_click_menu,
        finalize=True,
    )

    # Update gui with first default object (repo or group)
    update_object_gui(get_objects()[0], unencrypted=False)
    update_global_gui(full_config, unencrypted=False)

    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "cancel"):
            break
        if event == "-OBJECT-":
            try:
                update_object_gui(values["-OBJECT-"], unencrypted=False)
            except AttributeError:
                continue
        if event == "accept":
            if not values["repo_opts.password"] and not values["repo_opts.password_command"]:
                sg.PopupError(_t("config_gui.repo_password_cannot_be_empty"))
                continue
            full_config = update_config_dict(values, full_config)
            result = configuration.save_config(config_file, full_config)
            if result:
                sg.Popup(_t("config_gui.configuration_saved"), keep_on_top=True)
                logger.info("Configuration saved successfully.")
                break
            else:
                sg.PopupError(
                    _t("config_gui.cannot_save_configuration"), keep_on_top=True
                )
                logger.info("Could not save configuration")
        if event == _t("config_gui.show_decrypted"):
            if ask_backup_admin_password(full_config):
                update_object_gui(values["-OBJECT-"], unencrypted=True)
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
        if event == "change_backup_admin_password":
            if ask_backup_admin_password(full_config):
                full_config["options"]["backup_admin_password"] = values[
                    "backup_admin_password"
                ]
                sg.Popup(_t("config_gui.password_updated_please_save"))
    window.close()
    return full_config
