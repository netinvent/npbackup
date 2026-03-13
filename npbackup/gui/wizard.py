#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.wizard"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"


from typing import List, Optional, Tuple
import textwrap
from pathlib import Path
from logging import getLogger
import ofunctions.logger_utils
from ruamel.yaml.comments import CommentedMap
from ofunctions.process import kill_childs
from ofunctions.threading import threaded
from ofunctions.misc import BytesConverter
import FreeSimpleGUI as sg
import npbackup.configuration
from resources.customization import (
    OEM_LOGO,
    OEM_ICON,
    FILE_ICON,
    FOLDER_ICON,
    SHORT_PRODUCT_NAME,
    NON_INHERITED_ICON,
    INFO_ICON,
    WIZARD_STEP_ICONS,
)

from npbackup.gui.constants import combo_boxes, byte_units
from npbackup.core.i18n_helper import _t, _locale
from ofunctions.misc import get_key_from_value

# from npbackup.gui.buttons import RoundedButton
from FreeSimpleGUI import Button as RoundedButton
import npbackup.configuration
from npbackup.gui.ttk_theme import TITLE_FONT, SUBTITLE_FONT
import npbackup.gui.common_gui
from npbackup.gui.helpers import WaitWindow, popup_error, password_complexity
import npbackup.gui.common_gui_logic
import npbackup.configuration as configuration

sg.set_options(icon=OEM_ICON)

logger = getLogger()


