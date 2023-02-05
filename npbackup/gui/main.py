#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.main"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023020101"


from typing import List, Optional, Tuple
import sys
import os
from logging import getLogger
import re
import dateutil
import queue
from time import sleep
import PySimpleGUI as sg
from ofunctions.threading import threaded, Future
from threading import Thread
from ofunctions.misc import BytesConverter
from npbackup.customization import (
    OEM_STRING,
    OEM_LOGO,
    LOADER_ANIMATION,
    FOLDER_ICON,
    FILE_ICON,
    LICENSE_TEXT,
    LICENSE_FILE,
)
from npbackup.gui.config import config_gui
from npbackup.core.runner import NPBackupRunner
from npbackup.core.i18n_helper import _t
from npbackup.core.upgrade_runner import run_upgrade, check_new_version


logger = getLogger(__intname__)

# Let's use mutable to get a cheap way of transfering data from thread to main program
# There are no possible race conditions since we don't modifiy the data from anywhere outside the thread
THREAD_SHARED_DICT = {}


def _about_gui(version_string: str, config_dict: dict) -> None:
    license_content = LICENSE_TEXT

    result = check_new_version(config_dict)
    if result:
        new_version = [
            sg.Button(
                _t("config_gui.auto_upgrade_launch"),
                key="autoupgrade",
                size=(12, 2),
            )
        ]
    elif result is False:
        new_version = [sg.Text(_t("generic.is_uptodate"))]
    elif result is None:
        new_version = [sg.Text(_t("config_gui.auto_upgrade_disabled"))]
    try:
        with open(LICENSE_FILE, "r") as file_handle:
            license_content = file_handle.read()
    except OSError:
        logger.info("Could not read license file.")

    layout = [
        [sg.Text(version_string)],
        new_version,
        [sg.Text("License: GNU GPLv3")],
        [sg.Multiline(license_content, size=(65, 20))],
        [sg.Button(_t("generic.accept"), key="exit")],
    ]

    window = sg.Window(
        _t("generic.about"),
        layout,
        keep_on_top=True,
        element_justification="C",
        finalize=True,
    )

    while True:
        event, _ = window.read()
        if event in [sg.WIN_CLOSED, "exit"]:
            break
        elif event == "autoupgrade":
            result = sg.PopupOKCancel(
                _t("config_gui.auto_ugprade_will_quit"), keep_on_top=True
            )
            if result == "OK":
                logger.info("Running GUI initiated upgrade")
                sub_result = run_upgrade(config_dict)
                if sub_result:
                    sys.exit(0)
                else:
                    sg.Popup(_t("config_gui.auto_upgrade_failed"), keep_on_top=True)
    window.close()


