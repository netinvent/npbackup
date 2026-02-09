#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.helpers"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025070302"


from typing import Tuple, Union
from logging import getLogger
from time import sleep
import re
import queue
import time
import json
import FreeSimpleGUI as sg
from ofunctions.threading import threaded
from ofunctions.misc import BytesConverter
from npbackup.core.i18n_helper import _t
from resources.customization import (
    LOADER_ANIMATION,
)
from npbackup.core.runner import NPBackupRunner
from npbackup.__debug__ import _DEBUG
from npbackup.__env__ import GUI_CHECK_INTERVAL
from resources.customization import SIMPLEGUI_THEME, OEM_ICON

logger = getLogger()


sg.SetOptions(icon=OEM_ICON)


# For debugging purposes, we should be able to disable threading to see actual errors
# out of thread
if not _DEBUG:
    USE_THREADING = True
else:
    USE_THREADING = False
    logger.info("Running without threads as per debug requirements")

# Seconds between screen refreshes
UPDATE_INTERVAL = 1
# Seconds between total average speed updates
TOTAL_AVERAGE_INTERVAL = 5


def get_anon_repo_uri(repository: str) -> Tuple[str, str]:
    """
    Remove user / password part from repository uri
    """
    if not repository:
        return "UNDEFINED", None
    repo_type = repository.split(":")[0].upper()
    if repo_type.upper() in ["REST", "SFTP"]:
        res = re.match(
            r"(sftp|rest)(.*:\/\/)(.*):?(.*)@(.*)", repository, re.IGNORECASE
        )
        if res:
            repo_uri = res.group(1) + res.group(2) + res.group(5)
        else:
            repo_uri = repository
    elif repo_type.upper() in [
        "S3",
        "B2",
        "SWIFT",
        "AZURE",
        "GS",
        "RCLONE",
    ]:
        repo_uri = repository
    else:
        repo_type = "LOCAL"
        repo_uri = repository
    return repo_type, repo_uri


