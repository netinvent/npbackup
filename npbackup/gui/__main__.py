#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.main"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023121701"


from typing import List, Optional, Tuple
import sys
import os
import re
from pathlib import Path
import ofunctions.logger_utils
from datetime import datetime
import dateutil
from time import sleep
from ruamel.yaml.comments import CommentedMap
import atexit
from ofunctions.threading import threaded
from ofunctions.misc import BytesConverter
import PySimpleGUI as sg
import _tkinter
import npbackup.configuration
import npbackup.common
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
    PYSIMPLEGUI_THEME,
    OEM_ICON
)
from npbackup.gui.config import config_gui
from npbackup.gui.operations import operations_gui
from npbackup.gui.helpers import get_anon_repo_uri, gui_thread_runner
from npbackup.core.i18n_helper import _t
from npbackup.core.upgrade_runner import run_upgrade, check_new_version
from npbackup.path_helper import CURRENT_DIR
from npbackup.__version__ import version_string
from npbackup.__debug__ import _DEBUG
from npbackup.gui.config import config_gui
from npbackup.gui.operations import operations_gui
from npbackup.restic_wrapper import ResticRunner


LOG_FILE = os.path.join(CURRENT_DIR, "{}.log".format(__intname__))
logger = ofunctions.logger_utils.logger_get_logger(LOG_FILE, debug=_DEBUG)

sg.theme(PYSIMPLEGUI_THEME)
sg.SetOptions(icon=OEM_ICON)


def about_gui(version_string: str, full_config: dict = None) -> None:
    license_content = LICENSE_TEXT

    if full_config and full_config.g("global_options.auto_upgrade_server_url"):
        auto_upgrade_result = check_new_version(full_config)
    else:
        auto_upgrade_result = None
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
    elif auto_upgrade_result is None:
        new_version = [sg.Text(_t("config_gui.auto_upgrade_disabled"))]
    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as file_handle:
            license_content = file_handle.read()
    except OSError:
        logger.info("Could not read license file.")

    layout = [
        [sg.Text(version_string)],
        new_version,
        [sg.Text("License: GNU GPLv3")],
        [sg.Multiline(license_content, size=(65, 20), disabled=True)],
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
                sub_result = run_upgrade(full_config)
                if sub_result:
                    sys.exit(0)
                else:
                    sg.Popup(_t("config_gui.auto_upgrade_failed"), keep_on_top=True)
    window.close()


def viewer_repo_gui(viewer_repo_uri: str = None, viewer_repo_password: str = None) -> Tuple[str, str]:
    """
    Ask for repo and password if not defined in env variables
    """
    layout = [
        [sg.Text(_t("config_gui.backup_repo_uri"), size=(35, 1)), sg.Input(viewer_repo_uri, key="-REPO-URI-")],
        [sg.Text(_t("config_gui.backup_repo_password"), size=(35, 1)), sg.Input(viewer_repo_password, key="-REPO-PASSWORD-", password_char='*')],
        [sg.Push(), sg.Button(_t("generic.cancel"), key="--CANCEL--"), sg.Button(_t("generic.accept"), key="--ACCEPT--")]
    ]
    window = sg.Window("Viewer", layout, keep_on_top=True, grab_anywhere=True)
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, '--CANCEL--'):
            break
        if event == '--ACCEPT--':
            if values['-REPO-URI-'] and values['-REPO-PASSWORD-']:
                break
            sg.Popup(_t("main_gui.repo_and_password_cannot_be_empty"))
    window.close()
    return values['-REPO-URI-'], values['-REPO-PASSWORD-']

def get_gui_data(repo_config: dict) -> Tuple[bool, List[str]]:
    gui_msg = _t("main_gui.loading_snapshot_list_from_repo")
    snapshots = gui_thread_runner(repo_config, "list", __gui_msg=gui_msg, __autoclose=True, __compact=True)
    current_state, backup_tz = ResticRunner._has_snapshot_timedelta(snapshots, repo_config.g("repo_opts.minimum_backup_age"))
    snapshot_list = []
    if snapshots:
        snapshots.reverse()  # Let's show newer snapshots first
        for snapshot in snapshots:
            if re.match(
                    r"[0-9]{4}-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]\..*\+[0-2][0-9]:[0-9]{2}",
                    snapshot["time"],
                ):
                snapshot_date = dateutil.parser.parse(snapshot["time"]).strftime("%Y-%m-%d %H:%M:%S")
            else:
                snapshot_date = "Unparsable"
            snapshot_username = snapshot["username"]
            snapshot_hostname = snapshot["hostname"]
            snapshot_id = snapshot["short_id"]
            try:
                snapshot_tags = " [TAGS: {}]".format(snapshot["tags"])
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
    count = 0
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
        # dateutil.parser.parse is *really* cpu hungry, let's replace it with a dumb alternative
        # mtime = dateutil.parser.parse(entry["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
        mtime = str(entry["mtime"])[0:19]
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
        # Since the thread is heavily CPU bound, let's add a minimal
        # arbitrary sleep time to let GUI update
        # In a 130k entry scenario, this added less than a second on a 25 second run
        count += 1
        if not count % 1000:
            sleep(0.0001)
    return treedata


