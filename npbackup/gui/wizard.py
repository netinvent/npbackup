#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.wizard"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"


import os
from typing import List, Tuple
from logging import getLogger
import FreeSimpleGUI as sg
import textwrap

if os.name == "nt":
    from command_runner.elevate import is_admin
from resources.customization import (
    OEM_LOGO,
    OEM_ICON,
    SHORT_PRODUCT_NAME,
    WIZARD_STEP_ICONS,
)
from npbackup.restic_wrapper.url_parser import parse_restic_repo, build_restic_uri
from npbackup.gui.constants import combo_boxes, byte_units
from npbackup.core.i18n_helper import _t
from ofunctions.misc import get_key_from_value
from npbackup.gui.buttons import RoundedButton
import npbackup.configuration
from npbackup.gui.ttk_theme import (
    TITLE_FONT,
    SUBTITLE_FONT,
    STANDARD_FONT,
    WINDOW_SCALING,
)
import npbackup.gui.common_gui
from npbackup.gui.helpers import WaitWindow, popup_error, password_complexity
import npbackup.gui.common_gui_logic

sg.set_options(icon=OEM_ICON)

logger = getLogger()

# Wizard always handles the default repo
OBJECT_TYPE = "repos"
OBJECT_NAME = "default"


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text


def wizard_exclusion_window(full_config: dict):
    layout = [
        [npbackup.gui.common_gui.exclusion_col()],
        [
            sg.Push(),
            sg.Button(
                _t("generic.close"), key="-CLOSE-EXCLUSIONS-", font=SUBTITLE_FONT
            ),
        ],
    ]

    exclusion_window = sg.Window(
        _t("wizard_gui.handle_exclusions"),
        layout=layout,
        size=(int(800 * WINDOW_SCALING), int(600 * WINDOW_SCALING)),
        modal=True,
        grab_anywhere=True,
        resizable=True,
        finalize=True,
    )

    npbackup.gui.common_gui_logic.update_object_gui(
        window=exclusion_window,
        full_config=full_config,
        object_type=OBJECT_TYPE,
        object_name=OBJECT_NAME,
        unencrypted=False,
        is_wizard=True,
    )

    while True:
        event, values = exclusion_window.read()
        if event == sg.WIN_CLOSED:
            values = {}
            break
        elif event == "-CLOSE-EXCLUSIONS-":
            break
        npbackup.gui.common_gui_logic.handle_gui_events(
            event=event,
            values=values,
            window=exclusion_window,
            full_config=full_config,
            is_wizard=True,
        )

    npbackup.gui.common_gui_logic.update_config_dict(
        window=exclusion_window,
        full_config=full_config,
        object_type=OBJECT_TYPE,
        object_name=OBJECT_NAME,
        values=values,
        is_wizard=True,
    )
    exclusion_window.close()
    return full_config


def create_step_header(step_num: int, title_key: str, desc_key: str = "") -> list:
    """Create a consistent step header with icon and title"""
    step_icon = (
        [
            sg.Text(
                WIZARD_STEP_ICONS.get(step_num, "•"),
                font=(None, 36),
                pad=((0, 10), (0, 5)),
            ),
        ]
        if WIZARD_STEP_ICONS
        else []
    )
    header = [
        # step_icon +  # Doesn't cope well with Linux, remove it for now
        [
            sg.Column(
                [
                    [
                        sg.Text(
                            _t(title_key),
                            font=TITLE_FONT,
                        )
                    ],
                    (
                        [
                            sg.Text(
                                textwrap.fill(_t(desc_key), width=80),
                                font=STANDARD_FONT,
                                text_color="gray",
                            )
                        ]
                        if desc_key
                        else []
                    ),
                ],
                pad=0,
            ),
        ],
        [sg.HorizontalSeparator(pad=((0, 0), (0, 0)))],
    ]
    return header


