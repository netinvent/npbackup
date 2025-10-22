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
    TREE_ICON,
)

from npbackup.gui.constants import combo_boxes, byte_units
from npbackup.core.i18n_helper import _t, _locale
from npbackup.gui.buttons import RoundedButton
import npbackup.configuration
import sv_ttk

CONFIG_FILE = "npbackup.conf"  # WIP override via --config-file
sg.LOOK_AND_FEEL_TABLE["CLEAR"] = LOOK_AND_FEEL_TABLE["CLEAR"]
sg.LOOK_AND_FEEL_TABLE["DARK"] = LOOK_AND_FEEL_TABLE["DARK"]
sg.theme(SIMPLEGUI_THEME)
logger = getLogger()

add_source_menu = [
    "-ADD-SOURCE-",
    [
        _t("generic.add_files"),
        _t("generic.add_folder"),
        _t("wizard_gui.add_system"),
        _t("wizard_gui.add_hyper_v"),
        _t("wizard_gui.add_kvm"),
    ],
]

date_options = {
    "format": "%Y-%m-%d",
    "default_date_m_d_y": (
        datetime.now().month,
        datetime.now().day,
        datetime.now().year,
    ),
    "close_when_date_chosen": True,
}

conf = npbackup.configuration.load_config(CONFIG_FILE)
if not conf:
    conf = npbackup.configuration.get_default_config()
try:
    retention_policies = list(conf.g("presets.retention_policies").keys())
except Exception:
    retention_policies = {}

backup_paths_tree = sg.TreeData()
# retention_policies = list(combo_boxes["retention_options"].values())

wizard_layouts = {
    "wizard_layout_1": [
        [
            sg.Text(
                textwrap.fill(f"{_t('wizard_gui.step_1')}"),
                size=(40, 1),
                expand_x=False,
                font=("Helvetica", 16),
            ),
            sg.Push(),
            sg.ButtonMenu(
                _t("generic.add"),
                menu_def=add_source_menu,
                key="-ADD-SOURCE-MENU-",
                button_color=(TXT_COLOR_LDR, BG_COLOR_LDR),
            ),
        ],
        [
            sg.Text(
                _t('wizard_gui.step_1_description'),
                size=(80, 1),
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
        [
            sg.Push(), RoundedButton(_t("generic.remove_selected"), key="-REMOVE-SOURCE-", button_color=(TXT_COLOR_LDR, BG_COLOR_LDR),
                border_width=0, btn_size=(150, 30))
        ]
    ],
    "wizard_layout_2": [
        [sg.Text(_t("wizard_gui.backup_location"), font=("Helvetica", 16))],
                [
            sg.Text(
                _t('wizard_gui.step_2_description'),
                size=(80, 1),
            ),
        ],
        [
            sg.Text(_t("wizard_gui.backend"), size=(20, 1)),
            sg.Combo(
                list(combo_boxes["backends"].values()),
                default_value=_t("wizard_gui.select_backend"),
                key="-BACKEND-TYPE-",
                enable_events=True,
                size=(40, 1),
            ),
        ],
        [
            sg.Text(_t("config_gui.backup_repo_uri"), size=(20, 1), key="-BACKEND-URI-LABEL-", visible=False),
            sg.Input(key="-BACKEND-URI-", size=(45, 1), visible=False, background_color=sg.theme_background_color()),
        ],
        [
            sg.Text(_t("config_gui.backup_repo_password"), size=(20, 1), key="-BACKEND-REPO-PASSWORD-LABEL-", visible=False),
            sg.Input(key="-BACKEND-REPO-PASSWORD-", size=(45, 1), visible=False, background_color=sg.theme_background_color(), password_char="*"),
        ]
    ],
    "wizard_layout_3": [
        [sg.Text(_t("wizard_gui.step_3"), font=("Helvetica", 16))],
        [
            sg.Text(
                _t('wizard_gui.step_3_description'),
                size=(80, 1),
            ),
        ],
        [
            sg.Input("YYYY/MM/DD", key="-FIRST-BACKUP-DATE-", size=(12, 1), background_color=sg.theme_background_color()),
            sg.Combo(
                values=[h for h in range(0, 24)],
                default_value=0,
                key="-FIRST-BACKUP-HOUR-",
                size=(3, 1),
            ),
            sg.Text(" : "),
            sg.Combo(
                values=[m for m in range(0, 60)],
                default_value=0,
                key="-FIRST-BACKUP-MINUTE-",
                size=(3, 1),
            ),
        ],
        [
            sg.CalendarButton(
                "Calendar", target="-FIRST-BACKUP-DATE-", key="CALENDAR", **date_options
            ),
        ],
    ],
    "wizard_layout_4": [
        [sg.Text(_t("wizard_gui.step_4"), font=("Helvetica", 16))],
        [
            sg.Text(
                _t('wizard_gui.step_4_description'),
                size=(80, 1),
            ),
        ],
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
    "wizard_layout_5": [
        [sg.Text(_t("wizard_gui.step_5"), font=("Helvetica", 16))],
        [
            sg.Text(
                _t('wizard_gui.step_5_description'),
                size=(80, 1),
            ),
        ],
        [
            sg.Combo(
                values=retention_policies,
                default_value=retention_policies[0],
                key="-RETENTION-TYPE-",
                enable_events=True,
            )
        ],
    ],
    "wizard_layout_6": [
        [sg.Text(_t("wizard_gui.step_6"), font=("Helvetica", 16))],
        [
            sg.Text(
                _t('wizard_gui.step_6_description'),
                size=(80, 1),
            ),
        ],
        [
            sg.Checkbox(
                _t("wizard_gui.disable_config_button"),
                key="-DISABLE-CONFIG-BUTTON-",
                default=True,
            )
        ],
    ],
    "wizard_layout_7": [
        [sg.Text(_t("wizard_gui.step_7"), font=("Helvetica", 16))],
        [
            sg.Text(
                _t('wizard_gui.step_7_description'),
                size=(80, 1),
            ),
        ],
    ],
}

wizard_tabs = []
wizard_breadcrumbs = []
for i in range(1, len(wizard_layouts) + 1):
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
                button_color=(TXT_COLOR_LDR, BG_COLOR_LDR),
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
        sg.Column(
            [

            [
                sg.Text(_t("wizard_gui.welcome"), font=("Helvetica", 16)),
            ],
            [
                sg.Text(_t("wizard_gui.welcome_description")),
            ],
            ]
        )
        # Don't allow skins on rounded buttons that messes up the corners
        # sg.Image(source=THEME_CHOOSER_ICON, key="-THEME-", enable_events=True),
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
                        _t("generic.cancel"),
                        key="-PREVIOUS-",
                        button_color=(TXT_COLOR_LDR, BG_COLOR_LDR),
                        border_width=0,
                    ),
                    RoundedButton(
                        _t("generic.next"),
                        key="-NEXT-",
                        button_color=(TXT_COLOR_LDR, BG_COLOR_LDR),
                        border_width=0,
                    ),
                ],
            ],
            element_justification="C",
            expand_x=True,
            expand_y=False,
        )
    ],
]