def gui_thread_runner(
    __repo_config: dict,
    __fn_name: str,
    __compact: bool = True,
    __autoclose: bool = False,
    __gui_msg: str = "",
    __stdout: bool = True,
    __backend_binary: str = None,
    __ignore_errors: bool = False,
    __no_lock: bool = False,
    __full_concurrency: bool = False,
    __repo_aware_concurrency: bool = False,
    *args,
    **kwargs,
) -> Union[dict, str]:
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
            progress_window["-OPERATIONS-PROGRESS-STDOUT-"].Update(_stdout_cache)
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

    if __ignore_errors:
        runner.produce_metrics = False

    runner.no_lock = __no_lock

    runner.full_concurrency = __full_concurrency
    runner.repo_aware_concurrency = __repo_aware_concurrency

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
                        sg.Push(),
                        sg.Text(
                            "↓",
                            key="--EXPAND--",
                            enable_events=True,
                            visible=__compact,
                        ),
                    ],
                    [
                        sg.Image(
                            LOADER_ANIMATION,
                            key="-LOADER-ANIMATION-",
                        )
                    ],
                    [sg.Text("Debugging active", visible=not USE_THREADING)],
                ],
                expand_x=True,
                justification="C",
                element_justification="C",
            )
        ],
        [
            sg.Button(
                _t("generic.cancel"),
                key="--CANCEL--",
                disabled=False,
            ),
            sg.Button(
                _t("generic.close"),
                key="--EXIT--",
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
            )
        ]
    ]

    progress_window = sg.Window(
        __gui_msg,
        full_layout,
        use_custom_titlebar=False,  # Will not show an icon in task bar if custom titlebar is set unless window is minimized, basically it can be hidden behind others with this option
        grab_anywhere=True,
        disable_close=True,  # Don't allow closing this window via "X" since we still need to update it
        titlebar_icon=OEM_ICON,
    )
    # Finalize the window
    event, _ = progress_window.read(timeout=0.01)
    # window.bring_to_front() does not work, so we need to force focus on it
    progress_window.TKroot.focus_force()

    read_stdout_queue = __stdout
    read_stderr_queue = True
    read_queues = True

    stdout_cache = ""
    stderr_cache = ""
    previous_stdout_cache = ""
    previous_stderr_cache = ""

    if USE_THREADING:
        thread = fn(*args, **kwargs)
    else:
        kwargs = {**kwargs, **{"__no_threads": True}}
        result = runner.__getattribute__(fn.__name__)(*args, **kwargs)

    start_time = time.monotonic()
    restore_data = None
    previous_bytes_restored = None
    restore_speed_history = []
    average_speed_history = []
    loop_counter = 0
    while True:
        # No idea why pylint thinks that UpdateAnimation does not exist in SimpleGUI
        # pylint: disable=E1101 (no-member)
        progress_window["-LOADER-ANIMATION-"].UpdateAnimation(
            LOADER_ANIMATION, time_between_frames=75
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
                    if __fn_name == "restore":
                        # We only need last line since restore outputs self contained json status lines
                        stdout_cache = stdout_data
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
            # Arbitrary wait time so window gets time to get fully drawn
            sleep(0.2)
            break

        if stderr_has_messages and not __ignore_errors:
            _upgrade_from_compact_view()
            # Make sure we will keep the window visible since we have errors
            __autoclose = False

        if time.monotonic() - start_time > UPDATE_INTERVAL:
            if len(stdout_cache) > 1000:
                stdout_cache = stdout_cache[-1000:]
            if __fn_name == "restore":
                try:
                    restore_data = json.loads(stdout_cache)
                    try:
                        if previous_bytes_restored:
                            instant_throughput_per_second = (
                                restore_data["bytes_restored"] - previous_bytes_restored
                            ) / UPDATE_INTERVAL
                            restore_data["instant_throughput_per_second"] = (
                                BytesConverter(
                                    instant_throughput_per_second
                                ).human_iec_bytes
                            )
                            restore_speed_history.append(instant_throughput_per_second)
                            # Keep only last 300 seconds of restore speed history
                            restore_speed_history = restore_speed_history[-300:]
                            restore_data["average_5m_throughput_per_second"] = (
                                BytesConverter(
                                    sum(restore_speed_history)
                                    / len(restore_speed_history)
                                ).human_iec_bytes
                            )
                            if loop_counter % TOTAL_AVERAGE_INTERVAL == 0:
                                average_speed_history.append(
                                    sum(restore_speed_history)
                                    / len(restore_speed_history)
                                )
                            if average_speed_history:
                                restore_data["total_average_throughput_per_second"] = (
                                    BytesConverter(
                                        sum(average_speed_history)
                                        / len(average_speed_history)
                                    ).human_iec_bytes
                                )
                        previous_bytes_restored = restore_data["bytes_restored"]
                        restore_data["total_bytes"] = BytesConverter(
                            restore_data["total_bytes"]
                        ).human_iec_bytes
                        restore_data["bytes_restored"] = BytesConverter(
                            restore_data["bytes_restored"]
                        ).human_iec_bytes
                    except KeyError:
                        pass
                    stdout_cache = json.dumps(restore_data, indent=4)
                except json.JSONDecodeError:
                    pass
            # Don't update GUI if there isn't anything to update so it will avoid scrolling back to top every second
            if (
                previous_stdout_cache != stdout_cache
                or previous_stderr_cache != stderr_cache
            ):
                _update_gui_from_cache(stdout_cache, stderr_cache)
                previous_stdout_cache = stdout_cache
                previous_stderr_cache = stderr_cache
            start_time = time.monotonic()
            loop_counter += 1

    if restore_data:
        stdout_cache = json.dumps(restore_data, indent=4) + "\n\n" + stdout_cache
    _update_gui_from_cache(stdout_cache, stderr_cache)

    progress_window["--CANCEL--"].Update(disabled=True)
    progress_window["--EXIT--"].Update(disabled=False)
    if stderr_has_messages:
        progress_window["--EXIT--"].update(
            button_color=(sg.theme_button_color()[0], "red")
        )
    else:
        progress_window["--EXIT--"].update(
            button_color=(sg.theme_button_color()[0], "green")
        )
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


class HideWindow:
    """
    Context manager to hide a window when a new one is opened
    This prevents showing blocked windows
    """

    def __init__(self, window):
        self.window = window

    def __enter__(self):
        self.window.hide()

    def __exit__(self, exc_type, exc_value, traceback):
        # exit method receives optional traceback from execution within with statement
        self.window.un_hide()


@threaded
def quick_close_simplegui_window(window: sg.Window) -> None:
    """
    Closes a SimpleGUI window without waiting for the framework to "deconstruct the window"
    This is useful for closing windows that are not needed anymore
    """
    if window:
        try:
            window.close()
        except Exception as exc:
            logger.error(f"Error closing SimpleGUI window: {exc}")