def wizard_layouts() -> dict:
    return {
        "wizard_layout_1": create_step_header(
            1, "wizard_gui.step_1", "wizard_gui.step_1_description"
        )
        + [
            [
                sg.Push(),
                sg.Button(
                    _t("generic.remove_selected"),
                    key="-REMOVE-SOURCE-",
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
                    col0_heading=_t("config_gui.backup_sources"),
                    expand_x=True,
                    expand_y=True,
                )
            ],
            [
                sg.Push(),
                sg.Button(
                    _t("wizard_gui.handle_exclusions"),
                    key="-EXCLUSION-LISTS-MENU-",
                    font=SUBTITLE_FONT,
                ),
            ],
        ],
        "wizard_layout_2": create_step_header(
            2, "wizard_gui.step_2", "wizard_gui.step_2_description"
        )
        + [
            [
                sg.Text(_t("wizard_gui.backend"), size=(30, 1)),
                sg.Combo(
                    list(combo_boxes["backends"].values()),
                    default_value=_t("wizard_gui.select_backend"),
                    key="-BACKEND-TYPE-",
                    enable_events=True,
                    size=(40, 1),
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("config_gui.host"),
                        size=(30, 1),
                        key="-HOST-LABEL-",
                        visible=False,
                    ),
                ),
                sg.pin(
                    sg.Input(
                        key="-HOST-",
                        size=(45, 1),
                        visible=False,
                    ),
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("config_gui.path"),
                        size=(30, 1),
                        key="-PATH-LABEL-",
                    )
                ),
                sg.pin(
                    sg.Input(
                        key="-PATH-",
                        size=(45, 1),
                    )
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("generic.port") + f" ({_t('generic.optional')})",
                        size=(30, 1),
                        key="-HOST-PORT-LABEL-",
                        visible=False,
                    )
                ),
                sg.pin(
                    sg.Input(
                        key="-HOST-PORT-",
                        size=(45, 1),
                        visible=False,
                    )
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("config_gui.backup_repo_password"),
                        size=(30, 1),
                        key="-REPO-PASSWORD-LABEL-",
                    )
                ),
                sg.pin(
                    sg.Input(
                        key="repo_opts.repo_password",
                        size=(45, 1),
                        password_char="*",
                    )
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("wizard_gui.remote_username"),
                        size=(30, 1),
                        key="-SFTP-REST-USERNAME-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-SFTP-REST-USERNAME-",
                        size=(45, 1),
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("wizard_gui.remote_password"),
                        size=(30, 1),
                        key="-REST-PASSWORD-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-REST-PASSWORD-",
                        size=(45, 1),
                        password_char="*",
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("config_gui.sftp_windows_only_options"),
                        size=(80, 1),
                        key="-SFTP-AUTH-OPTIONS-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("config_gui.ssh_password"),
                        key="-SSH-PASSWORD-LABEL-",
                        size=(30, 1),
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="repo_opts.ssh_password",
                        size=(45, 1),
                        password_char="*",
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("config_gui.ssh_key_file"),
                        size=(30, 1),
                        key="-SSH-KEY-FILE-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="repo_opts.ssh_key_file",
                        size=(45, 4),
                        visible=False,
                    ),
                    shrink=False,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("wizard_gui.s3_accesskey_id"),
                        size=(30, 1),
                        key="-AWS_ACCESS_KEY_ID-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-AWS_ACCESS_KEY_ID-",
                        size=(45, 1),
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("wizard_gui.s3_secret_access_key"),
                        size=(30, 1),
                        key="-AWS_SECRET_ACCESS_KEY-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-AWS_SECRET_ACCESS_KEY-",
                        size=(45, 1),
                        password_char="*",
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("wizard_gui.azure_account_key"),
                        size=(30, 1),
                        key="-AZURE_ACCOUNT_KEY-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-AZURE_ACCOUNT_KEY-",
                        size=(45, 1),
                        password_char="*",
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("wizard_gui.azure_account_sas"),
                        size=(30, 1),
                        key="-AZURE_ACCOUNT_SAS-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-AZURE_ACCOUNT_SAS-",
                        size=(45, 1),
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("wizard_gui.azure_account_name"),
                        size=(30, 1),
                        key="-AZURE_ACCOUNT_NAME-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-AZURE_ACCOUNT_NAME-",
                        size=(45, 1),
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("wizard_gui.b2_account_id"),
                        size=(30, 1),
                        key="-B2_ACCOUNT_ID-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-B2_ACCOUNT_ID-",
                        size=(45, 1),
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("wizard_gui.b2_account_key"),
                        size=(30, 1),
                        key="-B2_ACCOUNT_KEY-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-B2_ACCOUNT_KEY-",
                        size=(45, 1),
                        password_char="*",
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("wizard_gui.google_project_id"),
                        size=(30, 1),
                        key="-GOOGLE_PROJECT_ID-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-GOOGLE_PROJECT_ID-",
                        size=(45, 1),
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("wizard_gui.google_application_credentials"),
                        size=(30, 1),
                        key="-GOOGLE_APPLICATION_CREDENTIALS-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-GOOGLE_APPLICATION_CREDENTIALS-",
                        size=(45, 1),
                        password_char="*",
                        visible=False,
                    ),
                    shrink=True,
                ),
            ],
        ],
        "wizard_layout_3": create_step_header(
            3, "wizard_gui.step_3", "wizard_gui.step_3_description"
        )
        + npbackup.gui.common_gui.scheduling_col(is_wizard=True),
        "wizard_layout_4": create_step_header(
            4, "wizard_gui.step_4", "wizard_gui.step_4_description"
        )
        + npbackup.gui.common_gui.retention_col(),
        "wizard_layout_5": create_step_header(
            5, "wizard_gui.step_5", "wizard_gui.step_5_description"
        )
        + [
            [
                sg.TabGroup(
                    [
                        [
                            sg.Tab(
                                _t("generic.identity"),
                                npbackup.gui.common_gui.per_object_monitoring_identity_col(),
                            )
                        ]
                    ]
                    + npbackup.gui.common_gui.global_monitoring_tab_group(),
                    key="-OPTIONS-TABGROUP-",
                    expand_x=True,
                    expand_y=True,
                )
            ],
        ],
        "wizard_layout_6": create_step_header(
            6, "wizard_gui.step_6", "wizard_gui.step_6_description"
        )
        + [
            [
                sg.Text(
                    f'{_t("config_gui.backups_size_checks")} ({_t("generic.optional")})',
                    font=SUBTITLE_FONT,
                ),
            ],
            [
                sg.Text(_t("config_gui.minimum_backup_size_error"), size=(60, 1)),
                sg.Input(key="backup_opts.minimum_backup_size_error", size=(8, 1)),
                sg.Combo(
                    byte_units,
                    default_value=byte_units[5],
                    key="backup_opts.minimum_backup_size_error_unit",
                ),
            ],
            [
                sg.Text(
                    f'{_t("config_gui.backups_heuristics_checks")} ({_t("generic.optional")})',
                    font=SUBTITLE_FONT,
                ),
            ],
            [
                sg.Text(
                    textwrap.fill(
                        _t("config_gui.backups_heuristics_checks_description")
                    ),
                    size=(100, 2),
                ),
            ],
            [
                sg.Text(
                    _t(
                        "config_gui.storage_heuristics_allowed_lower_standard_deviation"
                    ),
                    size=(60, 1),
                ),
                sg.Input(
                    key="backup_opts.storage_heuristics_allowed_lower_standard_deviation",
                    size=(8, 1),
                ),
            ],
            [
                sg.Text(
                    _t(
                        "config_gui.storage_heuristics_allowed_higher_standard_deviation"
                    ),
                    size=(60, 1),
                ),
                sg.Input(
                    key="backup_opts.storage_heuristics_allowed_higher_standard_deviation",
                    size=(8, 1),
                ),
            ],
            [
                sg.Text(
                    _t(
                        "config_gui.storage_heuristics_allowed_modified_files_standard_deviation"
                    ),
                    size=(60, 1),
                ),
                sg.Input(
                    key="backup_opts.storage_heuristics_allowed_modified_files_standard_deviation",
                    size=(8, 1),
                ),
            ],
            [
                sg.Text(_t("config_gui.tags"), font=SUBTITLE_FONT),
            ],
        ]
        + npbackup.gui.common_gui.backup_tags_col(),
        "wizard_layout_7": create_step_header(
            7, "wizard_gui.step_7", "wizard_gui.step_7_description"
        )
        + [
            [
                sg.Text(
                    _t("wizard_gui.wizard_ending_text"),
                    size=(80, 5),
                ),
            ],
            [
                sg.Text(
                    "",
                    key="-WIZARD-CONFIG-FILE-",
                    expand_x=True,
                    font=SUBTITLE_FONT,
                    justification="center",
                )
            ],
            [
                sg.Push(),
            ],
            [
                sg.Text(
                    _t("wizard_gui.wizard_ending_text2") + f" {SHORT_PRODUCT_NAME}!",
                    font=SUBTITLE_FONT,
                    justification="center",
                    expand_x=True,
                ),
            ],
        ],
    }


