#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.helpers"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024091501"


from typing import Tuple
from logging import getLogger
from time import sleep
import re
import queue
import time
import FreeSimpleGUI as sg
from npbackup.core.i18n_helper import _t
from resources.customization import (
    LOADER_ANIMATION,
    BG_COLOR_LDR,
    TXT_COLOR_LDR,
)
from npbackup.core.runner import NPBackupRunner
from npbackup.__debug__ import _DEBUG
from npbackup.__env__ import GUI_CHECK_INTERVAL
from resources.customization import SIMPLEGUI_THEME, OEM_ICON

logger = getLogger()


sg.theme(SIMPLEGUI_THEME)
sg.SetOptions(icon=OEM_ICON)


# For debugging purposes, we should be able to disable threading to see actual errors
# out of thread
if not _DEBUG:
    USE_THREADING = True
else:
    USE_THREADING = False
    logger.info("Running without threads as per debug requirements")


def get_anon_repo_uri(repository: str) -> Tuple[str, str]:
    """
    Remove user / password part from repository uri
    """
    if not repository:
        return "UNDEFINED", None
    backend_type = repository.split(":")[0].upper()
    if backend_type.upper() in ["REST", "SFTP"]:
        res = re.match(
            r"(sftp|rest)(.*:\/\/)(.*):?(.*)@(.*)", repository, re.IGNORECASE
        )
        if res:
            backend_uri = res.group(1) + res.group(2) + res.group(5)
        else:
            backend_uri = repository
    elif backend_type.upper() in [
        "S3",
        "B2",
        "SWIFT",
        "AZURE",
        "GS",
        "RCLONE",
    ]:
        backend_uri = repository
    else:
        backend_type = "LOCAL"
        backend_uri = repository
    return backend_type, backend_uri


