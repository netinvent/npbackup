#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.operations"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026030101"


import os
from typing import List
import logging
from collections import namedtuple
from ofunctions.misc import BytesConverter
import FreeSimpleGUI as sg
from npbackup.configuration import (
    get_repo_config,
    get_repo_list,
    get_group_list,
    get_repos_by_group,
    get_manager_password,
    save_config,
    get_monitoring_config,
)
from npbackup.core.i18n_helper import _t
from npbackup.gui.helpers import (
    get_anon_repo_uri,
    gui_thread_runner,
    popup_error,
    HideWindow,
)
from resources.customization import (
    OEM_STRING,
    OEM_LOGO,
)
import npbackup.gui.common_gui_logic
import npbackup.gui.common_gui
import npbackup.task

logger = logging.getLogger(__intname__)


gui_object = namedtuple("GuiObject", ["type", "name", "group", "backend", "uri"])


def gui_update_state(window, full_config: dict, unencrypted: str = None) -> list:
    repo_and_group_list = []
    try:
        for repo_name in full_config.g("repos"):
            repo_config, _ = get_repo_config(full_config, repo_name)
            if repo_config.g("repo_uri") and (
                repo_config.g("repo_opts.repo_password")
                or repo_config.g("repo_opts.repo_password_command")
            ):
                # NPF-SEC-00014: Don't leak repository url including passwords in logs/ui
                repo_type, repo_uri = get_anon_repo_uri(repo_config.g("repo_uri"))
                repo_group = repo_config.g("repo_group")
                if unencrypted != repo_name:
                    repo_uri = npbackup.gui.common_gui_logic.ENCRYPTED_DATA_PLACEHOLDER
                repo_and_group_list.append(
                    gui_object("repo", repo_name, repo_group, repo_type, repo_uri)
                )
            else:
                logger.warning("Incomplete URI/password for repo {}".format(repo_name))
        for group_name in get_group_list(full_config):
            repo_and_group_list.append(gui_object("group", group_name, "", "", ""))
    except KeyError:
        logger.info("No operations repos configured")
    window["repo-and-group-list"].update(repo_and_group_list)
    return repo_and_group_list


def task_scheduler(config_file: str, full_config: dict) -> None:
    """
    Handle tasks for given repos / groups
    read_existing_scheduled_tasks return something like

    windows:
    [{'task_type': 'backup', 'object_type': 'repos', object_name: 'default', 'frequency_minutes': 15, 'start_date': datetime.datetime(2026, 3, 9, 17, 30, 23), 'days_of_week': []}]
    """

    layout = [
        [
            sg.Text(_t("operations_gui.currently_configured_tasks")),
        ],
        [
            sg.Push(),
            sg.Button(_t("generic.refresh"), key="--REFRESH-TASKS--", size=(18, 1)),
            sg.Button(
                _t("generic.remove_selected"), key="--REMOVE-TASK--", size=(18, 1)
            ),
        ],
        [
            sg.Table(
                values=[[]],
                headings=[
                    "Task type",
                    "Object Type",
                    "Object Name",
                    "Freq",
                    "Unit",
                    "Start date",
                    "Weekdays",
                ],
                key="-EXISTING-TASKS-",
                enable_events=True,
                auto_size_columns=True,
                justification="left",
                expand_x=True,
            ),
        ],
    ]
    layout += npbackup.gui.common_gui.scheduling_col(
        task_types=list(npbackup.task.SCHEDULER_TASKS.keys())
    )
    layout += [
        [
            sg.Push(),
            sg.Button(_t("generic.add") + " ▾", key="--ADD-TASK--", size=(18, 1)),
            sg.Button(_t("generic.quit"), key="--EXIT--", size=(18, 1)),
        ],
    ]

    window = sg.Window(
        layout=layout, title=_t("operations_gui.task_scheduler"), finalize=True
    )
    tasks = npbackup.gui.common_gui_logic.update_task_list(
        config_file, full_config, window
    )
    objects = npbackup.gui.common_gui_logic.get_objects(full_config)
    window["-OBJECT-SELECT-TASKS-"].update(objects[0], values=objects)
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--EXIT--"):
            break
        if event == "--ADD-TASK--":
            result, full_config = npbackup.gui.common_gui_logic.create_scheduled_task(
                values, full_config, config_file
            )
            if not result:
                popup_error(_t("config_gui.scheduled_task_creation_failure"))
                continue

            result = save_config(config_file, full_config)
            if not result:
                popup_error(
                    _t("config_gui.scheduled_task_creation_failure")
                    + "\n"
                    + _t("config_gui.cannot_save_configuration")
                )
                continue

            sg.popup(_t("config_gui.scheduled_task_creation_success"), keep_on_top=True)
            tasks = npbackup.gui.common_gui_logic.update_task_list(
                config_file, full_config, window
            )
        if event == "--REMOVE-TASK--":
            if not values["-EXISTING-TASKS-"]:
                popup_error(_t("config_gui.no_task_selected"))
                continue
            if len(values["-EXISTING-TASKS-"]) > 1:
                popup_error(_t("config_gui.select_only_one_task"))
                continue
            index = values["-EXISTING-TASKS-"][0]
            task_type = tasks[index]["task_type"]
            object_type = tasks[index]["object_type"]
            object_name = tasks[index]["object_name"]
            result = npbackup.task.delete_scheduled_task(
                config_file, task_type, object_type, object_name
            )
            tasks = npbackup.gui.common_gui_logic.update_task_list(
                config_file, full_config, window
            )
        if event == "--REFRESH-TASKS--":
            tasks = npbackup.gui.common_gui_logic.update_task_list(
                config_file, full_config, window
            )
        if event == "-EXISTING-TASKS-":
            if values["-EXISTING-TASKS-"]:
                npbackup.gui.common_gui_logic.update_task_ui_for_object(
                    full_config, window, tasks[values["-EXISTING-TASKS-"][0]]
                )
            elif tasks:
                npbackup.gui.common_gui_logic.update_task_ui_for_object(
                    full_config, window, tasks[0]
                )
    window.close()


