#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.operations"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023121901"


from typing import Tuple
from logging import getLogger
import queue
import PySimpleGUI as sg
import npbackup.configuration as configuration
from ofunctions.threading import threaded, Future
from npbackup.core.runner import NPBackupRunner
from npbackup.core.i18n_helper import _t
from npbackup.gui.helpers import get_anon_repo_uri
from npbackup.customization import (
    OEM_STRING,
    OEM_LOGO,
    GUI_LOADER_COLOR,
    GUI_LOADER_TEXT_COLOR,
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
                backend_type, repo_uri = get_anon_repo_uri(
                    repo_config.g(f"repo_uri")
                )
                repo_list.append([backend_type, repo_uri])
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
    headings = ["Backend", "URI                                                  "]

    layout = [
        [
            sg.Column(
                [
                    [
                        sg.Column(
                            [[sg.Image(data=OEM_LOGO, size=(64, 64))]],
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
                        sg.Button(_t("operations_gui.quick_check"), key="--QUICK-CHECK--"),
                        sg.Button(_t("operations_gui.full_check"), key="--FULL-CHECK--"),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.forget_using_retention_policy"),
                            key="forget",
                        )
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.standard_prune"), key="--STANDARD-PRUNE--"
                        ),
                        sg.Button(_t("operations_gui.max_prune"), key="--MAX-PRUNE--"),
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
        size=(600, 600),
        text_justification="C",
        auto_size_text=True,
        auto_size_buttons=True,
        no_titlebar=False,
        grab_anywhere=True,
        keep_on_top=False,
        alpha_channel=1.0,
        default_button_element_size=(12, 1),
        finalize=True,
    )

    complete_repo_list = gui_update_state(window, full_config)

    # Auto reisze table to window size
    window["repo-list"].expand(True, True)

    # Create queues for getting runner data
    stdout_queue = queue.Queue()
    stderr_queue = queue.Queue()

    while True:
        event, values = window.read(timeout=60000)

        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, '--EXIT--'):
            break
        if event in [
            "--FORGET--",
            "--QUICK-CHECK--",
            "--FULL-CHECK--",
            "--STANDARD-PRUNE--",
            "--MAX-PRUNE--",
        ]:
            if not values["repo-list"]:
                result = sg.popup(
                    _t("operations_gui.apply_to_all"),
                    custom_text=(_t("generic.yes"), _t("generic.no")),
                )
                if not result == _t("generic.yes"):
                    continue
                repos = complete_repo_list
            else:
                repos = values["repo-list"]
        
            runner = NPBackupRunner()
            runner.stdout = stdout_queue
            runner.stderr = stderr_queue
            group_runner_repo_list = [repo_name for backend_type, repo_name in repos]

            if event == '--FORGET--':
                operation = 'forget'
                op_args = {}
            if event == '--QUICK-CHECK--':
                operation = 'check'
                op_args = {'read_data': False}
            if event == '--FULL-CHECK--':
                operation = 'check'
                op_args = {'read_data': True}
            if event == '--STANDARD-PRUNE--':
                operation = 'prune'
                op_args = {}
            if event == '--MAX-PRUNE--':
                operation = 'prune'
                op_args = {}
            @threaded
            def _group_runner(group_runner_repo_list, operation, **op_args) -> Future:
                return runner.group_runner(group_runner_repo_list, operation, **op_args)
            thread = _group_runner(group_runner_repo_list, operation, **op_args)

            read_stdout_queue = True
            read_sterr_queue = True

            progress_layout = [
                [sg.Text(_t("operations_gui.last_message"))],
                [sg.Multiline(key='-OPERATIONS-PROGRESS-STDOUT-', size=(40, 10))],
                [sg.Text(_t("operations_gui.error_messages"))],
                [sg.Multiline(key='-OPERATIONS-PROGRESS-STDERR-', size=(40, 10))],
                [sg.Button(_t("generic.close"), key="--EXIT--")]
            ]
            progress_window = sg.Window("Operation status", progress_layout)
            event, values = progress_window.read(timeout=0.01)

            #while read_stdout_queue or read_sterr_queue:
            while not thread.done() and not thread.cancelled():
                # Read stdout queue
                try:
                    stdout_data = stdout_queue.get(timeout=0.01)
                except queue.Empty:
                    pass
                else:
                    if stdout_data is None:
                        read_stdout_queue = False
                    else:
                        progress_window['-OPERATIONS-PROGRESS-STDOUT-'].Update(stdout_data)
                
                # Read stderr queue
                try:
                    stderr_data = stderr_queue.get(timeout=0.01)
                except queue.Empty:
                    pass
                else:
                    if stderr_data is None:
                        read_sterr_queue = False
                    else:
                        progress_window['-OPERATIONS-PROGRESS-STDERR-'].Update(f"{progress_window['-OPERATIONS-PROGRESS-STDERR-'].get()}\n{stderr_data}")

                # So we actually need to read the progress window for it to refresh...
                _, _ = progress_window.read(.01)
            
            # Keep the window open until user has done something
            while True:
                event, _ = progress_window.read()
                if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, '--EXIT--'):
                    break
            progress_window.close()

            event = '---STATE-UPDATE---'
        if event == "---STATE-UPDATE---":
            complete_repo_list = gui_update_state(window, full_config)
    window.close()

    return full_config