def wizard_tabs_and_breadcrumbs(wizard_layouts) -> Tuple[list, list]:
    wizard_tabs = []
    wizard_breadcrumbs = []
    for i in range(1, len(wizard_layouts) + 1):
        wizard_tabs.append(
            sg.Column(
                wizard_layouts[f"wizard_layout_{i}"],
                element_justification="L",
                key=f"-TAB{i}-",
                expand_x=True,
                expand_y=True,
            )
        )
        wizard_breadcrumbs.append(
            [
                RoundedButton(
                    f" {i} ",
                    border_width=0,
                    key=f"-BREADCRUMB-{i}-",
                    btn_width=40,
                    btn_height=40,
                    radius=20,
                    font=TITLE_FONT,
                ),
                sg.Text(_t(f"wizard_gui.step_{i}")),
            ]
        )
    return wizard_tabs, wizard_breadcrumbs


def wizard_layout(wizard_tabs, wizard_breadcrumbs) -> List[list]:
    return [
        [
            sg.Image(OEM_LOGO, subsample=2),
            sg.Column(
                [
                    [
                        sg.Text(
                            _t("wizard_gui.welcome") + f" {SHORT_PRODUCT_NAME}",
                            font=("Helvetica", 16),
                        ),
                    ],
                    [
                        sg.Text(_t("wizard_gui.welcome_description")),
                    ],
                ],
            ),
        ],
        [
            sg.Column(
                wizard_breadcrumbs, element_justification="L", vertical_alignment="top"
            ),
            sg.Column(
                [wizard_tabs], expand_x=True, expand_y=True, vertical_alignment="top"
            ),
        ],
        [
            sg.Column(
                [
                    [
                        sg.Button(
                            f'{_t("generic.cancel").capitalize()}',
                            key="-PREVIOUS-",
                            border_width=0,
                            font=TITLE_FONT,
                        ),
                        sg.Button(
                            f'{_t("generic.next").capitalize()} ▶',
                            key="-NEXT-",
                            border_width=0,
                            font=TITLE_FONT,
                        ),
                    ],
                ],
                element_justification="C",
                expand_x=True,
                expand_y=False,
            )
        ],
    ]


