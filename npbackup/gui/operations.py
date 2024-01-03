#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.operations"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023121901"


from logging import getLogger
import PySimpleGUI as sg
import npbackup.configuration as configuration
from npbackup.core.i18n_helper import _t
from npbackup.gui.helpers import get_anon_repo_uri, gui_thread_runner
from npbackup.customization import (
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
    LICENSE_TEXT,
    LICENSE_FILE,
)


logger = getLogger(__intname__)


def gui_update_state(window, full_config: dict) -> list:
    repo_list = []
    try:
        for repo_name in full_config.g("repos"):
            repo_config, _ = configuration.get_repo_config(full_config, repo_name)
            if repo_config.g(f"repo_uri") and (
                repo_config.g(f"repo_opts.repo_password")
                or repo_config.g(f"repo_opts.repo_password_command")
            ):
                backend_type, repo_uri = get_anon_repo_uri(repo_config.g(f"repo_uri"))
                repo_list.append([repo_name, backend_type, repo_uri])
            else:
                logger.warning("Incomplete operations repo {}".format(repo_name))
    except KeyError:
        logger.info("No operations repos configured")
    window["repo-list"].update(repo_list)
    return repo_list


def operations_gui(full_config: dict) -> dict:
    """
    Operate on one or multiple repositories
    """

    # This is a stupid hack to make sure uri column is large enough
    headings = [
        "Name      ",
        "Backend",
        "URI                                                  ",
    ]

    layout = [
        [
            sg.Column(
                [
                    [
                        sg.Column(
                            [[sg.Image(data=OEM_LOGO)]],
                            vertical_alignment="top",
                        ),
                        sg.Column(
                            [
                                [sg.Text(OEM_STRING, font="Arial 14")],
                            ],
                            justification="C",
                            element_justification="C",
                            vertical_alignment="top",
                        ),
                    ],
                    [sg.Text(_t("operations_gui.configured_repositories"))],
                    [
                        sg.Table(
                            values=[[]],
                            headings=headings,
                            key="repo-list",
                            auto_size_columns=True,
                            justification="left",
                        )
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.quick_check"),
                            key="--QUICK-CHECK--",
                            size=(45, 1),
                        ),
                        sg.Button(
                            _t("operations_gui.full_check"),
                            key="--FULL-CHECK--",
                            size=(45, 1),
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.repair_index"),
                            key="--REPAIR-INDEX--",
                            size=(45, 1),
                        ),
                        sg.Button(
                            _t("operations_gui.repair_snapshots"),
                            key="--REPAIR-SNAPSHOTS--",
                            size=(45, 1),
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.unlock"), key="--UNLOCK--", size=(45, 1)
                        ),
                        sg.Button(
                            _t("operations_gui.forget_using_retention_policy"),
                            key="--FORGET--",
                            size=(45, 1),
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.standard_prune"),
                            key="--STANDARD-PRUNE--",
                            size=(45, 1),
                        ),
                        sg.Button(
                            _t("operations_gui.max_prune"),
                            key="--MAX-PRUNE--",
                            size=(45, 1),
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.stats"),
                            key="--STATS--",
                            size=(45, 1),
                        )
                    ],
                    [sg.Button(_t("generic.quit"), key="--EXIT--")],
                ],
                element_justification="C",
            )
        ]
    ]

    window = sg.Window(
        "Configuration",
        layout,
        # size=(600, 600),
        text_justification="C",
        auto_size_text=True,
        auto_size_buttons=True,
        no_titlebar=False,
        grab_anywhere=True,
        keep_on_top=False,
        alpha_channel=1.0,
        default_button_element_size=(20, 1),
        finalize=True,
    )

    complete_repo_list = gui_update_state(window, full_config)

    # Auto reisze table to window size
    window["repo-list"].expand(True, True)

    while True:
        event, values = window.read()

        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--EXIT--"):
            break
        if event in (
            "--QUICK-CHECK--",
            "--FULL-CHECK--",
            "--REPAIR-INDEX--",
            "--REPAIR-SNAPSHOTS--",
            "--UNLOCK--",
            "--FORGET--",
            "--STANDARD-PRUNE--",
            "--MAX-PRUNE--",
            "--STATS--"
        ):
            if not values["repo-list"]:
                result = sg.popup(
                    _t("operations_gui.apply_to_all"),
                    custom_text=(_t("generic.yes"), _t("generic.no")),
                )
                if not result == _t("generic.yes"):
                    continue
                repos = complete_repo_list
            else:
                repos = []
                for value in values["repo-list"]:
                    repos.append(complete_repo_list[value])

            repo_config_list = []
            for repo_name, backend_type, repo_uri in repos:
                repo_config, config_inheritance = configuration.get_repo_config(
                    full_config, repo_name
                )
                repo_config_list.append((repo_name, repo_config))
            if event == "--FORGET--":
                operation = "forget"
                op_args = {"use_policy": True}
                gui_msg = _t("operations_gui.forget_using_retention_policy")
            if event == "--QUICK-CHECK--":
                operation = "check"
                op_args = {"read_data": False}
                gui_msg = _t("operations_gui.quick_check")
            if event == "--FULL-CHECK--":
                operation = "check"
                op_args = {"read_data": True}
                gui_msg = _t("operations_gui.full_check")
            if event == "--UNLOCK--":
                operation = "unlock"
                op_args = {}
                gui_msg = _t("operations_gui.unlock")
            if event == "--REPAIR-INDEX--":
                operation = "repair"
                op_args = {"subject": "index"}
                gui_msg = _t("operations_gui.repair_index")
            if event == "--REPAIR-SNAPSHOTS--":
                operation = "repair"
                op_args = {"subject": "snapshots"}
                gui_msg = _t("operations_gui.repair_snapshots")
            if event == "--STANDARD-PRUNE--":
                operation = "prune"
                op_args = {}
                gui_msg = _t("operations_gui.standard_prune")
            if event == "--MAX-PRUNE--":
                operation = "prune"
                op_args = {"max": True}
                gui_msg = _t("operations_gui.max_prune")
            if event == "--STATS--":
                operation = "stats"
                op_args = {}
                gui_msg = _t("operations_gui.stats")
            result = gui_thread_runner(
                None,
                "group_runner",
                operation=operation,
                repo_config_list=repo_config_list,
                __autoclose=False,
                __compact=False,
                __gui_msg=gui_msg,
                **op_args,
            )

            event = "---STATE-UPDATE---"
        if event == "---STATE-UPDATE---":
            complete_repo_list = gui_update_state(window, full_config)
    window.close()

    return full_config