def start_wizard():
    CURRENT_THEME = SIMPLEGUI_THEME
    NUMBER_OF_TABS = len(wizard_tabs)
    current_tab = 1
    wizard = sg.Window(
        "NPBackup Wizard",
        layout=wizard_layout,
        size=(900, 600),
        element_justification="L",
        #ttk_theme="xpnative"
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
        for tab_index in range(1, NUMBER_OF_TABS + 1):
            if tab_index != active_number:
                wizard[f"-TAB{tab_index}-"].Update(visible=False)
                wizard[f"-BREADCRUMB-{tab_index}-"].Update(
                    button_color=("#FAFAFA", None)
                )
        wizard[f"-TAB{active_number}-"].Update(visible=True)
        wizard[f"-BREADCRUMB-{active_number}-"].Update(button_color=("#3F2DCB", None))

    wizard.finalize()
    # Widget theming from https://github.com/rdbende/Sun-Valley-ttk-theme?tab=readme-ov-file
    sv_ttk.set_theme("light")

    set_active_tab(1)

    while True:
        event, values = wizard.read()
        if event == sg.WIN_CLOSED or event == _t("generic.cancel"):
            break
        """
        # Don't allow skins on rounded buttons that messes up the corners
        if event == "-THEME-":
            if CURRENT_THEME != "DARK":
                CURRENT_THEME = "DARK"
            else:
                CURRENT_THEME = "CLEAR"
            _reskin_job()
            continue
        """
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
        if event == "-ADD-SOURCE-MENU-":
            node = None
            if values["-ADD-SOURCE-MENU-"] == _t("generic.add_files"):
                sg.FileBrowse(_t("generic.add_files"), target="backup_opts.paths")
                node = sg.popup_get_file("Add files clicked", no_window=True)
            elif values["-ADD-SOURCE-MENU-"] == _t("generic.add_folder"):
                node = sg.popup_get_folder("Add folder clicked", no_window=True)
            elif values["-ADD-SOURCE-MENU-"] == _t("wizard_gui.add_system"):
                sg.popup("Add Windows system clicked", keep_on_top=True)
            elif values["-ADD-SOURCE-MENU-"] == _t("wizard_gui.add_hyper_v"):
                sg.popup("Add Hyper-V virtual machines clicked", keep_on_top=True)
            elif values["-ADD-SOURCE-MENU-"] == _t("wizard_gui.add_kvm"):
                sg.popup("Add KVM virtual machines clicked", keep_on_top=True)
            if node:
                icon = TREE_ICON
                tree = backup_paths_tree
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
                wizard["backup_opts.paths"].update(values=tree)
        if event == "-REMOVE-SOURCE-":
            selected_items = values["backup_opts.paths"]
            tree = backup_paths_tree
            for item in selected_items:
                tree.delete(item)
            wizard["backup_opts.paths"].update(values=tree)
        if event == "-BACKEND-TYPE-":
            wizard["-BACKEND-URI-LABEL-"].update(visible=True)
            wizard["-BACKEND-URI-"].update(visible=True)
            wizard["-BACKEND-REPO-PASSWORD-LABEL-"].update(visible=True)
            wizard["-BACKEND-REPO-PASSWORD-"].update(visible=True)
            wizard["-BACKEND-URI-"].Update("")
    wizard.close()


start_wizard()
