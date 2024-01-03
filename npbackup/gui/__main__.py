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
from ofunctions.process import kill_childs
from ofunctions.threading import threaded
from ofunctions.misc import BytesConverter
import PySimpleGUI as sg
import _tkinter
import npbackup.configuration
import npbackup.common
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
    PYSIMPLEGUI_THEME,
    OEM_ICON,
    SHORT_PRODUCT_NAME,
)
from npbackup.gui.config import config_gui
from npbackup.gui.operations import operations_gui
from npbackup.gui.helpers import get_anon_repo_uri, gui_thread_runner
from npbackup.core.i18n_helper import _t
from npbackup.core.upgrade_runner import run_upgrade, check_new_version
from npbackup.path_helper import CURRENT_DIR
from npbackup.__version__ import version_string
from npbackup.__debug__ import _DEBUG
from npbackup.restic_wrapper import ResticRunner


LOG_FILE = os.path.join(CURRENT_DIR, "{}.log".format(__intname__))
logger = ofunctions.logger_utils.logger_get_logger(LOG_FILE, debug=_DEBUG)

sg.theme(PYSIMPLEGUI_THEME)
sg.SetOptions(icon=OEM_ICON)


def about_gui(version_string: str, full_config: dict = None) -> None:
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
    repo_config.s("repo_opts.minimum_backup_age", 1440)
    # NPF-SEC-00005 Add restore permission
    repo_config.s("permissions", "restore")

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
    result = gui_thread_runner(
        repo_config, "ls", snapshot=snapshot_id, __autoclose=True, __compact=True
    )
    if not result["result"]:
        return None, None

    snapshot_content = result["output"]
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
            background_color=BG_COLOR_LDR,
            text_color=TXT_COLOR_LDR,
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
        result = gui_thread_runner(
            repo_config,
            "restore",
            snapshot=snapshot,
            target=target,
            restore_includes=restore_includes,
        )
        return result["result"]

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
            result = _restore_window(
                repo_config,
                snapshot=snapshot_id,
                target=values["-RESTORE-FOLDER-"],
                restore_includes=restore_include,
            )
            break
    window.close()
    return result


def backup(repo_config: dict) -> bool:
    gui_msg = _t("main_gui.backup_activity")
    # on_success = _t("main_gui.backup_done")
    # on_failure = _t("main_gui.backup_failed")
    result = gui_thread_runner(
        repo_config,
        "backup",
        force=True,
        __autoclose=False,
        __compact=False,
        __gui_msg=gui_msg,
    )
    return result["result"]


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
    )
    return result["result"]