def create_step_header(step_num: int, title_key: str, desc_key: str = None) -> list:
    """Create a consistent step header with icon and title"""
    step_icon = (
        [
            sg.Text(
                WIZARD_STEP_ICONS.get(step_num, "•"),
                font=("Segoe UI Emoji", 24),
                pad=((0, 10), (0, 5)),
            ),
        ]
        if WIZARD_STEP_ICONS
        else []
    )
    header = [
        step_icon
        + [
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
                                _t(desc_key),
                                font=SUBTITLE_FONT,
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
        [sg.HorizontalSeparator(pad=((0, 0), (5, 5)))],
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
                    col0_heading=_t("config_gui.backup_sources"),
                    expand_x=True,
                    expand_y=True,
                )
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
                        _t("config_gui.backup_repo_uri"),
                        size=(30, 1),
                        key="-BACKEND-URI-LABEL-",
                    )
                ),
                sg.pin(
                    sg.Input(
                        key="repo_uri",
                        size=(45, 1),
                    )
                ),
            ],
            [
                sg.pin(
                    sg.Text(
                        _t("config_gui.backup_repo_password"),
                        size=(30, 1),
                        key="-BACKEND-REPO-PASSWORD-LABEL-",
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
                        key="-SFTP-REST-PASSWORD-LABEL-",
                        visible=False,
                    ),
                    shrink=True,
                ),
                sg.pin(
                    sg.Input(
                        key="-SFTP-REST-PASSWORD-",
                        size=(45, 1),
                        visible=False,
                    ),
                    shrink=True,
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
                sg.Text(_t("config_gui.tags"), font=SUBTITLE_FONT),
            ],
        ]
        + npbackup.gui.common_gui.backup_tags_col()
        + [
            [
                sg.Text(
                    f"{_t("generic.minimum_size")} ({_t("generic.optional")})",
                    font=SUBTITLE_FONT,
                ),
            ],
            [
                sg.Text(_t("config_gui.minimum_backup_size_error")),
                sg.Input(key="backup_opts.minimum_backup_size_error", size=(8, 1)),
                sg.Combo(
                    byte_units,
                    default_value=byte_units[5],
                    key="backup_opts.minimum_backup_size_error_unit",
                ),
            ],
        ],
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
                    # btn_size=(30, 30),
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
                        RoundedButton(
                            f"{_t("generic.cancel").capitalize()}",
                            key="-PREVIOUS-",
                            border_width=0,
                            font=TITLE_FONT,
                        ),
                        RoundedButton(
                            f"{_t("generic.next").capitalize()} ▶",
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
        size=(900, 600),
        element_justification="L",
        no_titlebar=False,
        grab_anywhere=True,
        auto_size_buttons=True,
    )

    def set_active_tab(active_number):
        for tab_index in range(1, NUMBER_OF_TABS + 1):
            if tab_index != active_number:
                wizard[f"-TAB{tab_index}-"].Update(visible=False)
                wizard[f"-BREADCRUMB-{tab_index}-"].Update(
                    button_color=(sg.theme_button_color())
                )
        wizard[f"-TAB{active_number}-"].Update(visible=True)
        wizard[f"-BREADCRUMB-{active_number}-"].Update(
            button_color=(sg.theme_button_color()[1], sg.theme_button_color()[0])
        )

        wizard["-NEXT-"].update(
            f"✓ {_t("generic.finish").capitalize()}"
            if current_tab == NUMBER_OF_TABS
            else f"{_t("generic.next").capitalize()} ▶"
        )
        wizard["-PREVIOUS-"].update(
            f"◀ {_t('generic.cancel').capitalize()}"
            if current_tab == 1
            else f"◀ {_t('generic.previous').capitalize()}"
        )

    def set_active_backend_type(backend_type):
        """
        Show backends inputs depending on what backend type is selected
        """
        existing_keys = [
            "-SFTP-REST-USERNAME-LABEL-",
            "-SFTP-REST-PASSWORD-LABEL-",
            "-SFTP-REST-USERNAME-",
            "-SFTP-REST-PASSWORD-",
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
            wizard["-SFTP-REST-PASSWORD-LABEL-"].update(visible=True)
            wizard["-SFTP-REST-USERNAME-"].update(visible=True)
            wizard["-SFTP-REST-PASSWORD-"].update(visible=True)
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
        if backend_type == "gcs":
            wizard["-GOOGLE_PROJECT_ID-LABEL-"].update(visible=True)
            wizard["-GOOGLE_PROJECT_ID-"].update(visible=True)
            wizard["-GOOGLE_APPLICATION_CREDENTIALS-LABEL-"].update(visible=True)
            wizard["-GOOGLE_APPLICATION_CREDENTIALS-"].update(visible=True)

    wizard.finalize()
    # Let's load our previous config values for wizard
    # We'll use repo default
    npbackup.gui.common_gui_logic.update_object_gui(
        window=wizard,
        full_config=full_config,
        object_type="repos",
        object_name="default",
        unencrypted=False,
        is_wizard=True,  # Since we have less keys than full config interface
    )
    npbackup.gui.common_gui_logic.update_global_gui(
        window=wizard,
        full_config=full_config,
        unencrypted=False,
        is_wizard=True,
    )

    event, values = wizard.read(timeout=0.1)
    set_active_tab(1)
    npbackup.gui.common_gui_logic.update_monitoring_visibility(
        window=wizard, values=values
    )

    try:
        retention_policies = list(full_config.g("presets.retention_policies"))
    except Exception:
        # We might need to fallback to integrated presets in constants
        retention_policies = npbackup.configuration.get_default_config().g(
            "presets.retention_policy"
        )

    # retention_policies = list(combo_boxes["retention_options"].values())
    retention_policies_list = list(retention_policies.keys())
    retention_policies_list = [
        _t(f"wizard_gui.{policy}") for policy in retention_policies_list
    ]

    wizard["-RETENTION-POLICIES-"].update(values=retention_policies_list)
    wizard["-RETENTION-POLICIES-"].update(set_to_index=0)
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
        )

        ## WIZARD STEP 1 ##

        ## WIZARD STEP 2 ##

        if event == "-BACKEND-TYPE-":
            backend_type = get_key_from_value(
                combo_boxes["backends"], values["-BACKEND-TYPE-"]
            )
            set_active_backend_type(backend_type)

        ## WIZARD STEP 3 ##

        ## WIZARD STEP 4 ##

        ## WIZARD STEP 5 ##
        if event == "-NEXT-" and current_tab == 5:
            if not npbackup.gui.common_gui_logic.validate_email_addresses(wizard):
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
            full_config = npbackup.gui.common_gui_logic.update_config_dict(
                wizard,
                full_config,
                object_type="repos",
                object_name="default",
                values=values,
                is_wizard=True,
            )

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

        ## WIZARD NAVIGATION #
        if event == "-NEXT-":
            # Have preflight checks here

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
            if current_tab == 2:
                if not values["repo_uri"]:
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
                if not password_complexity(values["repo_opts.repo_password"]):
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
        # TODO: prev and next into 1
        if (
            event in ("-NEXT-", "-PREVIOUS-") and current_tab == 3
        ) or event == "-BREADCRUMB-3-":
            # run thread after window is finalized and active tab is set so controls get expanded
            thread = (
                npbackup.gui.common_gui_logic.read_existing_scheduled_tasks_threaded(
                    config_file, full_config
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
    return full_config, config_file


if __name__ == "__main__":
    start_wizard(
        npbackup.configuration.get_default_config(), "npbackup-wizard-test.conf"
    )
