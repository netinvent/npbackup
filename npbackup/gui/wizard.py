#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.wizard"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"


from typing import List, Optional, Tuple
import textwrap
from pathlib import Path
from logging import getLogger
import ofunctions.logger_utils
from datetime import datetime, timezone
import dateutil
from time import sleep
from ruamel.yaml.comments import CommentedMap
import atexit
from ofunctions.process import kill_childs
from ofunctions.threading import threaded
from ofunctions.misc import BytesConverter
import FreeSimpleGUI as sg
from reskinner import reskin
import _tkinter
import npbackup.configuration
import npbackup.common
from resources.customization import (
    LOOK_AND_FEEL_TABLE,
    OEM_LOGO,
    BG_COLOR_LDR,
    TXT_COLOR_LDR,
    SIMPLEGUI_THEME,
    THEME_CHOOSER_ICON,
)

from npbackup.gui.constants import combo_boxes, byte_units
from npbackup.core.i18n_helper import _t
from npbackup.gui.buttons import RoundedButton


sg.LOOK_AND_FEEL_TABLE["CLEAR"] = LOOK_AND_FEEL_TABLE["CLEAR"]
sg.LOOK_AND_FEEL_TABLE["DARK"] = LOOK_AND_FEEL_TABLE["DARK"]
sg.theme(SIMPLEGUI_THEME)
logger = getLogger()