def ls_window(repo_config: dict, snapshot_id: str) -> bool:
    snapshot_content = gui_thread_runner(repo_config, 'ls', snapshot=snapshot_id, __autoclose=True, __compact=True)
    if not snapshot_content:
        return snapshot_content, None

    try:
        # Since ls returns an iter now, we need to use next
        snapshot = next(snapshot_content)
    # Exception that happens when restic cannot successfully get snapshot content
    except StopIteration:
        return None, None
    try:
        snap_date = dateutil.parser.parse(snapshot["time"])
    except (KeyError, IndexError):
        snap_date = "[inconnu]"
    try:
        short_id = snapshot["short_id"]
    except (KeyError, IndexError):
        short_id = "[inconnu]"
    try:
        username = snapshot["username"]
    except (KeyError, IndexError):
        username = "[inconnu]"
    try:
        hostname = snapshot["hostname"]
    except (KeyError, IndexError):
        hostname = "[inconnu]"

    backup_id = f"{_t('main_gui.backup_content_from')} {snap_date} {_t('main_gui.run_as')} {username}@{hostname} {_t('main_gui.identified_by')} {short_id}"

    if not backup_id or not snapshot_content:
        sg.PopupError(_t("main_gui.cannot_get_content"), keep_on_top=True)
        return False

    # The following thread is cpu intensive, so the GUI will update sluggerish
    # In the thread, we added a sleep argument every 1000 iters so we get to update
    # the GUI. Earlier fix was to preload animation

    # We get a thread result, hence pylint will complain the thread isn't a tuple
    # pylint: disable=E1101 (no-member)
    thread = _make_treedata_from_json(snapshot_content)
    while not thread.done() and not thread.cancelled():
        sg.PopupAnimated(
            LOADER_ANIMATION,
            message="{}...".format(_t("main_gui.creating_tree")),
            time_between_frames=50,
            background_color=GUI_LOADER_COLOR,
            text_color=GUI_LOADER_TEXT_COLOR,
        )
    sg.PopupAnimated(None)
    treedata = thread.result()

    left_col = [
        [sg.Text(backup_id)],
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
        _t("generic.content"), layout=layout, grab_anywhere=True, keep_on_top=False
    )
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "quit"):
            break
        if event == "restore_to":
            if not values["-TREE-"]:
                sg.PopupError(_t("main_gui.select_folder"))
                continue
            restore_window(repo_config, snapshot_id, values["-TREE-"])

    # Closing a big sg.TreeData is really slow
    # This is a little trichery lesson
    # Still we should open a case at PySimpleGUI to know why closing a sg.TreeData window is painfully slow # TODO
    window.hide()

    @threaded
    def _close_win():
        """
        Since closing a sg.Treedata takes alot of time, let's thread it into background
        """
        window.close
    _close_win()
    return True


def restore_window(
    repo_config: dict, snapshot_id: str, restore_include: List[str]
) -> None: 
    def _restore_window(
    repo_config: dict, snapshot: str, target: str, restore_includes: Optional[List]
    ) -> bool:
        result = gui_thread_runner(repo_config, "restore", snapshot=snapshot, target=target, restore_includes=restore_includes)
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
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "cancel"):
            break
        if event == "restore":
            # on_success = _t("main_gui.restore_done")
            # on_failure = _t("main_gui.restore_failed")
            result = _restore_window(repo_config, snapshot=snapshot_id, target=values["-RESTORE-FOLDER-"], restore_includes=restore_include)
            break
    window.close()
    return result


def backup(repo_config: dict) -> bool:
    gui_msg = _t("main_gui.backup_activity")
    # on_success = _t("main_gui.backup_done")
    # on_failure = _t("main_gui.backup_failed")
    result = gui_thread_runner(repo_config, 'backup', force=True, __autoclose=False, __compact=False, __gui_msg=gui_msg)
    return result


def forget_snapshot(repo_config: dict, snapshot_ids: List[str]) -> bool:
    gui_msg = f"{_t('generic.forgetting')} {snapshot_ids} {_t('main_gui.this_will_take_a_while')}"
    # on_success = f"{snapshot_ids} {_t('generic.forgotten')} {_t('generic.successfully')}"
    # on_failure = _t("main_gui.forget_failed")
    result = gui_thread_runner(repo_config, "forget", snapshots=snapshot_ids, __gui_msg=gui_msg, __autoclose=True)
    return result


