#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.operations"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024093001"


import os
from typing import List
from logging import getLogger
from collections import namedtuple
import json
import FreeSimpleGUI as sg
from npbackup.configuration import (
    get_repo_config,
    get_repo_list,
    get_group_list,
    get_repos_by_group,
    get_manager_password,
)
from npbackup.core.i18n_helper import _t
from npbackup.gui.helpers import get_anon_repo_uri, gui_thread_runner
from resources.customization import (
    OEM_STRING,
    OEM_LOGO,
)
from npbackup.gui.config import ENCRYPTED_DATA_PLACEHOLDER, ask_manager_password


logger = getLogger(__intname__)


gui_object = namedtuple("GuiOjbect", ["type", "name", "group", "backend", "uri"])


def gui_update_state(window, full_config: dict, unencrypted: str = None) -> list:
    repo_and_group_list = []
    try:
        for repo_name in full_config.g("repos"):
            repo_config, _ = get_repo_config(full_config, repo_name)
            if repo_config.g(f"repo_uri") and (
                repo_config.g(f"repo_opts.repo_password")
                or repo_config.g(f"repo_opts.repo_password_command")
            ):
                backend_type, repo_uri = get_anon_repo_uri(repo_config.g(f"repo_uri"))
                repo_group = repo_config.g("repo_group")
                if not unencrypted and unencrypted != repo_name:
                    repo_uri = ENCRYPTED_DATA_PLACEHOLDER
                repo_and_group_list.append(
                    gui_object("repo", repo_name, repo_group, backend_type, repo_uri)
                )
            else:
                logger.warning("Incomplete URI/password for repo {}".format(repo_name))
        for group_name in get_group_list(full_config):
            repo_and_group_list.append(gui_object("group", group_name, "", "", ""))
    except KeyError:
        logger.info("No operations repos configured")
    window["repo-and-group-list"].update(repo_and_group_list)
    return repo_and_group_list


'''
def task_scheduler(repos: list):
    """
    Create tasks for given repo list

    WIP: This is a mock GUI, nothing works yet

    """
    task = namedtuple("Tasks", ["task", "hour", "minute", "day", "month", "weekday"])

    def _get_current_tasks():
        """
        mock tasks
        """
        return [
            task("housekeeping", 0, 0, "*", "*", "*"),
            task("check", 0, 0, "*", "*", "*"),
        ]

    def _update_task_list(window):
        tasks = _get_current_tasks()
        task_list = []
        for task in tasks:
            task_list.append(task)
        window["-TASKS-"].update(values=task_list)

    actions = [
        "backup",
        "housekeeping",
        "quick_check",
        "full_check" "unlock",
        "forget",
        "prune",
        "prune_max",
    ]

    layout = [
        [
            sg.Text(_t("operations_gui.currently_configured_tasks")),
        ],
        [
            sg.Table(
                values=[[]],
                headings=["Task type", "Minute", "Hour", "Day", "Month", "Weekday"],
                key="-TASKS-",
                auto_size_columns=True,
                justification="left",
            ),
        ],
        [
            sg.Button("Add", key="--ADD-TASK--", size=(10, 1)),
            sg.Button("Remove", key="--REMOVE-TASK--", size=(10, 1)),
        ],
        [
            sg.Text(_t("operations_gui.select_task_type")),
        ],
        [
            sg.Combo(
                values=actions,
                default_value="housekeeping",
                key="-ACTION-",
                size=(20, 1),
            ),
            sg.Button(_t("operations_gui.add_task"), key="-ADD-TASK-", size=(20, 1)),
        ],
    ]

    window = sg.Window(
        layout=layout, title=_t("operations_gui.task_scheduler"), finalize=True
    )
    _update_task_list(window)
    while True:
        event, values = window.read()

        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--EXIT--"):
            break
'''