def _main_gui(viewer_mode: bool):
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
                sg.Button(_t("generic.accept"), key="--ACCEPT--"),
            ],
        ]
        window = sg.Window("Configuration File", layout=layout)
        config_file = None
        while True:
            action = None
            event, values = window.read()
            if event in [sg.WIN_X_EVENT, sg.WIN_CLOSED, "--CANCEL--"]:
                action = "--CANCEL--"
                break
            if event == "--NEW-CONFIG--":
                action = event
                break
            if event == "--ACCEPT--":
                config_file = Path(values["-config_file-"])
                if not values["-config_file-"] or not config_file.exists():
                    sg.PopupError(_t("generic.file_does_not_exist"))
                    continue
                full_config = npbackup.configuration.load_config(config_file)
                if not full_config:
                    sg.PopupError(_t("generic.bad_file"))
                    continue
                break
        window.close()
        return config_file, action

    def gui_update_state() -> None:
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
                "{}: {}".format(
                    _t("generic.too_old"), backup_tz.replace(microsecond=0)
                ),
                button_color=GUI_STATE_OLD_BUTTON,
            )
        elif current_state is None:
            window["--STATE-BUTTON--"].Update(
                _t("generic.not_connected_yet"), button_color=GUI_STATE_UNKNOWN_BUTTON
            )

        window["snapshot-list"].Update(snapshot_list)

    def get_gui_data(repo_config: dict) -> Tuple[bool, List[str]]:
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
        )
        if not result["result"]:
            snapshots = None
        else:
            snapshots = result["output"]
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
                if re.match(
                    r"[0-9]{4}-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]\..*\+[0-2][0-9]:[0-9]{2}",
                    snapshot["time"],
                ):
                    snapshot_date = dateutil.parser.parse(snapshot["time"]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                else:
                    snapshot_date = "Unparseable"
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

    def get_config_file(default: bool = True) -> str:
        """
        Load config file until we got something
        """
        if default:
            config_file = Path(f"{CURRENT_DIR}/npbackup.conf")
            if default:
                full_config = npbackup.configuration.load_config(config_file)
                if not config_file.exists():
                    config_file = None
                if not full_config:
                    return full_config, config_file
        else:
            config_file = None

        while True:
            if not config_file or not config_file.exists():
                config_file, action = select_config_file()
                if action == "--CANCEL--":
                    break
                if action == "--NEW-CONFIG--":
                    config_file = "npbackup.conf"
                    full_config = config_gui(
                        npbackup.configuration.get_default_config(), config_file
                    )
            if config_file:
                logger.info(f"Using configuration file {config_file}")
                full_config = npbackup.configuration.load_config(config_file)
                if not full_config:
                    sg.PopupError(f"{_t('main_gui.config_error')} {config_file}")
                    config_file = None
                else:
                    return full_config, config_file
        return None, None

    def get_config(default: bool = False):
        full_config, config_file = get_config_file(default=default)
        if full_config and config_file:
            repo_config, config_inheritance = npbackup.configuration.get_repo_config(
                full_config
            )
            backup_destination = _t("main_gui.local_folder")
            backend_type, repo_uri = get_anon_repo_uri(repo_config.g("repo_uri"))
        else:
            repo_config = None
            config_inheritance = None
            backup_destination = "None"
            backend_type = "None"
            repo_uri = "None"
        repo_list = npbackup.configuration.get_repo_list(full_config)
        return (
            full_config,
            config_file,
            repo_config,
            backup_destination,
            backend_type,
            repo_uri,
            repo_list,
        )

    if not viewer_mode:
        (
            full_config,
            config_file,
            repo_config,
            backup_destination,
            backend_type,
            repo_uri,
            repo_list,
        ) = get_config(default=True)
    else:
        # Let's try to read standard restic repository env variables
        viewer_repo_uri = os.environ.get("RESTIC_REPOSITORY", None)
        viewer_repo_password = os.environ.get("RESTIC_PASSWORD", None)
        if viewer_repo_uri and viewer_repo_password:
            repo_config = viewer_create_repo(viewer_repo_uri, viewer_repo_password)
        else:
            repo_config = None
        config_file = None
        full_config = None

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
                                [sg.Text(_t("main_gui.viewer_mode"))]
                                if viewer_mode
                                else [],
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
                        sg.Text(_t("main_gui.no_config"), font=("Arial", 14), text_color="red", key="-NO-CONFIG-", visible=False)
                    ] if not viewer_mode
                    else [],
                    [
                        sg.Text(_t("main_gui.backup_list_to")),
                        sg.Combo(
                            repo_list,
                            key="-active_repo-",
                            default_value=repo_list[0] if repo_list else None,
                            enable_events=True,
                        ),
                        sg.Text(f"Type {backend_type}", key="-backend_type-"),
                    ]
                    if not viewer_mode
                    else [],
                    [
                        sg.Table(
                            values=[[]],
                            headings=headings,
                            auto_size_columns=True,
                            justification="left",
                            key="snapshot-list",
                            select_mode="extended",
                            size=(None, 10)
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
                            disabled=viewer_mode,
                        ),
                        sg.Button(_t("main_gui.see_content"), key="--SEE-CONTENT--"),
                        sg.Button(
                            _t("generic.forget"), key="--FORGET--", disabled=viewer_mode
                        ),  # TODO , visible=False if repo_config.g("permissions") != "full" else True),
                        sg.Button(
                            _t("main_gui.operations"),
                            key="--OPERATIONS--",
                            disabled=viewer_mode,
                        ),
                        sg.Button(
                            _t("generic.configure"),
                            key="--CONFIGURE--",
                            disabled=viewer_mode,
                        ),
                        sg.Button(
                            _t("main_gui.load_config"),
                            key="--LOAD-CONF--",
                            disabled=viewer_mode,
                        ),
                        sg.Button(_t("generic.about"), key="--ABOUT--"),
                        sg.Button(_t("generic.quit"), key="--EXIT--"),
                    ],
                ],
                element_justification="C",
            )
        ]
    ]

    window = sg.Window(
        SHORT_PRODUCT_NAME,
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
    window.set_title(f"{SHORT_PRODUCT_NAME} - {config_file}")

    window.read(timeout=0.01)
    if not config_file and not full_config and not viewer_mode:
        window["-NO-CONFIG-"].Update(visible=True)
    if repo_config:
        try:
            current_state, backup_tz, snapshot_list = get_gui_data(repo_config)
        except ValueError:
            current_state = None
            backup_tz = None
            snapshot_list = []
        gui_update_state()
    # Show which config file is loaded
    window.set_title(f"{SHORT_PRODUCT_NAME} - {config_file}")
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
            if not full_config:
                sg.PopupError(_t("main_gui.no_config"))
                continue
            backup(repo_config)
            event = "--STATE-BUTTON--"
        if event == "--SEE-CONTENT--":
            if not full_config:
                sg.PopupError(_t("main_gui.no_config"))
                continue
            if not values["snapshot-list"]:
                sg.Popup(_t("main_gui.select_backup"), keep_on_top=True)
                continue
            if len(values["snapshot-list"]) > 1:
                sg.Popup(_t("main_gui.select_only_one_snapshot"))
                continue
            snapshot_to_see = snapshot_list[values["snapshot-list"][0]][0]
            ls_window(repo_config, snapshot_to_see)
        if event == "--FORGET--":
            if not full_config:
                sg.PopupError(_t("main_gui.no_config"))
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
                sg.PopupError(_t("main_gui.no_config"))
                continue
            full_config = operations_gui(full_config)
            event = "--STATE-BUTTON--"
        if event == "--CONFIGURE--":
            if not full_config:
                sg.PopupError(_t("main_gui.no_config"))
                continue
            full_config = config_gui(full_config, config_file)
            # Make sure we trigger a GUI refresh when configuration is changed
            event = "--STATE-BUTTON--"
        if event == "--OPEN-REPO--":
            viewer_repo_uri, viewer_repo_password = viewer_repo_gui()
            repo_config = viewer_create_repo(viewer_repo_uri, viewer_repo_password)
            event = "--STATE-BUTTON--"
        if event == "--LOAD-CONF--":
            (
                full_config,
                config_file,
                repo_config,
                backup_destination,
                backend_type,
                repo_uri,
                repo_list,
            ) = get_config()
            window.set_title(f"{SHORT_PRODUCT_NAME} - {config_file}")
            if not viewer_mode and not config_file and not full_config:
                window["-NO-CONFIG-"].Update(visible=True)
            elif not viewer_mode:
                window["-NO-CONFIG-"].Update(visible=False)
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
            if full_config or viewer_mode:
                current_state, backup_tz, snapshot_list = get_gui_data(repo_config)
                gui_update_state()
                if current_state is None:
                    sg.Popup(_t("main_gui.cannot_get_repo_status"))


def main_gui(viewer_mode=False):
    atexit.register(
        npbackup.common.execution_logs,
        datetime.utcnow(),
    )
    # kill_childs normally would not be necessary, but let's just be foolproof here (kills restic subprocess in all cases)
    atexit.register(kill_childs, os.getpid(), grace_period=30)
    try:
        _main_gui(viewer_mode=viewer_mode)
        sys.exit(logger.get_worst_logger_level())
    except _tkinter.TclError as exc:
        logger.critical(f'Tkinter error: "{exc}". Is this a headless server ?')
        sys.exit(250)
    except Exception as exc:
        sg.Popup(_t("config_gui.unknown_error_see_logs") + f": {exc}")
        logger.critical(f"GUI Execution error {exc}")
        logger.info("Trace:", exc_info=True)
        sys.exit(251)