wizard_layouts = {
    "wizard_layout_1": [
        [
            sg.Text(
                textwrap.fill(f"{_t('wizard_gui.select_backup_sources')}", 70),
                size=(None, None),
                expand_x=True,
                justification="c",
            ),
        ],
        [
            sg.Input(visible=False, key="--ADD-PATHS-FILE--", enable_events=True),
            sg.FilesBrowse(
                "",  # _t("generic.add_files"
                target="--ADD-PATHS-FILE--",
                key="--ADD-PATHS-FILE-BUTTON--",
                border_width=0,
                # button_color=(None, sg.LOOK_AND_FEEL_TABLE[SIMPLEGUI_THEME]["BACKGROUND"])
            ),
            sg.Input(visible=False, key="--ADD-PATHS-FOLDER--", enable_events=True),
            sg.FolderBrowse(
                "",  # _t("generic.add_folder"),
                target="--ADD-PATHS-FOLDER--",
                key="--ADD-PATHS-FOLDER-BUTTON--",
                border_width=0,
                # button_color=(None, sg.LOOK_AND_FEEL_TABLE[SIMPLEGUI_THEME]["BACKGROUND"])
            ),
            sg.Button(
                "",  # _t("generic.add_manually"),
                key="--ADD-PATHS-MANUALLY--",
                border_width=0,
                # button_color=(None, sg.LOOK_AND_FEEL_TABLE[SIMPLEGUI_THEME]["BACKGROUND"])
            ),
            sg.Button(
                "",  # _t("generic.remove_selected"),
                key="--REMOVE-PATHS--",
                border_width=0,
                # button_color=(None, sg.LOOK_AND_FEEL_TABLE[SIMPLEGUI_THEME]["BACKGROUND"])
            ),
            sg.Button(
                "",
                key="-ADD-WINDOWS-SYSTEM-",
                border_width=0,
            ),
            sg.Button(
                "",
                key="-ADD-HYPERV-",
                border_width=0,
            ),
            sg.Button(
                "",
                key="-ADD-KVM-",
                border_width=0,
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
                header_text_color=TXT_COLOR_LDR,
                header_background_color=BG_COLOR_LDR,
            )
        ],
    ],
    "wizard_layout_2": [
        [sg.Text(_t("wizard_gui.backup_location"), font=("Helvetica", 16))],
        [
            sg.Text(_t("wizard_gui.backend"), size=(20, 1)), sg.Combo(list(combo_boxes["backends"].values()), default_value=next(iter(combo_boxes["backends"])), key="-BACKEND-TYPE-", enable_events=True, size=(40, 1))
        ],
    ],
    "wizard_layout_3": [
        [
            sg.Column(
                [
                    [
                        sg.Column(
                            [
                                [sg.Button("+", key="--ADD-BACKUP-TAG--", size=(3, 1))],
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
        ],
    ],
    "wizard_layout_4": [
        [sg.T(_t("wizard_gui.retention_settings"), font=("Helvetica", 16))],
        [
            sg.Combo(
                values=list(combo_boxes["retention_options"].values()),
                default_value=next(iter(combo_boxes["retention_options"])),
                key="-RETENTION-TYPE-",
                enable_events=True,
            )
        ],
    ],
    "wizard_layout_5": [
        [sg.Text(_t("wizard_gui.end_user_experience"), font=("Helvetica", 16))],
        [
            sg.Checkbox(
                _t("wizard_gui.disable_config_button"),
                key="-DISABLE-CONFIG-BUTTON-",
                default=True,
            )
        ],
    ],
    "wizard_layout_6": [
        [sg.Text(_t("wizard_gui.end_user_experience"), font=("Helvetica", 16))],
    ],
}

wizard_tabs = []
wizard_breadcrumbs = []
for i in range(1, len(wizard_layouts)):
    wizard_tabs.append(
        sg.Column(
            wizard_layouts[f"wizard_layout_{i}"],
            element_justification="L",
            key=f"-TAB{i}-",
        )
    )
    wizard_breadcrumbs.append(
        [
            RoundedButton(
                str(i),
                button_color=("#FAFAFA", "#ADADAD"),
                border_width=0,
                key=f"-BREADCRUMB-{i}-",
                btn_size=(30, 30),
            ),
            sg.Text(_t(f"wizard_gui.step_{i}")),
        ]
    )



wizard_layout = [
    [
        sg.Image(OEM_LOGO),
        sg.Push(),
        sg.Image(source=THEME_CHOOSER_ICON, key="-THEME-", enable_events=True),
    ],
    [
        sg.Text(_t("wizard_gui.welcome"), font=("Helvetica", 16)),
    ],
    [
        sg.Text(_t("wizard_gui.welcome_description")),
    ],
    [
        sg.Column(wizard_breadcrumbs, element_justification="L", vertical_alignment="top"),
        sg.Column([wizard_tabs], expand_x=True, expand_y=True, vertical_alignment="top"),
    ],
    [
        sg.Column([[
            RoundedButton(_t("generic.cancel"), key="-PREVIOUS-", button_color=(TXT_COLOR_LDR, BG_COLOR_LDR), border_width=0),
            RoundedButton(_t("generic.start"), key="-NEXT-", button_color=(TXT_COLOR_LDR, BG_COLOR_LDR), border_width=0),
        ],], element_justification="C", expand_x=True, expand_y=False)
    ],
]


def start_wizard():
    CURRENT_THEME = SIMPLEGUI_THEME
    NUMBER_OF_TABS = len(wizard_tabs) + 1
    current_tab = 0
    wizard = sg.Window(
        "NPBackup Wizard",
        layout=wizard_layout,
        size=(900, 600),
        element_justification="L",
    )

    def _reskin_job():
        nonlocal CURRENT_THEME
        reskin(
            window=wizard,
            new_theme=CURRENT_THEME,
            theme_function=sg.theme,
            lf_table=LOOK_AND_FEEL_TABLE,
        )
        wizard.TKroot.after(60000, _reskin_job)

    def set_active_tab(active_number):
        for tab_index in range(1, NUMBER_OF_TABS):
            if tab_index != active_number:
                wizard[f"-TAB{tab_index}-"].Update(visible=False)
                wizard[f"-BREADCRUMB-{tab_index}-"].Update(
                    button_color=("#FAFAFA", None)
                )
        wizard[f"-TAB{active_number}-"].Update(visible=True)
        wizard[f"-BREADCRUMB-{active_number}-"].Update(
            button_color=("#3F2DCB", None)
        )

    wizard.finalize()
    set_active_tab(1)
    while True:
        event, values = wizard.read()
        if event == sg.WIN_CLOSED or event == _t("generic.cancel"):
            break
        if event == "-THEME-":
            if CURRENT_THEME != "DARK":
                CURRENT_THEME = "DARK"
            else:
                CURRENT_THEME = "CLEAR"
            _reskin_job()
            continue
        if event == "-NEXT-":
            if current_tab < NUMBER_OF_TABS:
                current_tab += 1
                wizard["-NEXT-"].update(
                    _t("generic.finish")
                    if current_tab == NUMBER_OF_TABS
                    else _t("generic.next")
                )
                wizard["-PREVIOUS-"].update(
                    _t("generic.cancel") if current_tab == 0 else _t("generic.previous")
                )
                set_active_tab(current_tab)
            elif current_tab == NUMBER_OF_TABS:
                sg.popup(_t("wizard_gui.thank_you"), keep_on_top=True)
                break
        if event == "-PREVIOUS-":
            if current_tab > 1:
                current_tab -= 1
                wizard["-NEXT-"].update(
                    _t("generic.finish")
                    if current_tab == NUMBER_OF_TABS
                    else _t("generic.next")
                )
                wizard["-PREVIOUS-"].update(
                    _t("generic.cancel") if current_tab == 0 else _t("generic.previous")
                )
                set_active_tab(current_tab)
            elif current_tab == 1:
                break
    wizard.close()


start_wizard()