def show_stats(statistics: List[dict]) -> None:
    """
    Shows a "nice" representation of repo statistics
    """

    data = []
    for entry in statistics:
        repo_name = list(entry.keys())[0]
        state = "Success" if entry[repo_name]["result"] else "Failure"
        try:
            total_size = entry[repo_name]["output"]["total_size"]
            total_file_count= entry[repo_name]["output"]["total_file_count"]
            snapshots_count = entry[repo_name]["output"]["snapshots_count"]
            data.append([repo_name, state, total_size, total_file_count, snapshots_count])
        except:
            data.append([repo_name, state])

    headings = ["Repo", "Stat state", "Total size", "Total File Count", "Snapshot Count"]
    layout = [
        [
            sg.Table(values=data, headings=headings, justification="right")
        ],
        [
            sg.Button(_t("generic.close"), key="--EXIT--")
        ]
    ]

    window = sg.Window("Statistics", layout, keep_on_top=True, element_justification="R")
    while True:
        event, _ = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--EXIT--"):
            break
    window.close()


def operations_gui(full_config: dict) -> dict:
    """
    Operate on one or multiple repositories, or groups
    """

    def _get_repo_list(selected_rows): # WIP remove dependency
        if not values["repo-and-group-list"]:
            if (
                sg.popup_yes_no(_t("operations_gui.no_repo_selected"), keep_on_top=True)
                == "No"
            ):
                return False
            repos = get_repo_list(full_config)
        else:
            repos = []
            for index in values["repo-and-group-list"]:
                gui_object = complete_repo_list[index]
                if gui_object.type == "group":
                    repos += get_repos_by_group(full_config, gui_object.name)
                else:
                    repos.append(gui_object.name)
        # Cheap duplicate filter
        repos = list(set(repos))
        return repos

    # This is a stupid hack to make sure uri column is large enough
    headings = [
        "Type      ",
        "Name      ",
        "Group      ",
        "Backend",
        "URI                                 ",
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
                            key="repo-and-group-list",
                            auto_size_columns=True,
                            justification="left",
                        ),
                    ],
                    [
                        sg.Text(_t("operations_gui.select_repositories")),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.housekeeping"),
                            key="--HOUSEKEEPING--",
                            size=(45, 1),
                        ),
                        sg.Button(
                            _t("operations_gui.task_scheduler"),
                            key="--TASK-SCHEDULER--",
                            size=(45, 1),
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.quick_check"),
                            key="--QUICK-CHECK--",
                            size=(45, 1),
                            visible=False,
                        ),
                        sg.Button(
                            _t("operations_gui.full_check"),
                            key="--FULL-CHECK--",
                            size=(45, 1),
                            visible=False,
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.repair_index"),
                            key="--REPAIR-INDEX--",
                            size=(45, 1),
                            visible=False,
                        ),
                        sg.Button(
                            _t("operations_gui.repair_snapshots"),
                            key="--REPAIR-SNAPSHOTS--",
                            size=(45, 1),
                            visible=False,
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.repair_packs"),
                            key="--REPAIR-PACKS--",
                            size=(45, 1),
                            visible=False,
                        ),
                        sg.Button(
                            _t("operations_gui.forget_using_retention_policy"),
                            key="--FORGET--",
                            size=(45, 1),
                            visible=False,
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.standard_prune"),
                            key="--STANDARD-PRUNE--",
                            size=(45, 1),
                            visible=False,
                        ),
                        sg.Button(
                            _t("operations_gui.max_prune"),
                            key="--MAX-PRUNE--",
                            size=(45, 1),
                            visible=False,
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.unlock"),
                            key="--UNLOCK--",
                            size=(45, 1),
                            visible=False,
                        ),
                        sg.Button(
                            _t("operations_gui.recover"),
                            key="--RECOVER--",
                            size=(45, 1),
                            visible=False,
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.stats"),
                            key="--STATS--",
                            size=(45, 1),
                        ),
                        sg.Button(
                            _t("operations_gui.show_advanced"),
                            key="--ADVANCED--",
                            size=(45, 1),
                        ),
                    ],
                    [sg.Button(_t("generic.quit"), key="--EXIT--")],
                ],
                element_justification="C",
            )
        ]
    ]

    right_click_menu = ["", [_t("config_gui.show_decrypted")]]

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
        right_click_menu=right_click_menu,
        finalize=True,
    )

    complete_repo_list = gui_update_state(window, full_config)

    # Auto reisze table to window size
    window["repo-and-group-list"].expand(True, True)

    while True:
        event, values = window.read()

        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--EXIT--"):
            break
        if event == _t("config_gui.show_decrypted"):
            try:
                object_name = complete_repo_list[values["repo--group-list"][0]][0]
            except Exception as exc:
                logger.debug("Trace:", exc_info=True)
                object_name = None
            if not object_name:
                sg.PopupError(_t("operations_gui.no_repo_selected"), keep_on_top=True)
                continue
            manager_password = get_manager_password(full_config, object_name)
            # NPF-SEC-00009
            env_manager_password = os.environ.get("NPBACKUP_MANAGER_PASSWORD", None)
            if not manager_password:
                sg.PopupError(
                    _t("config_gui.no_manager_password_defined"), keep_on_top=True
                )
                continue
            if (
                env_manager_password and env_manager_password == manager_password
            ) or ask_manager_password(manager_password):
                complete_repo_list = gui_update_state(
                    window, full_config, unencrypted=object_name
                )
            continue
        if event == "--ADVANCED--":
            for button in (
                "--QUICK-CHECK--",
                "--FULL-CHECK--",
                "--REPAIR-INDEX--",
                "--REPAIR-PACKS--",
                "--REPAIR-SNAPSHOTS--",
                "--RECOVER--",
                "--UNLOCK--",
                "--FORGET--",
                "--STANDARD-PRUNE--",
                "--MAX-PRUNE--",
            ):
                window[button].update(visible=True)
                window["--ADVANCED--"].update(disabled=True)
            continue
        if event in (
            "--HOUSEKEEPING--",
            "--QUICK-CHECK--",
            "--FULL-CHECK--",
            "--REPAIR-INDEX--",
            "--REPAIR-PACKS--",
            "--REPAIR-SNAPSHOTS--",
            "--RECOVER--",
            "--UNLOCK--",
            "--FORGET--",
            "--STANDARD-PRUNE--",
            "--MAX-PRUNE--",
            "--STATS--",
        ):
            repos = _get_repo_list(values["repo-and-group-list"])

            repo_config_list = []
            if not repos:
                continue
            for repo_name in repos:
                repo_config, _ = get_repo_config(full_config, repo_name)
                repo_config_list.append(repo_config)
            operation = None
            op_args = None
            gui_msg = None
            if event == "--HOUSEKEEPING--":
                operation = "housekeeping"
                op_args = {}
                gui_msg = _t("operations_gui.housekeeping")
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
            if event == "--REPAIR-PACKS--":
                operation = "repair"
                pack_ids = sg.popup_get_text(
                    _t("operations_gui.repair_packs"), keep_on_top=True
                )
                op_args = {
                    "subject": "packs",
                    "pack_ids": pack_ids,
                }
                gui_msg = _t("operations_gui.repair_packs")
            if event == "--REPAIR-SNAPSHOTS--":
                operation = "repair"
                op_args = {"subject": "snapshots"}
                gui_msg = _t("operations_gui.repair_snapshots")
            if event == "--RECOVER--":
                operation = "recover"
                op_args = {}
                gui_msg = _t("operations_gui.recover")
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
            if operation:
                data = gui_thread_runner(
                    None,
                    "group_runner",
                    operation=operation,
                    repo_config_list=repo_config_list,
                    __autoclose=False if operation != "stats" else True,
                    __compact=False,
                    __gui_msg=gui_msg,
                    **op_args,
                )
                if operation == "stats":
                    try:
                        if data["result"]:
                            show_stats(data["output"])
                        else:
                            try:
                                error = data["reason"]
                            except KeyError:
                                error = ""
                            error += f"\n{data['additional_error_info']}\n{data['additional_warning_info']}"
                            sg.PopupError(data["reason"])
                    except Exception as exc:
                        sg.PopupError(_t("generic.failure") + f": {exc}")
            else:
                logger.error(f"Bogus operation: {operation}")
                sg.popup_error(f"Bogus operation: {operation}", keep_on_top=True)

            event = "---STATE-UPDATE---"
        if event == "--TASK-SCHEDULER--":
            repos = _get_repo_list(values["repo-and-group-list"])
            if not repos:
                continue
            sg.Popup(
                "Currently not implemented. Please use the task creation GUI in config section, or use cron / windows task scheduler"
            )
            # task_scheduler(repos)
            continue
        if event == "---STATE-UPDATE---":
            complete_repo_list = gui_update_state(window, full_config)
    window.close()

    return full_config