def show_stats(statistics: List[dict]) -> None:
    """
    Shows a "nice" representation of repo statistics
    """

    data = []
    stats_type = None
    entry = None
    for entry in statistics:
        repo_name = list(entry.keys())[0]
        state = "Success" if entry[repo_name]["result"] else "Failure"

        entry_good = False

        # --stats output
        try:
            total_size = BytesConverter(
                entry[repo_name]["output"]["total_size"]
            ).human_iec_bytes
            total_file_count = entry[repo_name]["output"]["total_file_count"]
            snapshots_count = entry[repo_name]["output"]["snapshots_count"]
            stats_type = "std"
            data.append(
                [repo_name, state, total_size, total_file_count, snapshots_count]
            )
            entry_good = True
        except Exception:
            pass
        # --stats --mode raw-data output
        try:
            total_size = BytesConverter(
                entry[repo_name]["output"]["total_size"]
            ).human_iec_bytes
            total_uncompressed_size = BytesConverter(
                entry[repo_name]["output"]["total_uncompressed_size"]
            ).human
            compression_progress = (
                str(round(float(entry[repo_name]["output"]["compression_progress"]), 2))
                + " %"
            )
            compression_space_saving = (
                str(
                    round(
                        float(entry[repo_name]["output"]["compression_space_saving"]), 2
                    )
                )
                + " %"
            )
            compression_ratio = (
                str(round(float(entry[repo_name]["output"]["compression_ratio"]), 2))
                + " %"
            )
            total_blob_count = entry[repo_name]["output"]["total_blob_count"]
            snapshots_count = entry[repo_name]["output"]["snapshots_count"]

            stats_type = "raw"
            data.append(
                [
                    repo_name,
                    state,
                    total_size,
                    total_uncompressed_size,
                    compression_progress,
                    compression_space_saving,
                    compression_ratio,
                    total_blob_count,
                    snapshots_count,
                ]
            )
            entry_good = True
        except Exception:
            pass
        if not entry_good:
            data.append([repo_name, state])
            logger.debug(f"Failed statistics for entry: {entry}")

    if stats_type == "raw":
        headings = [
            "Repo",
            "Stat state",
            "Total size",
            "Total uncompress size",
            "Compress progress",
            "Compress space savings",
            "Compress Ratio",
            "Total Blob Count",
            "Snapshot Count",
        ]
    else:
        headings = [
            "Repo",
            "Stat state",
            "Total size",
            "Total File Count",
            "Snapshot Count",
        ]
    layout = [
        [
            sg.Table(
                values=data,
                headings=headings,
                justification="right",
                auto_size_columns=True,
                expand_x=True,
                expand_y=True,
            )
        ],
        [sg.Button(_t("generic.close"), key="--EXIT--")],
    ]

    window = sg.Window(
        "Statistics",
        layout,
        keep_on_top=True,
        element_justification="R",
        size=(800, 400),
    )
    while True:
        event, _ = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--EXIT--"):
            break
    window.close()