def gui_thread_runner(
    __repo_config: dict,
    __fn_name: str,
    __compact: bool = True,
    __autoclose: bool = False,
    __gui_msg: str = "",
    __stdout: bool = True,
    __backend_binary: str = None,
    __ignore_errors: bool = False,
    *args,
    **kwargs,
):
    """
    Runs any NPBackupRunner functions in threads for GUI
    also gets stdout and stderr queues output into gui window
    Has a grace period after thread end to get queue output, so we can see whenever a thread dies of mysterious causes
    """

    def _upgrade_from_compact_view():
        for key in (
            "-OPERATIONS-PROGRESS-STDOUT-TITLE-",
            "-OPERATIONS-PROGRESS-STDOUT-",
            "-OPERATIONS-PROGRESS-STDERR-TITLE-",
            "-OPERATIONS-PROGRESS-STDERR-",
        ):
            progress_window[key].Update(visible=True)
        progress_window["--EXPAND--"].Update(visible=False)
        progress_window["-OPERATIONS-PROGRESS-STDOUT-"].update(autoscroll=True)

    def _update_gui_from_cache(_stdout_cache: str = None, _stderr_cache: str = None):
        if _stdout_cache:
            progress_window["-OPERATIONS-PROGRESS-STDOUT-"].Update(
                _stdout_cache[-1000:]
            )
        if _stderr_cache:
            progress_window["-OPERATIONS-PROGRESS-STDERR-"].Update(
                f"\n{_stderr_cache}", append=True
            )

    runner = NPBackupRunner()

    if __backend_binary:
        runner.binary = __backend_binary

    if __stdout:
        stdout_queue = queue.Queue()
        runner.stdout = stdout_queue

    stderr_queue = queue.Queue()
    runner.stderr = stderr_queue

    # We'll always use json output in GUI mode
    runner.json_output = True
    # in GUI mode, we'll use struct output instead of json whenever it's possible
    # as of v3, this only is needed for ls operations
    runner.struct_output = True

    # So we don't always init repo_config, since runner.group_runner would do that itself
    if __repo_config:
        runner.repo_config = __repo_config

    fn = getattr(runner, __fn_name)
    logger.debug(
        f"gui_thread_runner runs {fn.__name__} {'with' if USE_THREADING else 'without'} threads"
    )

    stderr_has_messages = False
    if not __gui_msg:
        __gui_msg = "Operation"

    progress_layout = [
        # Replaced by custom title bar
        # [sg.Text(__gui_msg, text_color=GUI_LOADER_TEXT_COLOR, background_color=GUI_LOADER_COLOR, visible=__compact, justification='C')],
        [
            sg.Text(
                _t("main_gui.last_messages"),
                key="-OPERATIONS-PROGRESS-STDOUT-TITLE-",
                text_color=TXT_COLOR_LDR,
                background_color=BG_COLOR_LDR,
                visible=not __compact,
            )
        ],
        [
            sg.Multiline(
                key="-OPERATIONS-PROGRESS-STDOUT-",
                size=(70, 15),
                visible=not __compact,
                # Setting autoscroll=True on not visible Multiline takes
                # huge time depending on the amount of text (up to minutes for 80k chars)
                autoscroll=False,
            )
        ],
        [
            sg.Text(
                _t("main_gui.error_messages"),
                key="-OPERATIONS-PROGRESS-STDERR-TITLE-",
                text_color=TXT_COLOR_LDR,
                background_color=BG_COLOR_LDR,
                visible=not __compact,
            )
        ],
        [
            sg.Multiline(
                key="-OPERATIONS-PROGRESS-STDERR-",
                size=(70, 5),
                visible=not __compact,
                autoscroll=True,
            )
        ],
        [
            sg.Column(
                [
                    [
                        sg.Push(background_color=BG_COLOR_LDR),
                        sg.Text(
                            "↓",
                            key="--EXPAND--",
                            enable_events=True,
                            background_color=BG_COLOR_LDR,
                            text_color=TXT_COLOR_LDR,
                            visible=__compact,
                        ),
                    ],
                    [
                        sg.Image(
                            LOADER_ANIMATION,
                            key="-LOADER-ANIMATION-",
                            background_color=BG_COLOR_LDR,
                            visible=USE_THREADING,
                        )
                    ],
                    [sg.Text("Debugging active", visible=not USE_THREADING)],
                ],
                expand_x=True,
                justification="C",
                element_justification="C",
                background_color=BG_COLOR_LDR,
            )
        ],
        [
            sg.Button(
                _t("generic.cancel"),
                key="--CANCEL--",
                button_color=(TXT_COLOR_LDR, BG_COLOR_LDR),
                disabled=False,
            ),
            sg.Button(
                _t("generic.close"),
                key="--EXIT--",
                button_color=(TXT_COLOR_LDR, BG_COLOR_LDR),
                disabled=True,
            ),
        ],
    ]

    full_layout = [
        [
            sg.Column(
                progress_layout,
                element_justification="C",
                expand_x=True,
                background_color=BG_COLOR_LDR,
            )
        ]
    ]

    progress_window = sg.Window(
        __gui_msg,
        full_layout,
        use_custom_titlebar=False,  # Will not show an icon in task bar if custom titlebar is set unless window is minimized, basically it can be hidden behind others with this option
        grab_anywhere=True,
        disable_close=True,  # Don't allow closing this window via "X" since we still need to update it
        background_color=BG_COLOR_LDR,
        titlebar_icon=OEM_ICON,
    )
    # Finalize the window
    event, values = progress_window.read(timeout=0.01)
    progress_window.bring_to_front()

    read_stdout_queue = __stdout
    read_stderr_queue = True
    read_queues = True

    stdout_cache = ""
    stderr_cache = ""

    if USE_THREADING:
        thread = fn(*args, **kwargs)
    else:
        kwargs = {**kwargs, **{"__no_threads": True}}
        result = runner.__getattribute__(fn.__name__)(*args, **kwargs)

    start_time = time.monotonic()
    while True:
        # No idea why pylint thinks that UpdateAnimation does not exist in SimpleGUI
        # pylint: disable=E1101 (no-member)
        progress_window["-LOADER-ANIMATION-"].UpdateAnimation(
            LOADER_ANIMATION, time_between_frames=100
        )
        # So we actually need to read the progress window for it to refresh...
        event, _ = progress_window.read(0.000000001)
        if event == "--EXPAND--":
            _upgrade_from_compact_view()
        if event == "--CANCEL--":
            result = sg.popup_yes_no(_t("main_gui.cancel_operation"), keep_on_top=True)
            if result == "Yes":
                logger.info("User cancelled operation")
                runner.cancel()
                progress_window["--CANCEL--"].Update(disabled=True)
        # Read stdout queue
        if read_stdout_queue:
            try:
                stdout_data = stdout_queue.get(timeout=GUI_CHECK_INTERVAL)
            except queue.Empty:
                pass
            else:
                if stdout_data is None:
                    logger.debug("gui_thread_runner got stdout queue close signal")
                    read_stdout_queue = False
                else:
                    stdout_cache += stdout_data.strip("\r\n") + "\n"
                    # So the FreeSimpleGUI update implementation is **really** slow to update multiline when autoscroll=True
                    # and there's too much invisible text
                    # we need to create a cache that's updated once
                    # every second or so in order to not block the GUI waiting for GUI redraw

        # Read stderr queue
        if read_stderr_queue:
            try:
                stderr_data = stderr_queue.get(timeout=GUI_CHECK_INTERVAL)
            except queue.Empty:
                pass
            else:
                if stderr_data is None:
                    logger.debug("gui_thread_runner got stderr queue close signal")
                    read_stderr_queue = False
                else:
                    stderr_has_messages = True
                    stderr_cache += stderr_data.strip("\r\n") + "\n"

        read_queues = read_stdout_queue or read_stderr_queue

        if not read_queues:
            # Arbitrary wait time so window get's time to get fully drawn
            sleep(0.2)
            break

        if stderr_has_messages and not __ignore_errors:
            _upgrade_from_compact_view()
            # Make sure we will keep the window visible since we have errors
            __autoclose = False

        if start_time - time.monotonic() > 1:
            _update_gui_from_cache(stdout_cache, stderr_cache)
            stdout_cache = ""
            stderr_cache = ""
            start_time = time.monotonic()

    _update_gui_from_cache(stdout_cache, stderr_cache)

    progress_window["--EXIT--"].Update(disabled=False)
    # Keep the window open until user has done something
    progress_window["-LOADER-ANIMATION-"].Update(visible=False)
    if (not __autoclose or stderr_has_messages) and not __ignore_errors:
        while not progress_window.is_closed():
            event, _ = progress_window.read()
            if event in (sg.WIN_CLOSED, sg.WIN_X_EVENT, "--EXIT--"):
                break
    progress_window.close()
    if USE_THREADING:
        return thread.result()
    # Do not change this because of linter, it's a false positive to say we can remove the else statement
    else:
        return result