@threaded
def _get_gui_data(config_dict: dict) -> Future:
    runner = NPBackupRunner(config_dict=config_dict)
    snapshots = runner.list()
    current_state = runner.check_recent_backups()
    snapshot_list = []
    if snapshots:
        snapshots.reverse()  # Let's show newer snapshots first
        for snapshot in snapshots:
            snapshot_date = dateutil.parser.parse(snapshot["time"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            snapshot_username = snapshot["username"]
            snapshot_hostname = snapshot["hostname"]
            snapshot_id = snapshot["short_id"]
            snapshot_list.append(
                "{} {} {} {}@{} [ID {}]".format(
                    _t("main_gui.backup_from"),
                    snapshot_date,
                    _t("main_gui.run_as"),
                    snapshot_username,
                    snapshot_hostname,
                    snapshot_id,
                )
            )

    return current_state, snapshot_list


def get_gui_data(config_dict: dict) -> Tuple[bool, List[str]]:
    try:
        if (
            not config_dict["repo"]["repository"]
            and not config_dict["repo"]["password"]
        ):
            sg.Popup(_t("main_gui.repository_not_configured"))
            return None, None
    except KeyError:
        sg.Popup(_t("main_gui.repository_not_configured"))
        return None, None
    runner = NPBackupRunner(config_dict=config_dict)
    if not runner.has_binary:
        sg.Popup(_t("config_gui.no_binary"))
        return None, None
    # We get a thread result, hence pylint will complain the thread isn't a tuple
    # pylint: disable=E1101 (no-member)
    thread = _get_gui_data(config_dict)
    while not thread.done() and not thread.cancelled():
        sg.PopupAnimated(
            LOADER_ANIMATION,
            message=_t("main_gui.loading_data_from_repo"),
            time_between_frames=50,
            background_color="darkgreen",
        )
    sg.PopupAnimated(None)
    return thread.result()


def _gui_update_state(window, current_state: bool, snapshot_list: List[str]) -> None:
    if current_state:
        window["state-button"].Update(
            _t("generic.up_to_date"), button_color=("white", "springgreen4")
        )
    elif current_state is False:
        window["state-button"].Update(
            _t("generic.too_old"), button_color=("white", "darkred")
        )
    elif current_state is None:
        window["state-button"].Update(
            _t("generic.not_connected"), button_color=("white", "darkgrey")
        )
    window["snapshot-list"].Update(snapshot_list)


@threaded
def _make_treedata_from_json(ls_result: List[dict]) -> sg.TreeData:
    """
    Treelist data construction from json input that looks like

    [
        {"time": "2023-01-03T00:16:13.6256884+01:00", "parent": "40e16692030951e0224844ea160642a57786a765152eae10940293888ee1744a", "tree": "3f14a67b4d7cfe3974a2161a24beedfbf62ad289387207eda1bbb575533dbd33", "paths": ["C:\\GIT\\npbackup"], "hostname": "UNIMATRIX0", "username": "UNIMATRIX0\\Orsiris", "id": "a2103ca811e8b081565b162cca69ab5ac8974e43e690025236e759bf0d85afec", "short_id": "a2103ca8", "struct_type": "snapshot"}

        {"name": "Lib", "type": "dir", "path": "/C/GIT/npbackup/.venv/Lib", "uid": 0, "gid": 0, "mode": 2147484159, "permissions": "drwxrwxrwx", "mtime": "2022-12-28T19:58:51.85719+01:00", "atime": "2022-12-28T19:58:51.85719+01:00", "ctime": "2022-12-28T19:58:51.85719+01:00", "struct_type": "node"}
        {'name': 'xpTheme.tcl', 'type': 'file', 'path': '/C/GIT/npbackup/npbackup.dist/tk/ttk/xpTheme.tcl', 'uid': 0, 'gid': 0, 'size': 2103, 'mode': 438, 'permissions': '-rw-rw-rw-', 'mtime': '2022-09-05T14:18:52+02:00', 'atime': '2022-09-05T14:18:52+02:00', 'ctime': '2022-09-05T14:18:52+02:00', 'struct_type': 'node'}
        {'name': 'unsupported.tcl', 'type': 'file', 'path': '/C/GIT/npbackup/npbackup.dist/tk/unsupported.tcl', 'uid': 0, 'gid': 0, 'size': 10521, 'mode': 438, 'permissions': '-rw-rw-rw-', 'mtime': '2022-09-05T14:18:52+02:00', 'atime': '2022-09-05T14:18:52+02:00', 'ctime': '2022-09-05T14:18:52+02:00', 'struct_type': 'node'}
        {'name': 'xmfbox.tcl', 'type': 'file', 'path': '/C/GIT/npbackup/npbackup.dist/tk/xmfbox.tcl', 'uid': 0, 'gid': 0, 'size': 27064, 'mode': 438, 'permissions': '-rw-rw-rw-', 'mtime': '2022-09-05T14:18:52+02:00', 'atime': '2022-09-05T14:18:52+02:00', 'ctime': '2022-09-05T14:18:52+02:00', 'struct_type': 'node'}
    ]
    """
    treedata = sg.TreeData()

    # First entry of list of list should be the snapshot description and can be discarded
    # Since we use an iter now, first result was discarded by ls_window function already
    # ls_result.pop(0)
    for entry in ls_result:
        # Make sure we drop the prefix '/' so sg.TreeData does not get an empty root
        entry["path"] = entry["path"].lstrip("/")
        if os.name == "nt":
            # On windows, we need to make sure tree keys don't get duplicate because of lower/uppercase
            # Shown filenames aren't affected by this
            entry["path"] = entry["path"].lower()
        parent = os.path.dirname(entry["path"])

        # Make sure we normalize mtime, and remove microseconds
        mtime = dateutil.parser.parse(entry["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
        if entry["type"] == "dir" and entry["path"] not in treedata.tree_dict:
            treedata.Insert(
                parent=parent,
                key=entry["path"],
                text=entry["name"],
                values=["", mtime],
                icon=FOLDER_ICON,
            )
        elif entry["type"] == "file":
            size = BytesConverter(entry["size"]).human
            treedata.Insert(
                parent=parent,
                key=entry["path"],
                text=entry["name"],
                values=[size, mtime],
                icon=FILE_ICON,
            )
    return treedata


@threaded
def _ls_window(config: dict, snapshot_id: str) -> Future:
    runner = NPBackupRunner(config_dict=config)
    result = runner.ls(snapshot=snapshot_id)
    if not result:
        return result, None

    # Since ls returns an iter now, we need to use next
    snapshot_id = next(result)
    try:
        snap_date = dateutil.parser.parse(snapshot_id["time"])
    except (KeyError, IndexError):
        snap_date = "[inconnu]"
    try:
        short_id = snapshot_id["short_id"]
    except (KeyError, IndexError):
        short_id = "[inconnu]"
    try:
        username = snapshot_id["username"]
    except (KeyError, IndexError):
        username = "[inconnu]"
    try:
        hostname = snapshot_id["hostname"]
    except (KeyError, IndexError):
        hostname = "[inconnu]"

    backup_content = " {} {} {} {}@{} {} {}".format(
        _t("main_gui.backup_content_from"),
        snap_date,
        _t("main_gui.run_as"),
        username,
        hostname,
        _t("main_gui.identified_by"),
        short_id,
    )
    return backup_content, result


def ls_window(config: dict, snapshot: str) -> bool:
    snapshot_id = re.match(r".*\[ID (.*)\].*", snapshot).group(1)
    # We get a thread result, hence pylint will complain the thread isn't a tuple
    # pylint: disable=E1101 (no-member)
    thread = _ls_window(config, snapshot_id)

    while not thread.done() and not thread.cancelled():
        sg.PopupAnimated(
            LOADER_ANIMATION,
            message="{}. {}".format(
                _t("main_gui.loading_data_from_repo"),
                _t("main_gui.this_will_take_a_while"),
            ),
            time_between_frames=150,
            background_color="darkgreen",
        )
    sg.PopupAnimated(None)
    backup_content, ls_result = thread.result()
    if not backup_content or not ls_result:
        sg.PopupError(_t("main_gui.cannot_get_content"), keep_on_top=True)
        return False

    # Preload animation before thread so we don't have to deal with slow initial drawing due to cpu usage of thread
    # This is an arbitrary way to make sure we get to see the popup
    sg.PopupAnimated(
        LOADER_ANIMATION,
        message="{}...".format(_t("main_gui.creating_tree")),
        time_between_frames=1,
        background_color="darkgreen",
    )
    sleep(0.01)
    sg.PopupAnimated(
        LOADER_ANIMATION,
        message="{}...".format(_t("main_gui.creating_tree")),
        time_between_frames=1,
        background_color="darkgreen",
    )
    # We get a thread result, hence pylint will complain the thread isn't a tuple
    # pylint: disable=E1101 (no-member)
    thread = _make_treedata_from_json(ls_result)

    while not thread.done() and not thread.cancelled():
        sg.PopupAnimated(
            LOADER_ANIMATION,
            message="{}...".format(_t("main_gui.creating_tree")),
            time_between_frames=150,
            background_color="darkgreen",
        )
    sg.PopupAnimated(None)
    treedata = thread.result()

    left_col = [
        [sg.Text(backup_content)],
        [
            sg.Tree(
                data=treedata,
                headings=[_t("generic.size"), _t("generic.modification_date")],
                auto_size_columns=True,
                select_mode=sg.TABLE_SELECT_MODE_EXTENDED,
                num_rows=40,
                col0_heading=_t("generic.path"),
                col0_width=80,
                key="-TREE-",
                show_expanded=False,
                enable_events=True,
                expand_x=True,
                expand_y=True,
                vertical_scroll_only=False,
            ),
        ],
        [
            sg.Button(_t("main_gui.restore_to"), key="restore_to"),
            sg.Button(_t("generic.quit"), key="quit"),
        ],
    ]
    layout = [[sg.Column(left_col, element_justification="C")]]
    window = sg.Window(
        _t("generic.content"), layout=layout, grab_anywhere=True, keep_on_top=False
    )
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_CLOSE_ATTEMPTED_EVENT, "quit"):
            break
        if event == "restore_to":
            if not values["-TREE-"]:
                sg.PopupError(_t("main_gui.select_folder"))
                continue
            restore_window(config, snapshot_id, values["-TREE-"])

    # Closing a big sg.TreeData is really slow
    # This is a little trichery lesson
    # Still we should open a case at PySimpleGUI to know why closing a sg.TreeData window is painfully slow # TODO
    window.hide()
    Thread(target=window.close, args=())

    return True


@threaded
def _restore_window(
    config_dict: dict, snapshot: str, target: str, restore_includes: Optional[List]
) -> Future:
    runner = NPBackupRunner(config_dict=config_dict)
    runner.verbose = True
    result = runner.restore(snapshot, target, restore_includes)
    THREAD_SHARED_DICT["exec_time"] = runner.exec_time
    return result


def restore_window(
    config_dict: dict, snapshot_id: str, restore_include: List[str]
) -> None:
    left_col = [
        [
            sg.Text(_t("main_gui.destination_folder")),
            sg.In(size=(25, 1), enable_events=True, key="-RESTORE-FOLDER-"),
            sg.FolderBrowse(),
        ],
        # Do not show which folder gets to get restored since we already make that selection
        # [sg.Text(_t("main_gui.only_include")), sg.Text(includes, size=(25, 1))],
        [
            sg.Button(_t("main_gui.restore"), key="restore"),
            sg.Button(_t("generic.cancel"), key="cancel"),
        ],
    ]

    layout = [[sg.Column(left_col, element_justification="C")]]
    window = sg.Window(
        _t("main_gui.restoration"), layout=layout, grab_anywhere=True, keep_on_top=False
    )
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_CLOSE_ATTEMPTED_EVENT, "cancel"):
            break
        if event == "restore":
            # We get a thread result, hence pylint will complain the thread isn't a tuple
            # pylint: disable=E1101 (no-member)
            thread = _restore_window(
                config_dict=config_dict,
                snapshot=snapshot_id,
                target=values["-RESTORE-FOLDER-"],
                restore_includes=restore_include,
            )
            while not thread.done() and not thread.cancelled():
                sg.PopupAnimated(
                    LOADER_ANIMATION,
                    message="{}...".format(_t("main_gui.restore_in_progress")),
                    time_between_frames=50,
                    background_color="darkgreen",
                )
            sg.PopupAnimated(None)

            result = thread.result()
            try:
                exec_time = THREAD_SHARED_DICT["exec_time"]
            except KeyError:
                exec_time = "N/A"
            if result:
                sg.Popup(
                    _t("main_gui.restore_done", seconds=exec_time), keep_on_top=True
                )
            else:
                sg.PopupError(
                    _t("main_gui.restore_failed", seconds=exec_time), keep_on_top=True
                )
            break
    window.close()


@threaded
def _gui_backup(config_dict, stdout) -> Future:
    runner = NPBackupRunner(config_dict=config_dict)
    runner.verbose = (
        True  # We must use verbose so we get progress output from ResticRunner
    )
    runner.stdout = stdout
    result = runner.backup(
        force=True,
    )  # Since we run manually, force backup regardless of recent backup state
    THREAD_SHARED_DICT["exec_time"] = runner.exec_time
    return result


def main_gui(config_dict: dict, config_file: str, version_string: str):
    backup_destination = _t("main_gui.local_folder")
    backend_type = None
    try:
        backend_type = config_dict["repo"]["repository"].split(":")[0].upper()
        if backend_type in [
            "REST",
            "S3",
            "B2",
            "SFTP",
            "SWIFT",
            "AZURE",
            "GZ",
            "RCLONE",
        ]:
            backup_destination = "{} {}".format(
                _t("main_gui.external_server"), backend_type
            )
    except (KeyError, AttributeError, TypeError):
        pass

    right_click_menu = ["", [_t("generic.destination")]]

    layout = [
        [
            sg.Column(
                [
                    [sg.Text(OEM_STRING, font="Arial 14")],
                    [
                        sg.Column(
                            [[sg.Image(data=OEM_LOGO)]], vertical_alignment="top"
                        ),
                        sg.Column(
                            [
                                [sg.Text("{}: ".format(_t("main_gui.backup_state")))],
                                [
                                    sg.Button(
                                        _t("generic.unknown"),
                                        key="state-button",
                                        button_color=("white", "grey"),
                                    )
                                ],
                            ],
                            vertical_alignment="top",
                        ),
                    ],
                    [
                        sg.Text(
                            "{} {}".format(
                                _t("main_gui.backup_list_to"), backup_destination
                            )
                        )
                    ],
                    [sg.Listbox(values=[], key="snapshot-list", size=(80, 15))],
                    [
                        sg.Button(_t("main_gui.launch_backup"), key="launch-backup"),
                        sg.Button(_t("main_gui.see_content"), key="see-content"),
                        sg.Button(_t("generic.configure"), key="configure"),
                        sg.Button(_t("generic.about"), key="about"),
                        sg.Button(_t("generic.quit"), key="exit"),
                    ],
                ],
                element_justification="C",
            )
        ]
    ]

    window = sg.Window(
        OEM_STRING,
        layout,
        default_element_size=(12, 1),
        text_justification="r",
        auto_size_text=True,
        auto_size_buttons=False,
        no_titlebar=False,
        grab_anywhere=False,
        keep_on_top=False,
        alpha_channel=0.9,
        default_button_element_size=(12, 1),
        right_click_menu=right_click_menu,
        finalize=True,
    )

    window.read(timeout=1)
    current_state, snapshot_list = get_gui_data(config_dict)
    _gui_update_state(window, current_state, snapshot_list)
    while True:
        event, values = window.read(timeout=60000)

        if event in (sg.WIN_CLOSED, "exit"):
            break
        if event == "launch-backup":
            progress_windows_layout = [
                [
                    sg.Multiline(
                        size=(80, 10), key="progress", expand_x=True, expand_y=True
                    )
                ]
            ]
            progress_window = sg.Window(
                _t("main_gui.backup_activity"),
                layout=progress_windows_layout,
                finalize=True,
            )
            # We need to read that window at least once fopr it to exist
            progress_window.read(timeout=1)
            stdout = queue.Queue()

            # let's use a mutable so the backup thread can modify it
            # We get a thread result, hence pylint will complain the thread isn't a tuple
            # pylint: disable=E1101 (no-member)
            thread = _gui_backup(config_dict=config_dict, stdout=stdout)
            while not thread.done() and not thread.cancelled():
                try:
                    stdout_line = stdout.get(timeout=0.01)
                except queue.Empty:
                    pass
                else:
                    if stdout_line:
                        progress_window["progress"].Update(stdout_line)
                sg.PopupAnimated(
                    LOADER_ANIMATION,
                    message="{}...".format(_t("main_gui.backup_in_progress")),
                    time_between_frames=50,
                    background_color="darkgreen",
                )
            sg.PopupAnimated(None)
            result = thread.result()
            try:
                exec_time = THREAD_SHARED_DICT["exec_time"]
            except KeyError:
                exec_time = "N/A"
            current_state, snapshot_list = get_gui_data(config_dict)
            _gui_update_state(window, current_state, snapshot_list)
            if not result:
                sg.PopupError(
                    _t("main_gui.backup_failed", seconds=exec_time), keep_on_top=True
                )
            else:
                sg.Popup(
                    _t("main_gui.backup_done", seconds=exec_time), keep_on_top=True
                )
            progress_window.close()
            continue
        if event == "see-content":
            if not values["snapshot-list"]:
                sg.Popup(_t("main_gui.select_backup"), keep_on_top=True)
                continue
            ls_window(config_dict, snapshot=values["snapshot-list"][0])
        if event == "configure":
            config_dict = config_gui(config_dict, config_file)
            # Make sure we trigger a GUI refresh when configuration is changed
            event = "state-button"
        if event == _t("generic.destination"):
            try:
                if backend_type:
                    if backend_type in ["REST", "SFTP"]:
                        destination_string = config_dict["repo"]["repository"].split(
                            "@"
                        )[-1]
                    else:
                        destination_string = config_dict["repo"]["repository"]
                sg.PopupNoFrame(destination_string)
            except (TypeError, KeyError):
                sg.PopupNoFrame(_t("main_gui.unknown_repo"))
        if event == "about":
            _about_gui(version_string, config_dict)
        if event == "state-button":
            current_state, snapshot_list = get_gui_data(config_dict)
            _gui_update_state(window, current_state, snapshot_list)
            if current_state is None:
                sg.Popup(_t("main_gui.cannot_get_repo_status"))