def operations_gui(full_config: dict, config_file: str) -> dict:
    """
    Operate on one or multiple repositories, or groups
    """

    def _get_repo_list(selected_rows):
        if not selected_rows:
            if sg.popup(
                _t("operations_gui.no_repo_selected_apply_all"),
                keep_on_top=True,
                custom_text=(_t("generic.no"), _t("generic.yes")),
            ) == _t("generic.no"):
                return False
            repos = get_repo_list(full_config)
        else:
            repos = []
            for index in selected_rows:
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
                            [[sg.Image(data=OEM_LOGO, subsample=4)]],
                            vertical_alignment="top",
                            justification="L",
                            element_justification="L",
                        ),
                        sg.Column(
                            [
                                [sg.Text(OEM_STRING, font="Arial 14")],
                            ],
                            justification="C",
                            element_justification="C",
                            vertical_alignment="C",
                        ),
                    ],
                    [sg.Text(_t("operations_gui.configured_repositories"))],
                    [
                        sg.Table(
                            values=[[]],
                            headings=headings,
                            key="repo-and-group-list",
                            auto_size_columns=True,
                            size=(None, 15),
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
                            size=(50, 1),
                        ),
                        sg.Button(
                            _t("operations_gui.task_scheduler"),
                            key="--TASK-SCHEDULER--",
                            size=(50, 1),
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.quick_check"),
                            key="--QUICK-CHECK--",
                            size=(50, 1),
                            visible=False,
                        ),
                        sg.Button(
                            _t("operations_gui.full_check"),
                            key="--FULL-CHECK--",
                            size=(50, 1),
                            visible=False,
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.repair_index"),
                            key="--REPAIR-INDEX--",
                            size=(50, 1),
                            visible=False,
                        ),
                        sg.Button(
                            _t("operations_gui.repair_snapshots"),
                            key="--REPAIR-SNAPSHOTS--",
                            size=(50, 1),
                            visible=False,
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.repair_packs"),
                            key="--REPAIR-PACKS--",
                            size=(50, 1),
                            visible=False,
                        ),
                        sg.Button(
                            _t("operations_gui.forget_using_retention_policy"),
                            key="--FORGET--",
                            size=(50, 1),
                            visible=False,
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.standard_prune"),
                            key="--STANDARD-PRUNE--",
                            size=(50, 1),
                            visible=False,
                        ),
                        sg.Button(
                            _t("operations_gui.max_prune"),
                            key="--MAX-PRUNE--",
                            size=(50, 1),
                            visible=False,
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.unlock"),
                            key="--UNLOCK--",
                            size=(50, 1),
                            visible=False,
                        ),
                        sg.Button(
                            _t("operations_gui.recover"),
                            key="--RECOVER--",
                            size=(50, 1),
                            visible=False,
                        ),
                    ],
                    [
                        sg.Button(
                            _t("operations_gui.stats"),
                            key="--STATS--",
                            size=(50, 1),
                        ),
                        sg.Button(
                            _t("operations_gui.stats_raw"),
                            key="--STATS-RAW--",
                            size=(50, 1),
                            visible=False,
                        ),
                        sg.Button(
                            _t("operations_gui.show_advanced"),
                            key="--ADVANCED--",
                            size=(50, 1),
                            visible=True,
                        ),
                    ],
                    [sg.Button(_t("generic.return"), key="--EXIT--")],
                ],
                element_justification="C",
            )
        ]
    ]

    right_click_menu = ["", [_t("config_gui.show_decrypted")]]

    window = sg.Window(
        _t("operations_gui.operation_center"),
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
                # Get first selected object
                object_name = _get_repo_list(values["repo-and-group-list"])[0]
            except Exception as exc:
                logger.error(f"Could not get object name: {exc}")
                logger.debug("Trace:", exc_info=True)
                object_name = None
            if not object_name:
                popup_error(_t("operations_gui.no_repo_selected"))
                continue
            manager_password = get_manager_password(full_config, object_name)
            # NPF-SEC-00009
            env_manager_password = os.environ.get("NPBACKUP_MANAGER_PASSWORD", None)
            if not manager_password:
                popup_error(_t("config_gui.no_manager_password_defined"))
                continue
            if (
                env_manager_password and env_manager_password == manager_password
            ) or npbackup.gui.common_gui_logic.ask_manager_password(manager_password):
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
                "--STATS-RAW--",
            ):
                window[button].update(visible=True)
                window["--ADVANCED--"].update(visible=False)
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
            "--STATS-RAW--",
        ):
            repos = _get_repo_list(values["repo-and-group-list"])

            repo_configs = {}
            monitoring_configs = {}
            if not repos:
                continue
            for repo_name in repos:
                repo_config, _ = get_repo_config(full_config, repo_name)
                repo_configs[repo_name] = repo_config
                monitoring_configs[repo_name] = get_monitoring_config(
                    repo_config, full_config
                )
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
                op_args = {"prune_max": True}
                gui_msg = _t("operations_gui.max_prune")
            if event == "--STATS--":
                operation = "stats"
                op_args = {}
                gui_msg = _t("operations_gui.stats")
            if event == "--STATS-RAW--":
                operation = "stats"
                op_args = {"subject": "--mode raw-data"}
                gui_msg = _t("operations_gui.stats_raw")
            if operation:
                data = gui_thread_runner(
                    None,
                    "group_runner",
                    operation=operation,
                    repo_configs=repo_configs,
                    monitoring_configs=monitoring_configs,
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
                            popup_error(data["reason"])
                    except Exception as exc:
                        popup_error(_t("generic.failure") + f": {exc}")
            else:
                logger.error(f"Bogus operation: {operation}")
                popup_error(f"Bogus operation: {operation}")

            event = "---STATE-UPDATE---"
        if event == "--TASK-SCHEDULER--":
            with HideWindow(window):
                task_scheduler(config_file, full_config)
            continue
        if event == "---STATE-UPDATE---":
            complete_repo_list = gui_update_state(window, full_config)
    window.close()

    return full_config


if __name__ == "__main__":
    logger.setLevel("INFO")
    logger.addHandler(logging.StreamHandler())
    from npbackup.configuration import get_default_config

    full_config = get_default_config()
    operations_gui(full_config, "config.yaml")
