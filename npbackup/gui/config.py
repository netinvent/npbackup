#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.config"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026030401"


from typing import List
import os
from logging import getLogger
import FreeSimpleGUI as sg
import textwrap
from npbackup import configuration
from npbackup.core.i18n_helper import _t
from npbackup.gui.constants import combo_boxes, byte_units
from ofunctions.misc import get_key_from_value
from npbackup.gui.ttk_theme import SUBTITLE_FONT
from resources.customization import NON_INHERITED_ICON
from npbackup.gui.helpers import quick_close_simplegui_window, popup_error, wait_window
import npbackup.gui.common_gui
import npbackup.gui.common_gui_logic

logger = getLogger()


def config_gui(full_config: dict, config_file: str):
    logger.info("Launching configuration GUI")

    def object_layout() -> List[list]:
        """
        Returns the GUI layout depending on the object type
        """
        backup_col = [
            [
                sg.Text(
                    textwrap.fill(f"{_t('config_gui.backup_objects')}"),
                    size=(None, None),
                    expand_x=True,
                    font=SUBTITLE_FONT,
                ),
                sg.Push(),
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
                sg.pin(
                    sg.Col(
                        [
                            [
                                sg.Push(),
                                sg.Button(
                                    _t("generic.remove_selected"),
                                    key="-REMOVE-SOURCE-",
                                    border_width=0,
                                    font=SUBTITLE_FONT,
                                ),
                                sg.ButtonMenu(
                                    _t("generic.add") + " ▾",
                                    menu_def=npbackup.gui.common_gui.add_source_menu(),
                                    key="-ADD-SOURCE-MENU-",
                                    font=SUBTITLE_FONT,
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
                        ],
                        key="-BACKUP-PATHS-",
                        expand_x=True,
                        expand_y=True,
                    ),
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.pin(
                    sg.Col(
                        [
                            [
                                sg.Text(
                                    _t("config_gui.stdin_from_command"),
                                    key="text_stdin_from_command",
                                )
                            ],
                            [
                                sg.Image(
                                    NON_INHERITED_ICON,
                                    key="inherited.backup_opts.stdin_from_command",
                                    tooltip=_t("config_gui.group_inherited"),
                                    pad=1,
                                ),
                                sg.Input(
                                    key="backup_opts.stdin_from_command",
                                    size=(100, 1),
                                ),
                            ],
                            [
                                sg.Text(
                                    _t("config_gui.stdin_filename"),
                                    key="text_stdin_filename",
                                )
                            ],
                            [
                                sg.Image(
                                    NON_INHERITED_ICON,
                                    key="inherited.backup_opts.stdin_filename",
                                    tooltip=_t("config_gui.group_inherited"),
                                    pad=1,
                                ),
                                sg.Input(
                                    key="backup_opts.stdin_filename",
                                    size=(100, 1),
                                ),
                            ],
                        ],
                        key="-BACKUP-STDIN-",
                        expand_x=True,
                        expand_y=True,
                    )
                )
            ],
            [
                sg.Column(
                    [
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
                        [
                            sg.Text(_t("config_gui.backup_priority"), size=(40, 1)),
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
                            sg.Text(
                                _t("config_gui.minimum_backup_size_error"), size=(50, 2)
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
                            sg.Text(_t("config_gui.pack_size"), size=(40, 1)),
                            sg.Image(
                                NON_INHERITED_ICON,
                                key="inherited.backup_opts.pack_size",
                                tooltip=_t("config_gui.group_inherited"),
                                pad=1,
                            ),
                            sg.Input(key="backup_opts.pack_size", size=(8, 1)),
                        ],
                    ],
                    pad=0,
                    expand_x=True,
                    expand_y=True,
                ),
                sg.Push(),
                sg.Column(
                    npbackup.gui.common_gui.backup_tags_col(),
                    expand_x=True,
                    expand_y=True,
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
                    key="backup_opts.additional_backup_only_parameters",
                    size=(100, 1),
                    expand_x=True,
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
                    key="backup_opts.additional_restore_only_parameters",
                    size=(100, 1),
                    expand_x=True,
                ),
            ],
        ]

        housekeeping_col = [
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
                sg.Text(
                    _t(
                        "config_gui.post_backup_housekeeping_percent_chance_explanation"
                    ),
                    size=(80, 1),
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
                sg.Text(
                    _t("config_gui.post_backup_housekeeping_interval_explanation"),
                    size=(80, 1),
                ),
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
            [
                sg.Text(_t("config_gui.read_data_subset"), size=(40, 1)),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.read_data_subset",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Input(key="repo_opts.read_data_subset", size=(8, 1)),
            ],
        ]

        exclusions_col = [
            [
                sg.Push(),
                sg.Button(
                    _t("generic.remove_selected"),
                    key="--REMOVE-EXCLUDE-PATTERN--",
                    size=(18, 1),
                ),
                sg.Button(
                    _t("generic.add") + " ▾",
                    key="--ADD-EXCLUDE-PATTERN--",
                    size=(18, 1),
                ),
            ],
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
            ],
            [sg.HSeparator()],
            [
                sg.Push(),
                sg.Input(
                    visible=False,
                    key="--ADD-EXCLUDE-FILE--",
                    enable_events=True,
                ),
                sg.Button(
                    _t("generic.remove_selected"),
                    key="--REMOVE-EXCLUDE-FILE--",
                    size=(18, 1),
                ),
                sg.Button(
                    _t("generic.add_manually"),
                    key="--ADD-EXCLUDE-FILE-MANUALLY--",
                    size=(18, 1),
                ),
                sg.FilesBrowse(
                    _t("generic.add") + " ▾",
                    target="--ADD-EXCLUDE-FILE--",
                    size=(18, 1),
                ),
            ],
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
                    f'{_t("config_gui.excludes_case_ignore")} ({_t("config_gui.windows_no_effect")})',
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
                sg.Push(),
                sg.Button(
                    _t("generic.remove_selected"),
                    key="--REMOVE-PRE-EXEC-COMMAND--",
                    size=(18, 1),
                ),
                sg.Button(
                    _t("generic.add") + " ▾",
                    key="--ADD-PRE-EXEC-COMMAND--",
                    size=(18, 1),
                ),
            ],
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
                sg.Push(),
                sg.Button(
                    _t("generic.remove_selected"),
                    key="--REMOVE-POST-EXEC-COMMAND--",
                    size=(18, 1),
                ),
                sg.Button(
                    _t("generic.add") + " ▾",
                    key="--ADD-POST-EXEC-COMMAND--",
                    size=(18, 1),
                ),
            ],
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
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited_repo_group",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Combo(
                    values=configuration.get_group_list(full_config),
                    key="repo_group",
                    enable_events=True,
                ),
            ],
            [
                sg.Text(_t("config_gui.compression"), size=(40, 1)),
                sg.Image(
                    NON_INHERITED_ICON,
                    key="inherited.repo_opts.compression",
                    tooltip=_t("config_gui.group_inherited"),
                    pad=1,
                ),
                sg.Combo(
                    list(combo_boxes["repo_opts.compression"].values()),
                    key="repo_opts.compression",
                    size=(20, 1),
                ),
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

        env_col = [
            [
                sg.Push(),
                sg.Button(
                    _t("generic.remove_selected"),
                    key="--REMOVE-ENV-VARIABLE--",
                    size=(18, 1),
                ),
                sg.Button(
                    _t("generic.add") + " ▾",
                    key="--ADD-ENV-VARIABLE--",
                    size=(18, 1),
                ),
            ],
            [
                sg.Tree(
                    sg.TreeData(),
                    key="env.env_variables",
                    headings=[_t("generic.value")],
                    col0_heading=_t("config_gui.env_variables"),
                    col0_width=1,
                    auto_size_columns=True,
                    justification="L",
                    num_rows=3,
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Push(),
                sg.Button(
                    _t("generic.remove_selected"),
                    key="--REMOVE-ENCRYPTED-ENV-VARIABLE--",
                    size=(18, 1),
                ),
                sg.Button(
                    _t("generic.add") + " ▾",
                    key="--ADD-ENCRYPTED-ENV-VARIABLE--",
                    size=(18, 1),
                ),
            ],
            [
                sg.Tree(
                    sg.TreeData(),
                    key="env.encrypted_env_variables",
                    headings=[_t("generic.value")],
                    col0_heading=_t("config_gui.encrypted_env_variables"),
                    col0_width=1,
                    auto_size_columns=True,
                    justification="L",
                    num_rows=3,
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Text(_t("config_gui.add_identity")),
                sg.Button("S3", key="--ADD-S3-IDENTITY--", size=(18, 1)),
                sg.Button("Azure", key="--ADD-AZURE-IDENTITY--", size=(18, 1)),
                sg.Button("B2", key="--ADD-B2-IDENTITY--", size=(18, 1)),
                sg.Button(
                    "Google Cloud Storage", key="--ADD-GCS-IDENTITY--", size=(18, 1)
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
                sg.Input(
                    key="backup_opts.additional_parameters",
                    size=(100, 1),
                    expand_x=True,
                ),
            ],
        ]

        object_list = npbackup.gui.common_gui_logic.get_objects(full_config)
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
                    font=SUBTITLE_FONT,
                    key="--tab-backup--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.backup_destination"),
                    repo_col,
                    font=SUBTITLE_FONT,
                    key="--tab-repo--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.exclusions"),
                    exclusions_col,
                    font=SUBTITLE_FONT,
                    key="--tab-exclusions--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.retention_policy"),
                    npbackup.gui.common_gui.retention_col(),
                    font=SUBTITLE_FONT,
                    key="--tab-retention--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.housekeeping"),
                    housekeeping_col,
                    font=SUBTITLE_FONT,
                    key="--tab-housekeeping--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.pre_post"),
                    pre_post_col,
                    font=SUBTITLE_FONT,
                    key="--tab-hooks--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.repo_monitoring_identity"),
                    npbackup.gui.common_gui.per_object_monitoring_identity_col(),
                    font=SUBTITLE_FONT,
                    key="--tab-monitoring--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Tab(
                    _t("config_gui.env_variables"),
                    env_col,
                    font=SUBTITLE_FONT,
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
                    tab_group_layout,
                    enable_events=True,
                    key="--object-tabgroup--",
                    expand_x=True,
                    expand_y=True,
                )
            ],
        ]
        return _layout

    def global_options_layout():
        """ "
        Returns layout for global options that can't be overridden by group / repo settings
        """

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

        _layout = [
            [
                sg.TabGroup(
                    [
                        [
                            sg.Tab(
                                _t("config_gui.global_monitoring_identity"),
                                npbackup.gui.common_gui.global_monitoring_identity_col(),
                                font=SUBTITLE_FONT,
                                key="--tab-global-monitoring-identity--",
                                expand_x=True,
                            )
                        ]
                    ]
                    + npbackup.gui.common_gui.global_monitoring_tab_group()
                    + [
                        [
                            sg.Tab(
                                _t("generic.options"),
                                global_options_col,
                                font=SUBTITLE_FONT,
                                key="--tab-global-options--",
                                expand_x=True,
                                expand_y=True,
                            )
                        ],
                    ],
                    enable_events=True,
                    key="--global-tabgroup--",
                    expand_x=True,
                    expand_y=True,
                )
            ]
        ]
        return _layout

    def config_layout() -> List[list]:
        buttons = [
            [
                sg.Push(),
                sg.Button(
                    _t("config_gui.add_object"),
                    key="-OBJECT-CREATE-",
                    size=(40, 1),
                    font=SUBTITLE_FONT,
                ),
                sg.Button(
                    _t("config_gui.delete_object"),
                    key="-OBJECT-DELETE-",
                    size=(40, 1),
                    font=SUBTITLE_FONT,
                ),
                sg.Button(
                    _t("generic.cancel"),
                    key="--CANCEL--",
                    size=(13, 1),
                    font=SUBTITLE_FONT,
                ),
                sg.Button(
                    _t("generic.accept"),
                    key="--ACCEPT--",
                    size=(13, 1),
                    font=SUBTITLE_FONT,
                ),
            ]
        ]

        """ WIP replace with newer task creation ui
        object_list = npbackup.gui.common_gui_logic.get_objects(full_config)
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
        """

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
                    npbackup.gui.common_gui.scheduling_col(),
                    font=SUBTITLE_FONT,
                    key="--tab-global-scheduled_task--",
                    expand_x=True,
                    expand_y=True,
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
        # margins=(0, 0),
        # element_padding=(0, 0),
        right_click_menu=right_click_menu,
        finalize=True,
        enable_close_attempted_event=True,
    )

    # Update gui with first default object (repo or group)
    full_config = npbackup.gui.common_gui_logic.update_object_gui(
        window, full_config, unencrypted=False
    )
    npbackup.gui.common_gui_logic.update_global_gui(
        window, full_config, unencrypted=False
    )

    # These contain object name/type so on object change we can update the current object before loading new one
    current_object_type = None
    current_object_name = None

    if config_file:
        window.set_title(f"Configuration - {config_file}")

    # Common config pages with wizard patches
    try:
        retention_policies = list(full_config.g("presets.retention_policies"))
    except Exception:
        # We might need to fallback to integrated presets in constants
        retention_policies = configuration.get_default_config().g(
            "presets.retention_policy"
        )

    retention_policies_list = list(retention_policies.keys())
    retention_policies_list = [
        _t(f"wizard_gui.{policy}") for policy in retention_policies_list  # WIP
    ]

    window["-RETENTION-POLICY-ADVANCED-COLUMN-"].update(visible=True)
    window["-RETENTION-POLICY-ADVANCED-"].update(visible=False)

    window["-RETENTION-POLICIES-"].update(values=retention_policies_list)
    window["-RETENTION-POLICIES-"].update(set_to_index=0)

    event, values = window.read(timeout=0.1)
    npbackup.gui.common_gui_logic.update_monitoring_visibility(
        window=window, values=values
    )

    while True:
        event, values = window.read()
        # Get object type for various delete operations
        object_type, object_name = npbackup.gui.common_gui_logic.get_object_from_combo(
            values["-OBJECT-SELECT-"]
        )
        if not current_object_type and not current_object_name:
            current_object_type, current_object_name = object_type, object_name
            npbackup.gui.common_gui_logic.update_object_selector(
                window, full_config, current_object_name, current_object_type
            )
        if event in (
            sg.WIN_CLOSED,
            sg.WIN_X_EVENT,
            "--CANCEL--",
            "-WINDOW CLOSE ATTEMPTED-",
        ):
            break

        ## Handle most lists add/remove objects
        npbackup.gui.common_gui_logic.handle_gui_events(
            full_config=full_config,
            window=window,
            event=event,
            values=values,
            object_type=object_type,
        )

        if event in ("-OBJECT-SELECT-", "repo_group"):
            # Update full_config with current object before updating
            full_config = npbackup.gui.common_gui_logic.update_config_dict(
                window, full_config, current_object_type, current_object_name, values
            )
            current_object_type, current_object_name = object_type, object_name
            full_config = npbackup.gui.common_gui_logic.update_object_gui(
                window,
                full_config,
                current_object_type,
                current_object_name,
                unencrypted=False,
            )
            npbackup.gui.common_gui_logic.update_global_gui(
                window, full_config, unencrypted=False
            )
            continue
        if event == "-OBJECT-DELETE-":
            object_type, object_name = (
                npbackup.gui.common_gui_logic.get_object_from_combo(
                    values["-OBJECT-SELECT-"]
                )
            )
            full_config = npbackup.gui.common_gui_logic.delete_object(
                window, full_config, values["-OBJECT-SELECT-"]
            )
            current_object_type, current_object_name = (
                npbackup.gui.common_gui_logic.update_object_selector(
                    window, full_config
                )
            )
            continue
        if event == "-OBJECT-CREATE-":
            full_config, _object_type, _object_name = (
                npbackup.gui.common_gui_logic.create_object(window, full_config)
            )
            if _object_type and _object_name:
                object_type = _object_type
                object_name = _object_name
                npbackup.gui.common_gui_logic.update_object_selector(
                    window, full_config, object_name, object_type
                )
                current_object_type = object_type
                current_object_name = object_name
            continue
        if event == "--SET-PERMISSIONS--":
            manager_password = configuration.get_manager_password(
                full_config, object_name
            )
            if (
                not manager_password
                or npbackup.gui.common_gui_logic.ask_manager_password(manager_password)
            ):
                # We need to update full_config with current GUI values before using or modifying it
                full_config = npbackup.gui.common_gui_logic.update_config_dict(
                    window,
                    full_config,
                    current_object_type,
                    current_object_name,
                    values,
                )
                full_config = npbackup.gui.common_gui_logic.set_permissions(
                    full_config,
                    object_type=current_object_type,
                    object_name=current_object_name,
                )
                full_config = npbackup.gui.common_gui_logic.update_object_gui(
                    window,
                    full_config,
                    current_object_type,
                    current_object_name,
                    unencrypted=False,
                )
                npbackup.gui.common_gui_logic.update_global_gui(
                    window, full_config, unencrypted=False
                )
            continue

        # WIP duplicate code with wizard ?
        if event == "--ACCEPT--":
            if object_type != "groups":
                result = _t("generic.yes")
                if not values["repo_uri"]:
                    result = sg.popup(
                        _t("config_gui.repo_uri_should_not_be_empty")
                        + ". "
                        + _t("generic.are_you_sure"),
                        keep_on_top=True,
                        icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                        custom_text=(_t("generic.no"), _t("generic.yes")),
                        title=_t("generic.warning").capitalize(),
                    )
                if (
                    not values["repo_opts.repo_password"]
                    and not values["repo_opts.repo_password_command"]
                ):
                    result = sg.popup(
                        _t("config_gui.repo_password_should_not_be_empty")
                        + ". "
                        + _t("generic.are_you_sure"),
                        keep_on_top=True,
                        icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                        custom_text=(_t("generic.no"), _t("generic.yes")),
                        title=_t("generic.warning").capitalize(),
                    )
                # We need to check that sg.TreeData for backups contains at least one object
                # At this point we need to reference the window object since backup_paths_tree isn't populated yet
                # TreeData will at least contain the root node, so we need to check for more than one entry
                if (
                    len(window["backup_opts.paths"].TreeData.tree_dict.values()) < 2
                    and get_key_from_value(
                        combo_boxes["backup_opts.source_type"],
                        values["backup_opts.source_type"],
                    )
                    != "stdin_from_command"
                ):
                    result = sg.popup(
                        _t("config_gui.backup_source_should_not_be_empty")
                        + ". "
                        + _t("generic.are_you_sure"),
                        keep_on_top=True,
                        icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                        custom_text=(_t("generic.no"), _t("generic.yes")),
                        title=_t("generic.warning").capitalize(),
                    )
                if result != _t("generic.yes"):
                    continue
            if not npbackup.gui.common_gui_logic.validate_email_addresses(window):
                result = sg.popup(
                    _t("config_gui.there_are_invalid_email_addresses")
                    + ". "
                    + _t("generic.are_you_sure"),
                    keep_on_top=True,
                    icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                    custom_text=(_t("generic.no"), _t("generic.yes")),
                    title=_t("generic.warning").capitalize(),
                )
                if result != _t("generic.yes"):
                    continue
            full_config = npbackup.gui.common_gui_logic.update_config_dict(
                window, full_config, current_object_type, current_object_name, values
            )
            result = configuration.save_config(config_file, full_config)
            if result:
                sg.popup(_t("config_gui.configuration_saved"), keep_on_top=True)
                break
            popup_error(_t("config_gui.cannot_save_configuration"))
            continue
        if event == _t("config_gui.show_decrypted"):
            manager_password = configuration.get_manager_password(
                full_config, object_name
            )
            # NPF-SEC-00009
            env_manager_password = os.environ.get("NPBACKUP_MANAGER_PASSWORD", None)
            if not manager_password:
                popup_error(_t("config_gui.no_manager_password_defined"))
                continue
            if (
                env_manager_password and env_manager_password == manager_password
            ) or npbackup.gui.common_gui_logic.ask_manager_password(manager_password):
                full_config = npbackup.gui.common_gui_logic.update_object_gui(
                    window,
                    full_config,
                    current_object_type,
                    current_object_name,
                    unencrypted=True,
                )
                npbackup.gui.common_gui_logic.update_global_gui(
                    window, full_config, unencrypted=True
                )
            continue
        if event == "repo_uri":
            for cloud_provider in ["s3", "azure", "b2", "gs"]:
                if values["repo_uri"].startswith(cloud_provider + ":"):
                    window["repo_uri_cloud_hint"].Update(visible=True)
                    break
                else:
                    window["repo_uri_cloud_hint"].Update(visible=False)

        if event == "-CREATE-SCHEDULED-TASK-":
            result, full_config = npbackup.gui.common_gui_logic.create_scheduled_task(
                values, full_config, config_file
            )
            if not result:
                sg.popup(
                    _t("config_gui.scheduled_task_creation_failure"), keep_on_top=True
                )
                continue
            result = configuration.save_config(config_file, full_config)
            if result:
                sg.popup(_t("config_gui.configuration_saved"), keep_on_top=True)
                break
            popup_error(_t("config_gui.cannot_save_configuration"))
            continue

    # Closing this window takes ages, let's defer it into an ugly thread
    # quick_close_simplegui_window(window)
    # This will make tkinter fail, but hey, it's hidden and we don't really care since it will die after a couple of seconds
    window.hide()
    quick_close_simplegui_window(window)
    return full_config


if __name__ == "__main__":
    full_config = configuration.get_default_config()
    config_gui(full_config, config_file=None)