def start_wizard(full_config: dict, config_file: str):
    # wizard tabs count
    wizard_tabs, wizard_breadcrumbs = wizard_tabs_and_breadcrumbs(wizard_layouts())
    NUMBER_OF_TABS = len(wizard_tabs)
    current_tab = 1

    wizard = sg.Window(
        f"{SHORT_PRODUCT_NAME} Wizard",
        layout=wizard_layout(wizard_tabs, wizard_breadcrumbs),
        element_justification="L",
        size=(int(1000 * WINDOW_SCALING), int(620 * WINDOW_SCALING)),
        no_titlebar=False,
        grab_anywhere=True,
        auto_size_text=True,
        auto_size_buttons=True,
        resizable=True,
        default_element_size=(12, 1),
        default_button_element_size=(16, 1),
    )

    lasttab = 1

    def set_active_tab(active_number):
        nonlocal lasttab
        lasttab = active_number if active_number > lasttab else lasttab
        for tab_index in range(1, NUMBER_OF_TABS + 1):
            if tab_index != active_number:
                wizard[f"-TAB{tab_index}-"].Update(visible=False)
                wizard[f"-BREADCRUMB-{tab_index}-"].Update(
                    button_color=(sg.theme_button_color()[0], None)
                )
                wizard[f"-BREADCRUMB-{tab_index}-"].update_color(
                    "#212AA7" if tab_index < active_number else "#84AAFF"
                )
        wizard[f"-TAB{active_number}-"].Update(visible=True)
        wizard[f"-BREADCRUMB-{active_number}-"].Update(
            button_color=(sg.theme_button_color()[0], None)
        )
        wizard[f"-BREADCRUMB-{active_number}-"].update_color(sg.theme_button_color()[1])
        wizard["-NEXT-"].update(
            f'✓ {_t("generic.finish").capitalize()}'
            if current_tab == NUMBER_OF_TABS
            else f'{_t("generic.next").capitalize()} ▶'
        )
        wizard["-PREVIOUS-"].update(
            f'◀ {_t("generic.cancel").capitalize()}'
            if current_tab == 1
            else f'◀ {_t("generic.previous").capitalize()}'
        )

    def set_active_backend_type(backend_type):
        """
        Show backends inputs depending on what backend type is selected
        """
        existing_keys = [
            "-HOST-LABEL-",
            "-HOST-",
            "-HOST-PORT-LABEL-",
            "-HOST-PORT-",
            "-SFTP-REST-USERNAME-LABEL-",
            "-SFTP-REST-USERNAME-",
            "-SFTP-AUTH-OPTIONS-LABEL-",
            "-SSH-PASSWORD-LABEL-",
            "repo_opts.ssh_password",
            "-SSH-KEY-FILE-LABEL-",
            "repo_opts.ssh_key_file",
            "-REST-PASSWORD-LABEL-",
            "-REST-PASSWORD-",
            "-AWS_ACCESS_KEY_ID-LABEL-",
            "-AWS_SECRET_ACCESS_KEY-LABEL-",
            "-AWS_ACCESS_KEY_ID-",
            "-AWS_SECRET_ACCESS_KEY-",
            "-AZURE_ACCOUNT_KEY-LABEL-",
            "-AZURE_ACCOUNT_SAS-LABEL-",
            "-AZURE_ACCOUNT_NAME-LABEL-",
            "-AZURE_ACCOUNT_KEY-",
            "-AZURE_ACCOUNT_SAS-",
            "-AZURE_ACCOUNT_NAME-",
            "-B2_ACCOUNT_ID-LABEL-",
            "-B2_ACCOUNT_KEY-LABEL-",
            "-B2_ACCOUNT_ID-",
            "-B2_ACCOUNT_KEY-",
            "-GOOGLE_PROJECT_ID-LABEL-",
            "-GOOGLE_APPLICATION_CREDENTIALS-LABEL-",
            "-GOOGLE_PROJECT_ID-",
            "-GOOGLE_APPLICATION_CREDENTIALS-",
        ]
        for key in existing_keys:
            if "LABEL" in key:
                wizard[key].update(visible=False)
            else:
                wizard[key].update("", visible=False)

        if backend_type in ("sftp", "rest"):
            wizard["-SFTP-REST-USERNAME-LABEL-"].update(visible=True)
            wizard["-SFTP-REST-USERNAME-"].update(visible=True)
        if backend_type == "sftp":
            wizard["-SFTP-AUTH-OPTIONS-LABEL-"].update(visible=True)
            wizard["-SSH-PASSWORD-LABEL-"].update(visible=True)
            wizard["repo_opts.ssh_password"].update(visible=True)
            wizard["-SSH-KEY-FILE-LABEL-"].update(visible=True)
            wizard["repo_opts.ssh_key_file"].update(visible=True)
        if backend_type == "rest":
            wizard["-REST-PASSWORD-LABEL-"].update(visible=True)
            wizard["-REST-PASSWORD-"].update(visible=True)
        if backend_type == "s3":
            wizard["-AWS_ACCESS_KEY_ID-LABEL-"].update(visible=True)
            wizard["-AWS_ACCESS_KEY_ID-"].update(visible=True)
            wizard["-AWS_SECRET_ACCESS_KEY-LABEL-"].update(visible=True)
            wizard["-AWS_SECRET_ACCESS_KEY-"].update(visible=True)
        if backend_type == "azure":
            wizard["-AZURE_ACCOUNT_KEY-LABEL-"].update(visible=True)
            wizard["-AZURE_ACCOUNT_KEY-"].update(visible=True)
            wizard["-AZURE_ACCOUNT_SAS-LABEL-"].update(visible=True)
            wizard["-AZURE_ACCOUNT_SAS-"].update(visible=True)
            wizard["-AZURE_ACCOUNT_NAME-LABEL-"].update(visible=True)
            wizard["-AZURE_ACCOUNT_NAME-"].update(visible=True)
        if backend_type == "b2":
            wizard["-B2_ACCOUNT_ID-LABEL-"].update(visible=True)
            wizard["-B2_ACCOUNT_ID-"].update(visible=True)
            wizard["-B2_ACCOUNT_KEY-LABEL-"].update(visible=True)
            wizard["-B2_ACCOUNT_KEY-"].update(visible=True)
        if backend_type == "gs":
            wizard["-GOOGLE_PROJECT_ID-LABEL-"].update(visible=True)
            wizard["-GOOGLE_PROJECT_ID-"].update(visible=True)
            wizard["-GOOGLE_APPLICATION_CREDENTIALS-LABEL-"].update(visible=True)
            wizard["-GOOGLE_APPLICATION_CREDENTIALS-"].update(visible=True)
        if backend_type != "local":
            wizard["-HOST-LABEL-"].update(visible=True)
            wizard["-HOST-"].update(visible=True)
            wizard["-HOST-PORT-LABEL-"].update(visible=True)
            wizard["-HOST-PORT-"].update(visible=True)
        wizard["-BACKEND-TYPE-"].update(value=combo_boxes["backends"][backend_type])

    wizard.finalize()
    # Let's load our previous config values for wizard
    # We'll use repo default
    npbackup.gui.common_gui_logic.update_object_gui(
        window=wizard,
        full_config=full_config,
        object_type=OBJECT_TYPE,
        object_name=OBJECT_NAME,
        unencrypted=False,
        is_wizard=True,  # Since we have less keys than full config interface
    )

    npbackup.gui.common_gui_logic.update_global_gui(
        window=wizard,
        full_config=full_config,
        unencrypted=False,
        is_wizard=True,  # Since we have less keys than full config interface
    )

    # We need to manually update backend config fields
    try:
        if full_config.g(
            f"{OBJECT_TYPE}.{OBJECT_NAME}.repo_opts.repo_password", default=None
        ):
            wizard["repo_opts.repo_password"].update(
                npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
            )
        if full_config.g(
            f"{OBJECT_TYPE}.{OBJECT_NAME}.repo_opts.ssh_password", default=None
        ):
            wizard["repo_opts.ssh_password"].update(
                npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
            )

        repo_uri = full_config.g(f"{OBJECT_TYPE}.{OBJECT_NAME}.repo_uri", default="")
        if repo_uri:
            repo_uri_dict = parse_restic_repo(repo_uri)
            backend_type = repo_uri_dict.get("backend_type")
            set_active_backend_type(backend_type)

            # Show the full URI in the repo_uri field so the user sees exactly
            # what is stored in the config.
            wizard["-PATH-"].update(repo_uri_dict.get("path") or "")
            wizard["-HOST-"].update(repo_uri_dict.get("host") or "")

            # Port field (relevant for REST and SFTP)
            wizard["-HOST-PORT-"].update(str(repo_uri_dict.get("port") or ""))

            if backend_type == "sftp":
                wizard["-SFTP-REST-USERNAME-"].update(
                    repo_uri_dict.get("username") or ""
                )
                wizard["repo_opts.ssh_password"].update(
                    npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                )
            elif backend_type == "rest":
                wizard["-SFTP-REST-USERNAME-"].update(
                    repo_uri_dict.get("username") or ""
                )
                if repo_uri_dict.get("password"):
                    wizard["-REST-PASSWORD-"].update(
                        npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                    )
            elif backend_type == "b2":
                wizard["-B2_ACCOUNT_ID-"].update(
                    npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                )
                wizard["-B2_ACCOUNT_KEY-"].update(
                    npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                )
            elif backend_type == "azure":
                wizard["-AZURE_ACCOUNT_NAME-"].update(
                    npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                )
                wizard["-AZURE_ACCOUNT_KEY-"].update(
                    npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                )
                wizard["-AZURE_ACCOUNT_SAS-"].update(
                    npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                )
            elif backend_type == "gs":
                wizard["-GOOGLE_PROJECT_ID-"].update(
                    npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                )
                wizard["-GOOGLE_APPLICATION_CREDENTIALS-"].update(
                    npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                )
            elif backend_type == "s3":
                wizard["-AWS_ACCESS_KEY_ID-"].update(
                    npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                )
                wizard["-AWS_SECRET_ACCESS_KEY-"].update(
                    npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                )

    except (AttributeError, IndexError, KeyError, ValueError) as exc:
        logger.error(f"Cannot read backend configuration: {exc}")

    event, values = wizard.read(timeout=0.1)
    set_active_tab(1)
    npbackup.gui.common_gui_logic.update_monitoring_visibility(
        window=wizard, values=values
    )

    npbackup.gui.common_gui_logic.update_zabbix_option_visibility(
        window=wizard, values=values
    )

    retention_policies_presets = (
        npbackup.gui.common_gui_logic.get_retention_policies_presets(full_config)
    )
    current_policy_name = npbackup.gui.common_gui_logic.retention_policy_preset_name(
        full_config, OBJECT_TYPE, OBJECT_NAME, retention_policies_presets
    )
    wizard["-RETENTION-POLICIES-"].update(
        values=list(retention_policies_presets.keys())
    )
    if current_policy_name:
        wizard["-RETENTION-POLICIES-"].update(
            set_to_index=list(retention_policies_presets.keys()).index(
                current_policy_name
            )
        )
    else:
        wizard["-RETENTION-POLICIES-"].update(
            _t("config_gui.select_a_retention_policy_preset")
        )

    wizard["-WIZARD-CONFIG-FILE-"].update(str(config_file))

    while True:
        event, values = wizard.read()
        if event == sg.WIN_CLOSED or event == _t("generic.cancel"):
            break

        ## Handle most lists add/remove objects
        npbackup.gui.common_gui_logic.handle_gui_events(
            full_config=full_config,
            window=wizard,
            event=event,
            values=values,
            object_type=OBJECT_TYPE,
            object_name=OBJECT_NAME,
            unencrypted=False,
            is_wizard=True,
        )

        ## WIZARD STEP 1 ##

        if event == "-EXCLUSION-LISTS-MENU-":
            full_config = wizard_exclusion_window(full_config)

        if current_tab == 1:
            if len(wizard["backup_opts.paths"].TreeData.tree_dict.values()) < 2:
                result = sg.popup(
                    _t("config_gui.backup_source_should_not_be_empty")
                    + ". "
                    + _t("generic.are_you_sure"),
                    custom_text=(_t("generic.no"), _t("generic.yes")),
                    keep_on_top=True,
                    icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                    title=_t("generic.warning").capitalize(),
                    line_width=100,
                    modal=True,
                )
                if result != _t("generic.yes"):
                    continue

        ## WIZARD STEP 2 ##
        if event == "-BACKEND-TYPE-":
            backend_type = get_key_from_value(
                combo_boxes["backends"], values["-BACKEND-TYPE-"]
            )
            set_active_backend_type(backend_type)
            continue

        if current_tab == 2:
            current_backend = get_key_from_value(
                combo_boxes["backends"], values["-BACKEND-TYPE-"]
            )
            if current_backend not in combo_boxes["backends"].keys():
                result = sg.popup(
                    _t("wizard_gui.please_select_a_valid_backend"),
                    custom_text=(_t("generic.no"), _t("generic.yes")),
                    keep_on_top=True,
                    icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                    title=_t("generic.warning").capitalize(),
                    line_width=100,
                    modal=True,
                )
                if result != _t("generic.yes"):
                    continue

            if (not values["-HOST-"] and current_backend != "local") or (
                values["-PATH-"] == "" and current_backend == "local"
            ):
                result = sg.popup(
                    _t("config_gui.repo_uri_should_not_be_empty")
                    + ". "
                    + _t("generic.are_you_sure"),
                    custom_text=(_t("generic.no"), _t("generic.yes")),
                    keep_on_top=True,
                    icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                    title=_t("generic.warning").capitalize(),
                    line_width=100,
                    modal=True,
                )
                if result != _t("generic.yes"):
                    continue
            if not values["repo_opts.repo_password"]:
                result = sg.popup(
                    _t("config_gui.repo_password_should_not_be_empty")
                    + ". "
                    + _t("generic.are_you_sure"),
                    custom_text=(_t("generic.no"), _t("generic.yes")),
                    keep_on_top=True,
                    icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                    title=_t("generic.warning").capitalize(),
                    line_width=100,
                    modal=True,
                )
                if result != _t("generic.yes"):
                    continue
            # If the password field contains the placeholder, we assume the user wants to keep the
            # existing password, so we don't check complexity in this case
            if not values[
                "repo_opts.repo_password"
            ] == npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER and not password_complexity(
                values["repo_opts.repo_password"]
            ):
                result = sg.popup(
                    _t("config_gui.password_too_simple")
                    + ". "
                    + _t("generic.are_you_sure"),
                    custom_text=(_t("generic.no"), _t("generic.yes")),
                    keep_on_top=True,
                    icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                    title=_t("generic.warning").capitalize(),
                    line_width=100,
                    modal=True,
                )
                if result != _t("generic.yes"):
                    continue
        ## WIZARD STEP 3 ##

        ## WIZARD STEP 4 ##

        ## WIZARD STEP 5 ##
        if current_tab == 5:
            if npbackup.gui.common_gui_logic.validate_email_addresses(wizard) is False:
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

        ## WIZARD STEP 6 ##

        ## WIZARD STEP 7 ##
        if event == "-NEXT-" and current_tab == NUMBER_OF_TABS:
            # Retrieve the current backend selection and the URI the user has entered.
            current_backend = get_key_from_value(
                combo_boxes["backends"], values["-BACKEND-TYPE-"]
            )
            encrypted_env_variables = full_config.g(
                f"{OBJECT_TYPE}.{OBJECT_NAME}.env.encrypted_env_variables", default={}
            )

            repo_uri_dict = {
                "backend_type": current_backend,
                "path": values.get("-PATH-", "").strip(),
            }
            if values.get("-HOST-", "").strip():
                repo_uri_dict["host"] = values.get("-HOST-", "").strip()
            port_str = values.get("-HOST-PORT-", "").strip()
            if port_str.isdigit():
                repo_uri_dict["port"] = int(port_str)

            # For SFTP and REST the username lives inside the URI itself
            # for REST, the passwword lives inside the URI too.
            # Parse the current URI, patch in whatever the user
            # has typed in the dedicated credential fields, then rebuild a
            # well-formed URI via build_restic_uri so we never save a malformed
            # or credential-less URI.
            if current_backend in ("sftp", "rest"):
                # Apply username from the dedicated GUI field
                username = values.get("-SFTP-REST-USERNAME-", "").strip()
                repo_uri_dict["username"] = username or None
            # SFTP password lives outside of the repo uri, so we need to put it in config file
            if current_backend == "rest":
                password = values.get("-REST-PASSWORD-", "")
                if (
                    password
                    and password
                    != npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                ):
                    # Reconstruct repo uri dict
                    repo_uri_dict["password"] = password

            elif current_backend == "b2":
                if (
                    values["-B2_ACCOUNT_ID-"]
                    != npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                ):
                    encrypted_env_variables["B2_ACCOUNT_ID"] = values["-B2_ACCOUNT_ID-"]
                if (
                    values["-B2_ACCOUNT_KEY-"]
                    != npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                ):
                    encrypted_env_variables["B2_ACCOUNT_KEY"] = values[
                        "-B2_ACCOUNT_KEY-"
                    ]

            elif current_backend == "azure":
                if (
                    values["-AZURE_ACCOUNT_KEY-"]
                    != npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                ):
                    encrypted_env_variables["AZURE_ACCOUNT_KEY"] = values[
                        "-AZURE_ACCOUNT_KEY-"
                    ]
                if (
                    values["-AZURE_ACCOUNT_SAS-"]
                    != npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                ):
                    encrypted_env_variables["AZURE_ACCOUNT_SAS"] = values[
                        "-AZURE_ACCOUNT_SAS-"
                    ]
                if (
                    values["-AZURE_ACCOUNT_NAME-"]
                    != npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                ):
                    encrypted_env_variables["AZURE_ACCOUNT_NAME"] = values[
                        "-AZURE_ACCOUNT_NAME-"
                    ]

            elif current_backend == "s3":
                if (
                    values["-AWS_ACCESS_KEY_ID-"]
                    != npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                ):
                    encrypted_env_variables["AWS_ACCESS_KEY_ID"] = values[
                        "-AWS_ACCESS_KEY_ID-"
                    ]
                if (
                    values["-AWS_SECRET_ACCESS_KEY-"]
                    != npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                ):
                    encrypted_env_variables["AWS_SECRET_ACCESS_KEY"] = values[
                        "-AWS_SECRET_ACCESS_KEY-"
                    ]

            elif current_backend == "gs":
                if (
                    values["-GOOGLE_PROJECT_ID-"]
                    != npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                ):
                    encrypted_env_variables["GOOGLE_PROJECT_ID"] = values[
                        "-GOOGLE_PROJECT_ID-"
                    ]
                if (
                    values["-GOOGLE_APPLICATION_CREDENTIALS-"]
                    != npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                ):
                    encrypted_env_variables["GOOGLE_APPLICATION_CREDENTIALS"] = values[
                        "-GOOGLE_APPLICATION_CREDENTIALS-"
                    ]

            # Now reassemble repo_uri from it's parts
            try:
                repo_uri = build_restic_uri(repo_uri_dict)
            except (KeyError, ValueError) as exc:
                logger.warning(
                    f"Could not rebuild repo URI from components: {exc}. Saving raw value."
                )

            full_config = npbackup.gui.common_gui_logic.update_config_dict(
                wizard,
                full_config,
                object_type=OBJECT_TYPE,
                object_name=OBJECT_NAME,
                values=values,
                is_wizard=True,
            )

            # Now that we updated the config dict with all values including the
            # repo_uri which has been anonymized, we need to patch the full_config dict
            full_config.s(f"{OBJECT_TYPE}.{OBJECT_NAME}.repo_uri", repo_uri)
            full_config.s(
                f"{OBJECT_TYPE}.{OBJECT_NAME}.env.encrypted_env_variables",
                encrypted_env_variables,
            )

            create_task = True
            if os.name == "nt":
                if not is_admin():
                    result = sg.popup(
                        _t("config_gui.elevate_uac_tasks"),
                        custom_text=(_t("generic.no"), _t("generic.yes")),
                        keep_on_top=True,
                        icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                        title=_t("generic.information").capitalize(),
                        line_width=100,
                    )
                    if result != _t("generic.yes"):
                        create_task = False

            if create_task:
                result, full_config = (
                    npbackup.gui.common_gui_logic.create_scheduled_task(
                        values, full_config, config_file
                    )
                )
                if not result:
                    result = sg.popup(
                        _t("wizard_gui.do_you_still_want_to_save"),
                        custom_text=(_t("generic.no"), _t("generic.yes")),
                        keep_on_top=True,
                        icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                        title=_t("generic.warning").capitalize(),
                        line_width=100,
                    )
                    if result == _t("generic.no"):
                        break

            result = npbackup.configuration.save_config(config_file, full_config)
            if result:
                sg.popup(_t("config_gui.configuration_saved"), keep_on_top=True)
                break
            popup_error(_t("config_gui.cannot_save_configuration"))
            continue

        ## WIZARD NAVIGATION #
        if event == "-NEXT-":
            if current_tab < NUMBER_OF_TABS:
                current_tab += 1
                set_active_tab(current_tab)
            elif current_tab == NUMBER_OF_TABS:
                sg.popup(
                    _t("wizard_gui.thank_you") + f" {SHORT_PRODUCT_NAME}",
                    keep_on_top=True,
                )
                # We won't break here since we need to save config from gui
        if event == "-PREVIOUS-":
            if current_tab > 1:
                current_tab -= 1
                set_active_tab(current_tab)
            elif current_tab == 1:
                break
        if "-BREADCRUMB-" in event:
            current_tab = int(event.split("-")[-2])
            set_active_tab(current_tab)

        # Loading scheduled tasks for step 4 need to be done after tab nav
        if (
            event in ("-NEXT-", "-PREVIOUS-") and current_tab == 3
        ) or event == "-BREADCRUMB-3-":
            if os.name == "nt":
                if not is_admin():
                    result = sg.popup(
                        _t("config_gui.elevate_uac_tasks"),
                        custom_text=(_t("generic.no"), _t("generic.yes")),
                        keep_on_top=True,
                        icon=sg.SYSTEM_TRAY_MESSAGE_ICON_WARNING,
                        title=_t("generic.information").capitalize(),
                        line_width=100,
                    )
                    if result != _t("generic.yes"):
                        continue
            # run thread after window is finalized and active tab is set so controls get expanded
            # Limit scheduled task to backup operation in wizard
            thread = (
                npbackup.gui.common_gui_logic.read_existing_scheduled_tasks_threaded(
                    config_file, full_config, "backup"
                )
            )
            tasks = WaitWindow(
                thread, message=_t("config_gui.reading_tasks")
            ).wait_for_thread_result()

            if tasks:
                npbackup.gui.common_gui_logic.update_task_ui_for_object(
                    window=wizard,
                    full_config=full_config,
                    task=tasks[0],
                    is_wizard=True,
                )

        ## END NAVIGATION ##
    wizard.close()
    return full_config, config_file


if __name__ == "__main__":
    start_wizard(
        npbackup.configuration.get_default_config(), "npbackup-wizard-test.conf"
    )
