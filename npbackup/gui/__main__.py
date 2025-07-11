#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup-gui"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"


from typing import List, Optional, Tuple
import sys
import os
import re
import gc
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
import _tkinter
import npbackup.configuration
import npbackup.common
from resources.customization import (
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
    OEM_ICON,
    SHORT_PRODUCT_NAME,
)
from npbackup.gui.config import config_gui, ask_manager_password
from npbackup.gui.operations import operations_gui
from npbackup.gui.helpers import get_anon_repo_uri, gui_thread_runner, HideWindow
from npbackup.gui.handle_window import handle_current_window
from npbackup.core.i18n_helper import _t
from npbackup.core import upgrade_runner
from npbackup.path_helper import CURRENT_DIR
from npbackup.__version__ import version_dict, version_string
from npbackup.__debug__ import _DEBUG, _NPBACKUP_ALLOW_AUTOUPGRADE_DEBUG
from npbackup.restic_wrapper import ResticRunner
from npbackup.restic_wrapper import schema


logger = getLogger()
backend_binary = None
__no_lock = False
__full_concurrency = False
__repo_aware_concurrency = False

# This bool allows to not show errors on freshly configured repos or first runs, when repo isn't initialized yet
# Also prevents showing errors when config was just changed
GUI_STATUS_IGNORE_ERRORS = True


sg.theme(SIMPLEGUI_THEME)
sg.SetOptions(icon=OEM_ICON)


def popup_wait_for_upgrade(text: str):

    layout = [[sg.Text(text)]]
    window = sg.Window(
        "Upgrade", layout=layout, no_titlebar=False, keep_on_top=True, finalize=True
    )
    window.read(timeout=0)
    return window


