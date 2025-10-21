#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.wizard"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"


from typing import List, Optional, Tuple
import sys
import os
import re
import gc
import textwrap
from argparse import ArgumentParser
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
from psg_reskinner import animated_reskin, reskin
import _tkinter
import npbackup.configuration
import npbackup.common
from resources.customization import (
    LOOK_AND_FEEL_TABLE,
    OEM_STRING,
    OEM_LOGO,
    BG_COLOR_LDR,
    TXT_COLOR_LDR,
    GUI_STATE_OK_BUTTON,
    GUI_STATE_OLD_BUTTON,
    GUI_STATE_UNKNOWN_BUTTON,
    LOADER_ANIMATION,
    FOLDER_ICON,
    FILE_ICON,
    SYMLINK_ICON,
    IRREGULAR_FILE_ICON,
    LICENSE_TEXT,
    SIMPLEGUI_THEME,
    SIMPLEGUI_DARK_THEME,
    OEM_ICON,
    SHORT_PRODUCT_NAME,
    THEME_CHOOSER_ICON,
    # WIZARD
    ADD_FOLDER,
    ADD_FILE,
    ADD_PROPERTY,
    REMOVE_PROPERTY,
    HYPERV,
    KVM,
    WINDOWS_SYSTEM,
    BACKEND_LOCAL,
    BACKEND_SFTP,
    BACKEND_B2,
    BACKEND_S3,
    BACKEND_REST,
    BACKEND_WASABI,
    BACKEND_GOOGLE,
    BACKEND_AZURE
)
from npbackup.gui.config import config_gui, ask_manager_password
from npbackup.gui.operations import operations_gui
from npbackup.gui.helpers import get_anon_repo_uri, gui_thread_runner, HideWindow
from npbackup.gui.handle_window import handle_current_window
from npbackup.gui.constants import combo_boxes, byte_units
from npbackup.core.i18n_helper import _t
from npbackup.core import upgrade_runner
from npbackup.path_helper import CURRENT_DIR
from npbackup.__version__ import version_dict, version_string
from npbackup.__debug__ import _DEBUG, _NPBACKUP_ALLOW_AUTOUPGRADE_DEBUG
from npbackup.restic_wrapper import ResticRunner
from npbackup.restic_wrapper import schema
from npbackup.gui.buttons import RoundedButton

sg.LOOK_AND_FEEL_TABLE["CLEAR"] = LOOK_AND_FEEL_TABLE["CLEAR"]
sg.LOOK_AND_FEEL_TABLE["DARK"] = LOOK_AND_FEEL_TABLE["DARK"]
sg.theme(SIMPLEGUI_THEME)
logger = getLogger()


wizard_layout_1 =  [
        [sg.Text(_t("wizard_gui.welcome", font=("Helvetica", 16)))],
        [sg.Push()],
        [sg.Text(_t("wizard_gui.welcome_description"))],
    ]    