def _main_gui(viewer_mode: bool):

    def select_config_file():
        """
        Option to select a configuration file
        """
        layout = [
            [
                sg.Text(_t("main_gui.select_config_file")),
                sg.Input(key="-config_file-"),
                sg.FileBrowse(_t("generic.select_file")),
            ],
            [
                sg.Button(_t("generic.cancel"), key="-CANCEL-"),
                sg.Button(_t("generic.accept"), key="-ACCEPT-"),
            ],
        ]
        window = sg.Window("Configuration File", layout=layout)
        while True:
            event, values = window.read()
            if event in [sg.WIN_X_EVENT, sg.WIN_CLOSED, "-CANCEL-"]:
                break
            if event == "-ACCEPT-":
                config_file = Path(values["-config_file-"])
                if not config_file.exists():
                    sg.PopupError(_t("generic.file_does_not_exist"))
                    continue
                config = npbackup.configuration._load_config_file(config_file)
                if not config:
                    sg.PopupError(_t("generic.bad_file"))
                    continue
                return config_file

    def gui_update_state() -> None:
        if current_state:
            window["--STATE-BUTTON--"].Update(
                "{}: {}".format(_t("generic.up_to_date"), backup_tz.replace(microsecond=0)),
                button_color=GUI_STATE_OK_BUTTON,
            )
        elif current_state is False and backup_tz == datetime(1, 1, 1, 0, 0):
            window["--STATE-BUTTON--"].Update(
                _t("generic.no_snapshots"), button_color=GUI_STATE_OLD_BUTTON
            )
        elif current_state is False:
            window["--STATE-BUTTON--"].Update(
                "{}: {}".format(_t("generic.too_old"), backup_tz.replace(microsecond=0)),
                button_color=GUI_STATE_OLD_BUTTON,
            )
        elif current_state is None:
            window["--STATE-BUTTON--"].Update(
                _t("generic.not_connected_yet"), button_color=GUI_STATE_UNKNOWN_BUTTON
            )

        window["snapshot-list"].Update(snapshot_list)


    if not viewer_mode:
        config_file = Path(f"{CURRENT_DIR}/npbackup.conf")
        if not config_file.exists():
            while True:
                config_file = select_config_file()
                if config_file:
                    config_file = select_config_file()
                else:
                    break

        logger.info(f"Using configuration file {config_file}")
        full_config = npbackup.configuration.load_config(config_file)
        repo_config, config_inheritance = npbackup.configuration.get_repo_config(
            full_config
        )
        repo_list = npbackup.configuration.get_repo_list(full_config)

        backup_destination = _t("main_gui.local_folder")
        backend_type, repo_uri = get_anon_repo_uri(repo_config.g("repo_uri"))
    else:
        # Init empty REPO
        repo_config = CommentedMap()
        repo_config.s("name", "external")
        viewer_repo_uri = os.environ.get("RESTIC_REPOSITORY", None)
        viewer_repo_password = os.environ.get("RESTIC_PASSWORD", None)
        if not viewer_repo_uri or not viewer_repo_password:
            viewer_repo_uri, viewer_repo_password = viewer_repo_gui(viewer_repo_uri, viewer_repo_password)
        repo_config.s("repo_uri", viewer_repo_uri)
        repo_config.s("repo_opts", CommentedMap())
        repo_config.s("repo_opts.repo_password", viewer_repo_password)
        # Let's set default backup age to 24h
        repo_config.s("repo_opts.minimum_backup_age", 1440)

    right_click_menu = ["", [_t("generic.destination")]]
    headings = [
        "ID     ",
        "Date               ",
        "Hostname  ",
        "User              ",
        "Tags        ",
    ]

    layout = [
        [
            sg.Column(
                [
                    [
                        sg.Column(
                            [[sg.Image(data=OEM_LOGO)]], vertical_alignment="top"
                        ),
                        sg.Column(
                            [
                                [sg.Text(OEM_STRING, font="Arial 14")],
                                [sg.Text(_t("main_gui.viewer_mode"))] if viewer_mode else [],
                                [sg.Text("{}: ".format(_t("main_gui.backup_state")))],
                                [
                                    sg.Button(
                                        _t("generic.unknown"),
                                        key="--STATE-BUTTON--",
                                        button_color=("white", "grey"),
                                    )
                                ],
                            ],
                            justification="C",
                            element_justification="C",
                            vertical_alignment="top",
                        ),
                    ],
                    [
                        sg.Text(_t("main_gui.backup_list_to")),
                        sg.Combo(
                            repo_list,
                            key="-active_repo-",
                            default_value=repo_list[0],
                            enable_events=True,
                        ),
                        sg.Text(f"Type {backend_type}", key="-backend_type-"),
                    ] if not viewer_mode else [],
                    [
                        sg.Table(
                            values=[[]],
                            headings=headings,
                            auto_size_columns=True,
                            justification="left",
                            key="snapshot-list",
                            select_mode="extended",
                        )
                    ],
                    [
                        sg.Button(
                            _t("main_gui.launch_backup"), key="--LAUNCH-BACKUP--", disabled=viewer_mode
                        ),
                        sg.Button(_t("main_gui.see_content"), key="--SEE-CONTENT--"),
                        sg.Button(_t("generic.forget"), key="--FORGET--", disabled=viewer_mode), # TODO , visible=False if repo_config.g("permissions") != "full" else True),
                        sg.Button(_t("main_gui.operations"), key="--OPERATIONS--", disabled=viewer_mode),
                        sg.Button(_t("generic.configure"), key="--CONFIGURE--", disabled=viewer_mode),
                        sg.Button(_t("generic.about"), key="--ABOUT--"),
                        sg.Button(_t("generic.quit"), key="--EXIT--"),
                    ],
                ],
                element_justification="C",
            )
        ]
    ]

    window = sg.Window(
        "npbackup",
        layout,
        default_element_size=(12, 1),
        text_justification="r",
        auto_size_text=True,
        auto_size_buttons=True,
        no_titlebar=False,
        grab_anywhere=False,
        keep_on_top=False,
        alpha_channel=0.9,
        default_button_element_size=(16, 1),
        right_click_menu=right_click_menu,
        finalize=True,
    )

    # Auto reisze table to window size
    window["snapshot-list"].expand(True, True)

    window.read(timeout=1)
    try:
        current_state, backup_tz, snapshot_list = get_gui_data(repo_config)
    except ValueError:
        current_state = None
        backup_tz = None
        snapshot_list = []
    gui_update_state()
    while True:
        event, values = window.read(timeout=60000)

        if event in (sg.WIN_X_EVENT, sg.WIN_CLOSED, "--EXIT--"):
            break
        if event == "-active_repo-":
            active_repo = values["-active_repo-"]
            if full_config.g(f"repos.{active_repo}"):
                (
                    repo_config,
                    config_inheriteance,
                ) = npbackup.configuration.get_repo_config(full_config, active_repo)
                current_state, backup_tz, snapshot_list = get_gui_data(repo_config)
                gui_update_state()
            else:
                sg.PopupError("Repo not existent in config")
                continue
        if event == "--LAUNCH-BACKUP--":
            backup(repo_config)
            event = "--STATE-BUTTON--"
        if event == "--SEE-CONTENT--":
            if not values["snapshot-list"]:
                sg.Popup(_t("main_gui.select_backup"), keep_on_top=True)
                continue
            if len(values["snapshot-list"]) > 1:
                sg.Popup(_t("main_gui.select_only_one_snapshot"))
                continue
            snapshot_to_see = snapshot_list[values["snapshot-list"][0]][0]
            ls_window(repo_config, snapshot_to_see)
        if event == "--FORGET--":
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
            full_config = operations_gui(full_config)
            event = "--STATE-BUTTON--"
        if event == "--CONFIGURE--":
            full_config = config_gui(full_config, config_file)
            # Make sure we trigger a GUI refresh when configuration is changed
            event = "--STATE-BUTTON--"
        if event == _t("generic.destination"):
            try:
                if backend_type:
                    if backend_type in ["REST", "SFTP"]:
                        destination_string = repo_config.g("repo_uri").split("@")[-1]
                    else:
                        destination_string = repo_config.g("repo_uri")
                sg.PopupNoFrame(destination_string)
            except (TypeError, KeyError):
                sg.PopupNoFrame(_t("main_gui.unknown_repo"))
        if event == "--ABOUT--":
            about_gui(version_string, full_config if not viewer_mode else None)
        if event == "--STATE-BUTTON--":
            current_state, backup_tz, snapshot_list = get_gui_data(repo_config)
            gui_update_state()
            if current_state is None:
                sg.Popup(_t("main_gui.cannot_get_repo_status"))


def main_gui(viewer_mode=False):
    atexit.register(
        npbackup.common.execution_logs,
        datetime.utcnow(),
    )
    try:
        _main_gui(viewer_mode=viewer_mode)
        sys.exit(logger.get_worst_logger_level())
    except _tkinter.TclError as exc:
        logger.critical(f'Tkinter error: "{exc}". Is this a headless server ?')
        sys.exit(250)
    except Exception as exc:
        sg.Popup(_t("config_gui.unknown_error_see_logs") + f": {exc}")
        logger.critical("GUI Execution error", exc)
        if _DEBUG:
            logger.critical("Trace:", exc_info=True)
        sys.exit(251)