def about_gui(
    version_string: str,
    config_file: str,
    full_config: dict = None,
    auto_upgrade_result: bool = False,
) -> None:

    if auto_upgrade_result:
        new_version = [
            sg.Button(
                _t("config_gui.auto_upgrade_launch"),
                key="autoupgrade",
                size=(12, 2),
            )
        ]
    elif auto_upgrade_result is False:
        new_version = [sg.Text(_t("generic.is_uptodate"))]
    else:
        # auto_upgrade_result is None
        new_version = [sg.Text(_t("config_gui.auto_upgrade_disabled"))]
    layout = [
        [sg.Text(version_string)],
        new_version,
        [sg.Text("License: GNU GPLv3")],
        [sg.Multiline(LICENSE_TEXT, size=(65, 20), disabled=True)],
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
        if event == "autoupgrade":
            result = sg.PopupOKCancel(
                _t("config_gui.auto_upgrade_will_quit"), keep_on_top=True
            )
            if result == "OK":
                logger.info("Running GUI initiated upgrade")
                sub_result = upgrade_runner.run_upgrade(config_file, full_config)
                if sub_result:
                    sys.exit(0)
                else:
                    sg.Popup(_t("config_gui.auto_upgrade_failed"), keep_on_top=True)
    window.close()


def viewer_create_repo(viewer_repo_uri: str, viewer_repo_password: str) -> dict:
    """
    Create a minimal repo config for viewing purposes
    """
    repo_config = CommentedMap()
    repo_config.s("name", "external")
    repo_config.s("repo_uri", viewer_repo_uri)
    repo_config.s("repo_opts", CommentedMap())
    repo_config.s("repo_opts.repo_password", viewer_repo_password)
    # Let's set default backup age to 24h
    repo_config.s("repo_opts.minimum_backup_age", 1435)
    # NPF-SEC-00005 Add restore permission
    repo_config.s("permissions", "restore_only")

    return repo_config


def viewer_repo_gui(
    viewer_repo_uri: str = None, viewer_repo_password: str = None
) -> Tuple[str, str]:
    """
    Ask for repo and password if not defined in env variables
    """
    layout = [
        [
            sg.Text(_t("config_gui.backup_repo_uri"), size=(35, 1)),
            sg.Input(viewer_repo_uri, key="-REPO-URI-"),
        ],
        [
            sg.Text(_t("config_gui.backup_repo_password"), size=(35, 1)),
            sg.Input(viewer_repo_password, key="-REPO-PASSWORD-", password_char="*"),
        ],
        [
            sg.Push(),
            sg.Button(_t("generic.cancel"), key="--CANCEL--"),
            sg.Button(_t("generic.accept"), key="--ACCEPT--"),
        ],
    ]
    window = sg.Window("Viewer", layout, keep_on_top=True, grab_anywhere=True)
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--CANCEL--"):
            break
        if event == "--ACCEPT--":
            if values["-REPO-URI-"] and values["-REPO-PASSWORD-"]:
                break
            sg.Popup(_t("main_gui.repo_and_password_cannot_be_empty"))
    window.close()
    return values["-REPO-URI-"], values["-REPO-PASSWORD-"]


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

    Since v3-rc6, we're actually using a msgspec.Struct representation which uses dot notation, but only on Python 3.8+
    We still rely on json for Python 3.7
    """
    treedata = sg.TreeData()
    count = 0
    if isinstance(ls_result[0], dict):
        HAVE_MSGSPEC = False
    else:
        HAVE_MSGSPEC = True
    if not HAVE_MSGSPEC:
        logger.info(
            "Using basic json representation for data which is slow and memory hungry. Consider using a newer OS that supports Python 3.8+"
        )

    # For performance reasons, we don't refactor this code in order to avoid allocating more variables
    for entry in ls_result:
        # Make sure we drop the prefix '/' so sg.TreeData does not get an empty root
        if HAVE_MSGSPEC:
            entry.path = entry.path.lstrip("/")
            if os.name == "nt":
                # On windows, we need to make sure tree keys don't get duplicate because of lower/uppercase
                # Shown filenames aren't affected by this
                entry.path = entry.path.lower()
            parent = os.path.dirname(entry.path)

            # Make sure we normalize mtime, and remove microseconds
            # dateutil.parser.parse is *really* cpu hungry, let's replace it with a dumb alternative
            # mtime = dateutil.parser.parse(entry["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
            mtime = entry.mtime.strftime("%Y-%m-%d %H:%M:%S")
            name = os.path.basename(entry.path)
            if (
                entry.type == schema.LsNodeType.DIR
                and entry.path not in treedata.tree_dict
            ):
                treedata.Insert(
                    parent=parent,
                    key=entry.path,
                    text=name,
                    values=["", mtime],
                    icon=FOLDER_ICON,
                )
            elif entry.type == schema.LsNodeType.FILE:
                size = BytesConverter(entry.size).human
                treedata.Insert(
                    parent=parent,
                    key=entry.path,
                    text=name,
                    values=[size, mtime],
                    icon=FILE_ICON,
                )
            elif entry.type == schema.LsNodeType.SYMLINK:
                treedata.Insert(
                    parent=parent,
                    key=entry.path,
                    text=name,
                    values=["", mtime],
                    icon=SYMLINK_ICON,
                )
            elif entry.type == schema.LsNodeType.IRREGULAR:
                treedata.Insert(
                    parent=parent,
                    key=entry.path,
                    text=name,
                    values=["", mtime],
                    icon=IRREGULAR_FILE_ICON,
                )
        else:
            entry["path"] = entry["path"].lstrip("/")
            if os.name == "nt":
                # On windows, we need to make sure tree keys don't get duplicate because of lower/uppercase
                # Shown filenames aren't affected by this
                entry["path"] = entry["path"].lower()
            parent = os.path.dirname(entry["path"])

            # Make sure we normalize mtime, and remove microseconds
            # dateutil.parser.parse is *really* cpu hungry, let's replace it with a dumb alternative
            # mtime = dateutil.parser.parse(entry["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
            mtime = entry["mtime"][0:19]
            name = os.path.basename(entry["name"])
            if entry["type"] == "dir" and entry["path"] not in treedata.tree_dict:
                treedata.Insert(
                    parent=parent,
                    key=entry["path"],
                    text=name,
                    values=["", mtime],
                    icon=FOLDER_ICON,
                )
            elif entry["type"] == "file":
                size = BytesConverter(entry["size"]).human
                treedata.Insert(
                    parent=parent,
                    key=entry["path"],
                    text=name,
                    values=[size, mtime],
                    icon=FILE_ICON,
                )
            elif entry["type"] == "symlink":
                treedata.Insert(
                    parent=parent,
                    key=entry["path"],
                    text=name,
                    values=["", mtime],
                    icon=SYMLINK_ICON,
                )
            elif entry["type"] == "irregular":
                treedata.Insert(
                    parent=parent,
                    key=entry["path"],
                    text=name,
                    values=["", mtime],
                    icon=IRREGULAR_FILE_ICON,
                )

        # Since the thread is heavily CPU bound, let's add a minimal
        # arbitrary sleep time to let GUI update
        # In a 130k entry scenario, using count % 1000 added less than a second on a 25 second run
        count += 1
        if not count % 2000:
            sleep(0.0001)
            logger.debug(f"Processed {count} entries")
    return treedata


def ls_window(parent_window: sg.Window, repo_config: dict, snapshot_id: str) -> bool:
    result = gui_thread_runner(
        repo_config,
        "ls",
        snapshot=snapshot_id,
        __stdout=False,
        __autoclose=True,
        __compact=True,
        __backend_binary=backend_binary,
        __no_lock=__no_lock,
    )
    if not result or not result["result"]:
        sg.Popup(_t("main_gui.snapshot_is_empty"))
        return None, None

    # result is {"result": True, "output": [{snapshot_description}, {entry}, {entry}]}
    # content = result["output"]
    # First entry of snapshot list is the snapshot description
    snapshot = result["output"].pop(0)
    try:
        snap_date = dateutil.parser.parse(snapshot["time"])
    except (KeyError, IndexError, TypeError):
        snap_date = "[inconnu]"
    try:
        short_id = snapshot["short_id"]
    except (KeyError, IndexError, TypeError):
        short_id = None
    try:
        username = snapshot["username"]
    except (KeyError, IndexError, TypeError):
        username = "[inconnu]"
    try:
        hostname = snapshot["hostname"]
    except (KeyError, IndexError, TypeError):
        hostname = "[inconnu]"

    backup_id = f"{_t('main_gui.backup_content_from')} {snap_date} {_t('main_gui.run_as')} {username}@{hostname} {_t('main_gui.identified_by')} {short_id}"
    if not backup_id or not snapshot or not short_id:
        sg.PopupError(_t("main_gui.cannot_get_content"), keep_on_top=True)
        return False

    # The following thread is cpu intensive, so the GUI will update sluggerish
    # In the thread, we added a sleep argument every 1000 iters so we get to update
    # the GUI. Earlier fix was to preload animation

    # We get a thread result, hence pylint will complain the thread isn't a tuple
    # pylint: disable=E1101 (no-member)

    thread = _make_treedata_from_json(result["output"])
    while not thread.done() and not thread.cancelled():
        sg.PopupAnimated(
            LOADER_ANIMATION,
            message="{}...".format(_t("main_gui.creating_tree")),
            time_between_frames=50,
            background_color=BG_COLOR_LDR,
            text_color=TXT_COLOR_LDR,
        )
    sg.PopupAnimated(None)

    logger.info("Finished creating data tree")

    left_col = [
        [sg.Text(backup_id)],
        [
            sg.Tree(
                data=thread.result(),
                headings=[_t("generic.size"), _t("generic.modification_date")],
                auto_size_columns=True,
                select_mode=sg.TABLE_SELECT_MODE_EXTENDED,
                num_rows=40,
                col0_heading=_t("generic.path"),
                col0_width=80,
                key="-TREE-",
                show_expanded=False,
                enable_events=False,
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
        _t("generic.content"),
        layout=layout,
        grab_anywhere=True,
        keep_on_top=False,
        enable_close_attempted_event=True,
    )

    # Reclaim memory from thread result
    # Note from v3 dev: This doesn't actually improve memory usage
    del thread
    del result
    gc.collect()

    with HideWindow(parent_window):
        while True:
            event, values = window.read()
            if event in (
                sg.WIN_CLOSED,
                sg.WIN_X_EVENT,
                "quit",
                "-WINDOW CLOSE ATTEMPED-",
            ):
                break
            if event == "restore_to":
                if not values["-TREE-"]:
                    sg.PopupError(_t("main_gui.select_folder"), keep_on_top=True)
                    continue
                with HideWindow(window):
                    restore_window(repo_config, snapshot_id, values["-TREE-"])

        # Closing a big sg.Tree is really slow
        # We can workaround this by emptying the Tree with a new sg.TreeData() object
        # before closing the window
        window["-TREE-"].update(values=sg.TreeData())
        window.close()
        del window
        return True


def restore_window(
    repo_config: dict, snapshot_id: str, restore_include: List[str]
) -> None:
    def _restore_window(
        repo_config: dict, snapshot: str, target: str, restore_includes: Optional[List]
    ) -> bool:
        result = gui_thread_runner(
            repo_config,
            "restore",
            snapshot=snapshot,
            target=target,
            __gui_msg=_t("main_gui.restore_in_progress"),
            __compact=False,
            restore_includes=restore_includes,
            __backend_binary=backend_binary,
            __autoclose=True,
            __no_lock=__no_lock,
            __full_concurrency=__full_concurrency,
            __repo_aware_concurrency=__repo_aware_concurrency,
        )
        try:
            return result["result"]
        except TypeError:
            return result

    left_col = [
        [
            sg.Text(_t("main_gui.destination_folder")),
            sg.In(size=(25, 1), enable_events=True, key="-RESTORE-FOLDER-"),
            sg.FolderBrowse(),
        ],
        [
            sg.Button(_t("main_gui.restore"), key="restore"),
            sg.Button(_t("generic.cancel"), key="cancel"),
        ],
    ]

    layout = [[sg.Column(left_col, element_justification="C")]]
    window = sg.Window(
        _t("main_gui.restoration"), layout=layout, grab_anywhere=True, keep_on_top=False
    )
    result = None
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "cancel"):
            break
        if event == "restore":
            with HideWindow(window):
                result = _restore_window(
                    repo_config,
                    snapshot=snapshot_id,
                    target=values["-RESTORE-FOLDER-"],
                    restore_includes=restore_include,
                )
                if result:
                    sg.popup(_t("main_gui.restore_done"), keep_on_top=True)
                else:
                    sg.popup(_t("main_gui.restore_failed"), keep_on_top=True)
                break
    window.close()
    return result


def backup(repo_config: dict) -> bool:
    gui_msg = _t("main_gui.gui_activity")
    # on_success = _t("main_gui.backup_done")
    # on_failure = _t("main_gui.backup_failed")
    result = gui_thread_runner(
        repo_config,
        "backup",
        force=True,
        __autoclose=False,
        __compact=False,
        __gui_msg=gui_msg,
        __backend_binary=backend_binary,
        __no_lock=__no_lock,
        __full_concurrency=__full_concurrency,
        __repo_aware_concurrency=__repo_aware_concurrency,
        honor_delay=False,
    )
    try:
        return result["result"]
    except TypeError:
        return result


def forget_snapshot(repo_config: dict, snapshot_ids: List[str]) -> bool:
    gui_msg = f"{_t('generic.forgetting')} {snapshot_ids} {_t('main_gui.this_will_take_a_while')}"
    # on_success = f"{snapshot_ids} {_t('generic.forgotten')} {_t('generic.successfully')}"
    # on_failure = _t("main_gui.forget_failed")
    result = gui_thread_runner(
        repo_config,
        "forget",
        snapshots=snapshot_ids,
        __gui_msg=gui_msg,
        __autoclose=True,
        __backend_binary=backend_binary,
        __no_lock=__no_lock,
        __full_concurrency=__full_concurrency,
        __repo_aware_concurrency=__repo_aware_concurrency,
    )
    try:
        return result["result"]
    except TypeError:
        return result


def _main_gui(viewer_mode: bool):
    global logger
    global backend_binary
    global __no_lock
    global GUI_STATUS_IGNORE_ERRORS

    def check_for_auto_upgrade(config_file: str, full_config: dict) -> bool:
        if full_config and full_config.g("global_options.auto_upgrade_server_url"):
            upgrade_popup = popup_wait_for_upgrade(_t("main_gui.auto_upgrade_checking"))
            auto_upgrade_result = upgrade_runner.check_new_version(full_config)
            upgrade_popup.close()
            if auto_upgrade_result:
                r = sg.Popup(
                    _t("config_gui.auto_upgrade_launch"),
                    custom_text=(_t("generic.yes"), _t("generic.no")),
                )
                if r == _t("generic.yes"):
                    sg.Popup(
                        _t("main_gui.upgrade_in_progress"),
                    )
                    result = upgrade_runner.run_upgrade(config_file, full_config)
                    if not result:
                        sg.Popup(_t("config_gui.auto_upgrade_failed"))
            return auto_upgrade_result
        return None

    def select_config_file(config_file: str = None) -> None:
        """
        Option to select a configuration file
        """
        layout = [
            [
                sg.Text(_t("main_gui.select_config_file")),
                sg.Input(config_file, key="-config_file-"),
                sg.FileBrowse(_t("generic.select_file")),
            ],
            [
                sg.Push(),
                sg.Button(_t("generic.cancel"), key="--CANCEL--"),
                sg.Button(_t("main_gui.new_config"), key="--NEW-CONFIG--"),
                sg.Button(_t("main_gui.open_existing_file"), key="--LOAD--"),
            ],
        ]
        window = sg.Window("Configuration File", layout=layout, keep_on_top=True)
        while True:
            action = None
            event, values = window.read()
            if event in (sg.WIN_X_EVENT, sg.WIN_CLOSED, "--CANCEL--"):
                action = "--CANCEL--"
                break
            if event == "--NEW-CONFIG--":
                action = event
                config_file = Path(values["-config_file-"])
                break
            if event == "--LOAD--":
                config_file = Path(values["-config_file-"])
                if not values["-config_file-"] or not config_file.exists():
                    sg.PopupError(_t("generic.file_does_not_exist"), keep_on_top=True)
                    continue
                try:
                    with HideWindow(window):
                        full_config = npbackup.configuration.load_config(config_file)
                except EnvironmentError as exc:
                    sg.PopupError(exc, keep_on_top=True)
                    continue
                if not full_config:
                    sg.PopupError(_t("generic.bad_file"), keep_on_top=True)
                    continue
                break
        window.close()
        return config_file, action

    def gui_update_state(current_state, backup_tz, snapshot_list, repo_type) -> None:

        if current_state:
            window["--STATE-BUTTON--"].Update(
                "{}: {}".format(
                    _t("generic.up_to_date"), backup_tz.replace(microsecond=0)
                ),
                button_color=GUI_STATE_OK_BUTTON,
            )
        elif current_state is False and backup_tz == datetime(1, 1, 1, 0, 0):
            window["--STATE-BUTTON--"].Update(
                _t("generic.no_snapshots"), button_color=GUI_STATE_OLD_BUTTON
            )
        elif current_state is False:
            window["--STATE-BUTTON--"].Update(
                "{}: {}".format(_t("generic.old"), backup_tz.replace(microsecond=0)),
                button_color=GUI_STATE_OLD_BUTTON,
            )
        elif current_state is None:
            window["--STATE-BUTTON--"].Update(
                _t("generic.not_connected_yet"), button_color=GUI_STATE_UNKNOWN_BUTTON
            )
        window["-repo_type-"].Update(repo_type)
        window["snapshot-list"].Update(snapshot_list)

    def get_gui_data(repo_config: dict) -> Tuple[bool, List[str]]:
        global GUI_STATUS_IGNORE_ERRORS

        window["--STATE-BUTTON--"].Update(
            _t("generic.please_wait"), button_color="orange"
        )
        gui_msg = _t("main_gui.loading_snapshot_list_from_repo")
        result = gui_thread_runner(
            repo_config,
            "snapshots",
            __gui_msg=gui_msg,
            __autoclose=True,
            __compact=True,
            __backend_binary=backend_binary,
            __ignore_errors=GUI_STATUS_IGNORE_ERRORS,
            __no_lock=__no_lock,
            __full_concurrency=__full_concurrency,
            __repo_aware_concurrency=__repo_aware_concurrency,
            errors_allowed=True,
        )
        GUI_STATUS_IGNORE_ERRORS = False
        try:
            if not result or not result["result"]:
                snapshots = None
            else:
                snapshots = result["output"]
        except TypeError:
            snapshots = None
            sg.popup_error(_t("main_gui.failed_operation"))
        try:
            min_backup_age = repo_config.g("repo_opts.minimum_backup_age")
        except AttributeError:
            min_backup_age = 0

        current_state, backup_tz = ResticRunner._has_recent_snapshot(
            snapshots, min_backup_age
        )
        snapshot_list = []
        if snapshots:
            snapshots.reverse()  # Let's show newer snapshots first
            for snapshot in snapshots:
                # So we get different snapshot time formats depending on platforms:
                # windows   2024-09-06T13:58:10.7684887+02:00
                # Linux     2024-09-06T11:39:06.566382538Z
                if re.match(
                    r"[0-9]{4}-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]\..*(Z|[+-][0-2][0-9]:[0-9]{2})?",
                    snapshot["time"],
                ):
                    snapshot_date = dateutil.parser.parse(snapshot["time"]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                else:
                    snapshot_date = "Unparsable"
                snapshot_username = snapshot["username"]
                snapshot_hostname = snapshot["hostname"]
                snapshot_id = snapshot["short_id"]
                try:
                    tags = snapshot["tags"]
                    if isinstance(tags, list):
                        tags = ", ".join(tags)
                    snapshot_tags = tags
                except KeyError:
                    snapshot_tags = ""
                snapshot_list.append(
                    [
                        snapshot_id,
                        snapshot_date,
                        snapshot_hostname,
                        snapshot_username,
                        snapshot_tags,
                    ]
                )
        return current_state, backup_tz, snapshot_list

    def get_config_file(config_file: str = None) -> str:
        """
        Load config file until we got something
        """
        global GUI_STATUS_IGNORE_ERRORS

        config_exists = True
        full_config = None
        if config_file:
            if not config_file.exists():
                config_exists = False
            else:
                try:
                    full_config = npbackup.configuration.load_config(config_file)
                except EnvironmentError as exc:
                    sg.PopupError(exc, keep_on_top=True)
                    return None, None
                if full_config:
                    return full_config, config_file
        else:
            config_file = "npbackup.conf"
            config_exists = False

        while True:
            if not config_exists or not config_file.exists():
                config_file, action = select_config_file(config_file=config_file)
                if action == "--CANCEL--":
                    break
                if action == "--NEW-CONFIG--":
                    full_config = config_gui(
                        npbackup.configuration.get_default_config(), config_file
                    )
            if config_file:
                logger.info(f"Using configuration file {config_file}")
                try:
                    full_config = npbackup.configuration.load_config(config_file)
                    GUI_STATUS_IGNORE_ERRORS = True
                except EnvironmentError as exc:
                    sg.PopupError(exc, keep_on_top=True)
                else:
                    if not full_config:
                        sg.PopupError(
                            f"{_t('main_gui.config_error')} {config_file}",
                            keep_on_top=True,
                        )
                        config_exists = False
                    else:
                        config_exists = True
                        break
        return full_config, config_file

    def get_config(
        config_file: str = None, window: sg.Window = None, repo_name: str = None
    ) -> Tuple:
        global __full_concurrency
        global __repo_aware_concurrency
        full_config, config_file = get_config_file(config_file=config_file)
        if full_config and config_file:
            __full_concurrency = full_config.g("global_options.full_concurrency")
            if __full_concurrency is None:
                __full_concurrency = False
            __repo_aware_concurrency = full_config.g(
                "global_options.repo_aware_concurrency"
            )
            if __repo_aware_concurrency is None:
                __repo_aware_concurrency = False
            # If no repo name is given, just show first one
            try:
                if not repo_name:
                    repo_name = npbackup.configuration.get_repo_list(full_config)[0]
                repo_config, _ = npbackup.configuration.get_repo_config(
                    full_config, repo_name=repo_name
                )
                backup_destination = _t("main_gui.local_folder")
                repo_type, repo_uri = get_anon_repo_uri(repo_config.g("repo_uri"))
            except IndexError:
                repo_config = None
                backup_destination = "None"
                repo_type = "None"
                repo_uri = "None"
        else:
            repo_config = None
            backup_destination = "None"
            repo_type = "None"
            repo_uri = "None"
        repo_list = npbackup.configuration.get_repo_list(full_config)

        if window:
            if config_file:
                window.set_title(f"{SHORT_PRODUCT_NAME} - {config_file}")
            if not viewer_mode and full_config:
                window["--LAUNCH-BACKUP--"].Update(disabled=False)
                window["--SEE-CONTENT--"].Update(disabled=False)
                window["--OPERATIONS--"].Update(disabled=False)
                window["--FORGET--"].Update(disabled=False)
                window["--CONFIGURE--"].Update(disabled=False)
            if repo_list:
                window["-active_repo-"].Update(values=repo_list, value=repo_list[0])
        return (
            full_config,
            config_file,
            repo_config,
            backup_destination,
            repo_type,
            repo_uri,
            repo_list,
        )

    # FN ENTRY POINT
    parser = ArgumentParser(
        prog=f"{__intname__}",
        description="""Portable Network Backup Client\n
        This program is distributed under the GNU General Public License and comes with ABSOLUTELY NO WARRANTY.\n
        This is free software, and you are welcome to redistribute it under certain conditions; See about button for more.""",
        epilog="You may also run this program with --run-as-cli, in which case, it will behave like npbackup-cli. See '--run-as-cli --help' for specific parameters",
    )

    parser.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        type=str,
        default=None,
        required=False,
        help="Path to alternative configuration file (defaults to current dir/npbackup.conf)",
    )
    parser.add_argument(
        "--repo-name",
        dest="repo_name",
        type=str,
        default=None,
        required=False,
        help="Name of the repository to work with. Defaults to 'default'",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        required=False,
        help="Optional path for logfile",
    )
    parser.add_argument(
        "--external-backend-binary",
        type=str,
        default=None,
        required=False,
        help="Full path to alternative external backend binary",
    )
    parser.add_argument(
        "-V", "--version", action="store_true", help="Show program version"
    )
    args = parser.parse_args()

    if args.version:
        print(version_string)
        sys.exit(0)

    if args.log_file:
        log_file = args.log_file
    else:
        if viewer_mode:
            app_log_name = "npbackup-viewer"
        else:
            app_log_name = __intname__
        if os.name == "nt":
            log_file = os.path.join(CURRENT_DIR, "{}.log".format(app_log_name))
        else:
            log_file = "/var/log/{}.log".format(app_log_name)
    logger = ofunctions.logger_utils.logger_get_logger(log_file, debug=_DEBUG)
    logger.info("GUI: " + version_string)

    if args.config_file:
        config_file = Path(args.config_file).absolute()
    else:
        config_file = Path(f"{CURRENT_DIR}/npbackup.conf").absolute()
        if not config_file.is_file():
            config_file = Path("./npbackup.conf").absolute()
            if not config_file.is_file():
                config_file = None

    backend_binary = None
    if args.external_backend_binary:
        binary = args.external_backend_binary
        if not os.path.isfile(binary):
            msg = f"External backend binary {binary} cannot be found."
            logger.critical(msg)
            sg.PopupError(msg, keep_on_top=True)
            sys.exit(73)

    if viewer_mode:
        __no_lock = True

    # Let's try to read standard restic repository env variables
    viewer_repo_uri = os.environ.get("RESTIC_REPOSITORY", None)
    viewer_repo_password = os.environ.get("RESTIC_PASSWORD", None)
    if viewer_mode and not config_file or (config_file and not config_file.exists()):
        if viewer_repo_uri and viewer_repo_password:
            repo_config = viewer_create_repo(viewer_repo_uri, viewer_repo_password)
        else:
            repo_config = None
        config_file = None
        full_config = None
        repo_type = None
        repo_list = []
    else:
        (
            full_config,
            config_file,
            repo_config,
            _,
            repo_type,
            _,
            repo_list,
        ) = get_config(config_file=config_file, repo_name=args.repo_name)

    right_click_menu = ["", [_t("generic.destination")]]
    # So I did not find any good way to make sure tables have the right size on Linux
    # So here is a hack to make sure the table is larger on linux
    if os.name == "nt":
        headings = [
            "ID    ",
            "Date      ",
            "Hostname     ",
            "User               ",
            "Tags            ",
        ]
    else:
        headings = [
            "ID       ",
            "Date         ",
            "Hostname        ",
            "User                  ",
            "Tags               ",
        ]

    layout = [
        [
            sg.Column(
                [
                    [
                        sg.Column(
                            [[sg.Image(data=OEM_LOGO)]], vertical_alignment="middle"
                        ),
                        sg.Column(
                            [
                                [
                                    sg.Text(
                                        OEM_STRING,
                                        font="Arial 14",
                                        size=(10, None),
                                        justification="center",
                                    )
                                ],
                            ],
                            justification="C",
                            element_justification="C",
                            vertical_alignment="top",
                        ),
                        sg.Column(
                            [
                                [
                                    sg.Text(_t("main_gui.backup_state"), size=(28, 1)),
                                    sg.Button(
                                        _t("generic.refresh"),
                                        key="--STATE-BUTTON--",
                                        button_color=("white", "grey"),
                                    ),
                                ],
                                (
                                    [
                                        sg.Text(
                                            _t("main_gui.backup_list_to"), size=(28, 1)
                                        ),
                                        sg.Combo(
                                            repo_list,
                                            key="-active_repo-",
                                            default_value=(
                                                repo_list[0] if repo_list else None
                                            ),
                                            enable_events=True,
                                            size=(20, 1),
                                        ),
                                    ]
                                    if not viewer_mode
                                    else [
                                        sg.Text(
                                            _t("main_gui.viewer_mode"), size=(28, 1)
                                        )
                                    ]
                                ),
                                [
                                    sg.Text(_t("main_gui.repo_type"), size=(28, 1)),
                                    sg.Text("", key="-repo_type-"),
                                ],
                            ],
                            justification="L",
                            element_justification="L",
                            vertical_alignment="top",
                        ),
                    ],
                    (
                        [
                            sg.Text(
                                _t("main_gui.no_config"),
                                text_color="red",
                                key="-NO-CONFIG-",
                                visible=False,
                                justification="center",
                            )
                        ]
                        if not viewer_mode
                        else []
                    ),
                    [
                        sg.Table(
                            values=[[]],
                            headings=headings,
                            auto_size_columns=True,
                            justification="left",
                            key="snapshot-list",
                            select_mode="extended",
                            size=(None, 10),
                        )
                    ],
                    [
                        sg.Button(
                            _t("main_gui.open_repo"),
                            key="--OPEN-REPO--",
                            visible=viewer_mode,
                        ),
                        sg.Button(
                            _t("main_gui.launch_backup"),
                            key="--LAUNCH-BACKUP--",
                            disabled=viewer_mode
                            or (not viewer_mode and not full_config),
                            visible=not viewer_mode,
                        ),
                        sg.Button(
                            _t("main_gui.see_content"),
                            key="--SEE-CONTENT--",
                            disabled=not viewer_mode and not full_config,
                        ),
                        sg.Button(
                            _t("generic.forget"),
                            key="--FORGET--",
                            disabled=viewer_mode
                            or (not viewer_mode and not full_config),
                            visible=not viewer_mode,
                        ),
                        sg.Button(
                            _t("main_gui.operations"),
                            key="--OPERATIONS--",
                            disabled=viewer_mode
                            or (not viewer_mode and not full_config),
                            visible=not viewer_mode,
                        ),
                        sg.Button(
                            _t("generic.configure"),
                            key="--CONFIGURE--",
                            disabled=viewer_mode
                            or (not viewer_mode and not full_config),
                            visible=not viewer_mode,
                        ),
                        sg.Button(
                            _t("main_gui.load_config"),
                            key="--LOAD-CONF--",
                            disabled=viewer_mode,
                            visible=not viewer_mode,
                        ),
                        sg.Button(_t("generic.about"), key="--ABOUT--"),
                        sg.Button(_t("generic.quit"), key="--EXIT--"),
                    ],
                ],
                element_justification="C",
            )
        ]
    ]

    if not viewer_mode and (version_dict["comp"] or _NPBACKUP_ALLOW_AUTOUPGRADE_DEBUG):
        auto_upgrade_result = check_for_auto_upgrade(config_file, full_config)
    else:
        auto_upgrade_result = None
    window = sg.Window(
        f"{SHORT_PRODUCT_NAME} - {config_file}",
        layout,
        default_element_size=(12, 1),
        text_justification="r",
        auto_size_text=True,
        auto_size_buttons=True,
        no_titlebar=False,
        grab_anywhere=False,
        keep_on_top=False,
        alpha_channel=1.0,
        default_button_element_size=(16, 1),
        right_click_menu=right_click_menu,
        finalize=True,
    )

    # Auto reisze table to window size
    window["snapshot-list"].expand(True, True)

    window.read(timeout=0.01)
    if not config_file and not full_config and not viewer_mode:
        window["-NO-CONFIG-"].Update(visible=True)

    if repo_config:
        try:
            current_state, backup_tz, snapshot_list = get_gui_data(repo_config)
        except (TypeError, ValueError):
            current_state = None
            backup_tz = None
            snapshot_list = []
        gui_update_state(current_state, backup_tz, snapshot_list, repo_type)

    while True:
        event, values = window.read(timeout=60000)

        if event in (sg.WIN_X_EVENT, sg.WIN_CLOSED, "--EXIT--"):
            break
        if event == "-active_repo-":
            active_repo = values["-active_repo-"]
            if full_config.g(f"repos.{active_repo}"):
                (
                    repo_config,
                    _,
                ) = npbackup.configuration.get_repo_config(full_config, active_repo)
                current_state, backup_tz, snapshot_list = get_gui_data(repo_config)
                repo_type, _ = get_anon_repo_uri(repo_config.g("repo_uri"))
                gui_update_state(current_state, backup_tz, snapshot_list, repo_type)
            else:
                sg.PopupError("Repo not existent in config", keep_on_top=True)
                continue
        if event == "--LAUNCH-BACKUP--":
            if not full_config:
                sg.PopupError(_t("main_gui.no_config"), keep_on_top=True)
                continue
            backup(repo_config)
            event = "--STATE-BUTTON--"
        if event == "--SEE-CONTENT--":
            if not repo_config:
                sg.PopupError(_t("main_gui.no_config"), keep_on_top=True)
                continue
            if not values["snapshot-list"]:
                sg.Popup(_t("main_gui.select_backup"), keep_on_top=True)
                continue
            if len(values["snapshot-list"]) > 1:
                sg.Popup(_t("main_gui.select_only_one_snapshot"))
                continue
            snapshot_id = snapshot_list[values["snapshot-list"][0]][0]
            ls_window(
                parent_window=window, repo_config=repo_config, snapshot_id=snapshot_id
            )
            gc.collect()
        if event == "--FORGET--":
            if not full_config:
                sg.PopupError(_t("main_gui.no_config"), keep_on_top=True)
                continue
            if not values["snapshot-list"]:
                sg.Popup(_t("main_gui.select_backup"), keep_on_top=True)
                continue
            snapshots_to_forget = []
            for row in values["snapshot-list"]:
                snapshots_to_forget.append(snapshot_list[row][0])
            forget_snapshot(repo_config, snapshots_to_forget)
            # Make sure we trigger a GUI refresh after forgetting snapshots
            event = "--STATE-BUTTON--"
        if event == "--OPERATIONS--":
            if not full_config:
                sg.PopupError(_t("main_gui.no_config"), keep_on_top=True)
                continue
            with HideWindow(window):
                full_config = operations_gui(full_config)
            event = "--STATE-BUTTON--"
        if event == "--CONFIGURE--":
            if not full_config:
                sg.PopupError(_t("main_gui.no_config"), keep_on_top=True)
                continue
            with HideWindow(window):
                full_config = config_gui(full_config, config_file)
            GUI_STATUS_IGNORE_ERRORS = True
            # Make sure we trigger a GUI refresh when configuration is changed
            # Also make sure we retrigger get_config
            event = "--LOAD-EXISTING-CONF--"
        if event == "--OPEN-REPO--":
            with HideWindow(window):
                viewer_repo_uri, viewer_repo_password = viewer_repo_gui(
                    viewer_repo_uri, viewer_repo_password
                )
            if not viewer_repo_uri or not viewer_repo_password:
                sg.Popup(
                    _t("main_gui.repo_and_password_cannot_be_empty"), keep_on_top=True
                )
                continue
            repo_config = viewer_create_repo(viewer_repo_uri, viewer_repo_password)
            event = "--STATE-BUTTON--"
        if event in ("--LOAD-CONF--", "--LOAD-EXISTING-CONF--"):
            if event == "--LOAD-EXISTING-CONF--":
                cfg_file = config_file
            else:
                cfg_file = None
            (
                _full_config,
                _config_file,
                _repo_config,
                _backup_destination,
                _repo_type,
                _repo_uri,
                _repo_list,
            ) = get_config(window=window, config_file=cfg_file)
            if _full_config:
                full_config = _full_config
                config_file = _config_file
                repo_config = _repo_config
                _ = _backup_destination
                repo_type = _repo_type
                _ = _repo_uri
                repo_list = _repo_list
            else:
                sg.PopupError(
                    _t("main_gui.cannot_load_config_keep_current"), keep_on_top=True
                )
            if not viewer_mode and not config_file and not full_config:
                window["-NO-CONFIG-"].Update(visible=True)
            elif not viewer_mode:
                window["-NO-CONFIG-"].Update(visible=False)
            event = "--STATE-BUTTON--"
        if event == _t("generic.destination"):
            # This is the right click event
            object_name = values["-active_repo-"]
            manager_password = npbackup.configuration.get_manager_password(
                full_config, object_name
            )
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
                destination_string = get_anon_repo_uri(repo_config.g("repo_uri"))
                sg.PopupNoFrame(destination_string)
            continue
        if event == "--ABOUT--":
            with HideWindow(window):
                about_gui(
                    version_string,
                    config_file,
                    full_config if not viewer_mode else None,
                    auto_upgrade_result,
                )
        if event == "--STATE-BUTTON--":
            if full_config or (
                viewer_mode and viewer_repo_uri and viewer_repo_password
            ):
                current_state, backup_tz, snapshot_list = get_gui_data(repo_config)
                gui_update_state(current_state, backup_tz, snapshot_list, repo_type)
                if current_state is None:
                    sg.Popup(_t("main_gui.cannot_get_repo_status"))


def main_gui(viewer_mode=False):
    atexit.register(
        npbackup.common.execution_logs,
        datetime.now(timezone.utc),
    )
    # kill_childs normally would not be necessary, but let's just be foolproof here (kills restic subprocess in all cases)
    # We need to only kill the backend process on windows since we compile with Nuitka option --windows-disable-console=hide
    if os.name == "nt":
        backend_process = "restic.exe"
    else:
        backend_process = "restic"
    atexit.register(
        kill_childs, os.getpid(), grace_period=30, process_name=backend_process
    )
    try:
        # Hide CMD window when Nuitka hide action does not work
        if _DEBUG and version_dict["comp"]:
            handle_current_window(action="minimize")
        elif version_dict["comp"]:
            handle_current_window(action="hide")
        _main_gui(viewer_mode=viewer_mode)
        sys.exit(logger.get_worst_logger_level(all_time=True))
    except _tkinter.TclError as exc:
        logger.critical(f'Tkinter error: "{exc}". Is this a headless server ?')
        sys.exit(250)
    except KeyboardInterrupt as exc:
        logger.error(f"Program interrupted by keyboard: {exc}")
        logger.debug("Trace:", exc_info=True)
        # EXIT_CODE 200 = keyboard interrupt
        sys.exit(200)
    except Exception as exc:
        sg.Popup(_t("config_gui.unknown_error_see_logs") + f": {exc}", keep_on_top=True)
        logger.critical(f"GUI Execution error {exc}")
        logger.info("Trace:", exc_info=True)
        sys.exit(251)