wizard_layout_2 = [
            [
                sg.Text(
                    textwrap.fill(f"{_t('wizard_gui.select_backup_sources')}", 70),
                    size=(None, None),
                    expand_x=True,
                    justification='c',
                ),
            ],
            [
                sg.Input(visible=False, key="--ADD-PATHS-FILE--", enable_events=True),
                sg.FilesBrowse(
                    "", # _t("generic.add_files"
                    target="--ADD-PATHS-FILE--",
                    key="--ADD-PATHS-FILE-BUTTON--",
                    image_data=ADD_FILE,
                    border_width=0,
                    #button_color=(None, sg.LOOK_AND_FEEL_TABLE[SIMPLEGUI_THEME]["BACKGROUND"])
                ),
                sg.Input(visible=False, key="--ADD-PATHS-FOLDER--", enable_events=True),
                sg.FolderBrowse(
                    "", # _t("generic.add_folder"),
                    target="--ADD-PATHS-FOLDER--",
                    key="--ADD-PATHS-FOLDER-BUTTON--",
                    image_data=ADD_FOLDER,
                    border_width=0,
                    #button_color=(None, sg.LOOK_AND_FEEL_TABLE[SIMPLEGUI_THEME]["BACKGROUND"])
                ),
                sg.Button(
                    "",  # _t("generic.add_manually"),
                    key="--ADD-PATHS-MANUALLY--",
                    image_source=ADD_PROPERTY,
                    border_width=0,
                    #button_color=(None, sg.LOOK_AND_FEEL_TABLE[SIMPLEGUI_THEME]["BACKGROUND"])
                ),
                sg.Button(
                    "", # _t("generic.remove_selected"),
                    key="--REMOVE-PATHS--",
                    image_data=REMOVE_PROPERTY,
                    border_width=0,
                    #button_color=(None, sg.LOOK_AND_FEEL_TABLE[SIMPLEGUI_THEME]["BACKGROUND"])
                ),
                sg.Button(
                    "",
                    image_data=WINDOWS_SYSTEM,
                    key="-ADD-WINDOWS-SYSTEM-",
                    border_width=0,
                ),
                sg.Button(
                    "",
                    image_data=HYPERV,
                    key="-ADD-HYPERV-",
                    border_width=0,
                ),
                sg.Button(
                    "",
                    image_data=KVM,
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
        ]  

wizard_layout_3 = [
    [
        sg.Text(_t("wizard_gui.backup_location", font=("Helvetica", 16)))
    ],
    [
        sg.Input(visible=False, key="--ADD-DESTINATION-FOLDER--", enable_events=True),
        sg.FolderBrowse("", image_data=BACKEND_LOCAL, key="-BACKEND-LOCAL", border_width=0, target="--ADD-DESTINATION-FOLDER--"),
        sg.Button(image_data=BACKEND_SFTP, key="-BACKEND-SFTP", border_width=0),
        sg.Button(image_data=BACKEND_B2, key="-BACKEND-B2", border_width=0),
        sg.Button(image_data=BACKEND_S3, key="-BACKEND-S3", border_width=0),
    ],
    [
        sg.Text("      HDD        "),
        sg.Text("        SFTP        "),
        sg.Text("        B2        "),
        sg.Text("        S3        "),
    ],
    [
        sg.Button(image_data=BACKEND_REST, key="-BACKEND-REST", border_width=0),
        sg.Button(image_data=BACKEND_GOOGLE, key="-BACKEND-GOOGLE", border_width=0),
        sg.Button(image_data=BACKEND_AZURE, key="-BACKEND-AZURE", border_width=0),
        sg.Button(image_data=BACKEND_WASABI, key="-BACKEND-WASABI", border_width=0),
    ],
    [
        sg.Text("       REST       "),
        sg.Text("       Google       "),
        sg.Text("       Azure       "),
        sg.Text("       Wasabi       ")
    ]
]
wizard_layout_4 = [
            [
                sg.Column(
                    [
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
            ],

]
wizard_layout_5 = [
    [
        sg.T(_t("wizard_gui.retention_settings"), font=("Helvetica", 16))
    ],
    [sg.Combo(values=list(combo_boxes["retention_options"].values()), default_value=next(iter(combo_boxes["retention_options"])), key="-RETENTION-TYPE-", enable_events=True)],
]

wizard_layout_6 = [
    [
        sg.Text(_t("wizard_gui.end_user_experience", font=("Helvetica", 16)))
    ],
    [
        sg.Checkbox(_t("wizard_gui.disable_config_button"), key="-DISABLE-CONFIG-BUTTON-", default=True)
    ]
]

wizard_layout_7 = [
    [sg.Text(_t("wizard_gui.end_user_experience", font=("Helvetica", 16)))],
]


wizard_breadcrumbs = [
    [RoundedButton('1', button_color=("#FAFAFA", "#ADADAD"), border_width=0, key='-BREADCRUMB-1-')],
    [RoundedButton('2', button_color=("#FAFAFA", "#ADADAD"), border_width=0, key='-BREADCRUMB-2-')],
    [RoundedButton('3', button_color=("#FAFAFA", "#ADADAD"), border_width=0, key='-BREADCRUMB-3-')],
    [RoundedButton('4', button_color=("#FAFAFA", "#ADADAD"), border_width=0, key='-BREADCRUMB-4-')],
    [RoundedButton('5', button_color=("#FAFAFA", "#ADADAD"), border_width=0, key='-BREADCRUMB-5-')],
    [RoundedButton('6', button_color=("#FAFAFA", "#ADADAD"), border_width=0, key='-BREADCRUMB-6-')],
    [RoundedButton('7', button_color=("#FAFAFA", "#ADADAD"), border_width=0, key='-BREADCRUMB-7-')],

]

wizard_tabs = [
    sg.Column(wizard_layout_1, element_justification='c', key='-TAB1-'),
    sg.Column(wizard_layout_2, element_justification='c', key='-TAB2-'),
    sg.Column(wizard_layout_3, element_justification='c', key='-TAB3-'),
    sg.Column(wizard_layout_4, element_justification='c', key='-TAB4-'),
    sg.Column(wizard_layout_5, element_justification='c', key='-TAB5-'),
    sg.Column(wizard_layout_6, element_justification='c', key='-TAB6-'),
    sg.Column(wizard_layout_7, element_justification='c', key='-TAB7-'),
]

wizard_layout = [
    [sg.Push(), sg.Image(source=THEME_CHOOSER_ICON, key="-THEME-",enable_events=True)],
    [sg.Column(wizard_breadcrumbs, element_justification="L"), sg.Column([wizard_tabs], expand_x=True, expand_y=True)],
    [sg.Button(_t("generic.cancel"), key="-PREVIOUS-"), sg.Button(_t("generic.start"), key="-NEXT-")]
]

def start_wizard():
    CURRENT_THEME = SIMPLEGUI_THEME
    NUMBER_OF_TABS = len(wizard_tabs)
    current_tab = 1
    wizard = sg.Window("NPBackup Wizard",
                       layout=wizard_layout,
                       size=(800, 500),
                       element_justification='c',)

    def _reskin_job():
        nonlocal CURRENT_THEME
        animated_reskin(
            window=wizard,
            new_theme=CURRENT_THEME,
            theme_function=sg.theme,
            lf_table=LOOK_AND_FEEL_TABLE,
        )
        wizard.TKroot.after(60000, _reskin_job)
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
                wizard["-NEXT-"].update(_t("generic.finish") if current_tab == NUMBER_OF_TABS else _t("generic.next"))
                wizard["-PREVIOUS-"].update(_t("generic.cancel") if current_tab == 1 else _t("generic.previous"))
                for tab_index in range(1, NUMBER_OF_TABS + 1):
                    if tab_index != current_tab:
                        wizard[f"-TAB{tab_index}-"].Update(visible=False)
                        wizard[f"-BREADCRUMB-{tab_index}-"].Update(button_color=("#FAFAFA", None))
                wizard[f"-TAB{current_tab}-"].Update(visible=True)
                wizard[f"-BREADCRUMB-{current_tab}-"].Update(button_color=("#3F2DCB", None))
            elif current_tab == NUMBER_OF_TABS:
                sg.popup(_t("wizard_gui.thank_you"), keep_on_top=True)
                break
        if event == "-PREVIOUS-":
            if current_tab > 1:
                current_tab -= 1
                wizard["-NEXT-"].update(_t("generic.finish") if current_tab == NUMBER_OF_TABS else _t("generic.next"))
                wizard["-PREVIOUS-"].update(_t("generic.cancel") if current_tab == 1 else _t("generic.previous"))
                for tab_index in range(1, NUMBER_OF_TABS + 1):
                    if tab_index != current_tab:
                        wizard[f"-TAB{tab_index}-"].Update(visible=False)
                        wizard[f"-BREADCRUMB-{tab_index}-"].Update(button_color=("#FAFAFA", None))
                wizard[f"-TAB{current_tab}-"].Update(visible=True)
                wizard[f"-BREADCRUMB-{current_tab}-"].Update(button_color=("#3F2DCB", None))
            elif current_tab == 1:
                break
    wizard.close()



start_wizard()