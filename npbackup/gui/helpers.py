#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.helpers"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023122201"


from typing import Tuple, Callable
from logging import getLogger
from time import sleep
import re
import queue
import PySimpleGUI as sg
from npbackup.core.i18n_helper import _t
from npbackup.customization import (
    LOADER_ANIMATION,
    GUI_LOADER_COLOR,
    GUI_LOADER_TEXT_COLOR,
)
from npbackup.core.runner import NPBackupRunner
from npbackup.__debug__ import _DEBUG
from npbackup.customization import PYSIMPLEGUI_THEME, OEM_ICON, OEM_LOGO

logger = getLogger()


sg.theme(PYSIMPLEGUI_THEME)
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

    runner = NPBackupRunner()
    # So we don't always init repo_config, since runner.group_runner would do that itself
    if __repo_config:
        runner.repo_config = __repo_config
    stdout_queue = queue.Queue()
    stderr_queue = queue.Queue()
    fn = getattr(runner, __fn_name)
    logger.debug(
        f"gui_thread_runner runs {fn.__name__} {'with' if USE_THREADING else 'without'} threads"
    )

    runner.stdout = stdout_queue
    runner.stderr = stderr_queue

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
                text_color=GUI_LOADER_TEXT_COLOR,
                background_color=GUI_LOADER_COLOR,
                visible=not __compact,
            )
        ],
        [
            sg.Multiline(
                key="-OPERATIONS-PROGRESS-STDOUT-",
                size=(70, 5),
                visible=not __compact,
                autoscroll=True,
            )
        ],
        [
            sg.Text(
                _t("main_gui.error_messages"),
                key="-OPERATIONS-PROGRESS-STDERR-TITLE-",
                text_color=GUI_LOADER_TEXT_COLOR,
                background_color=GUI_LOADER_COLOR,
                visible=not __compact,
            )
        ],
        [
            sg.Multiline(
                key="-OPERATIONS-PROGRESS-STDERR-",
                size=(70, 10),
                visible=not __compact,
                autoscroll=True,
            )
        ],
        [
            sg.Column(
                [
                    [
                        sg.Image(
                            LOADER_ANIMATION,
                            key="-LOADER-ANIMATION-",
                            background_color=GUI_LOADER_COLOR,
                            visible=USE_THREADING,
                        )
                    ],
                    [sg.Text("Debugging active", visible=not USE_THREADING)],
                ],
                expand_x=True,
                justification="C",
                element_justification="C",
                background_color=GUI_LOADER_COLOR,
            )
        ],
        [
            sg.Button(
                _t("generic.close"),
                key="--EXIT--",
                button_color=(GUI_LOADER_TEXT_COLOR, GUI_LOADER_COLOR),
            )
        ],
    ]

    full_layout = [
        [
            sg.Column(
                progress_layout,
                element_justification="C",
                expand_x=True,
                background_color=GUI_LOADER_COLOR,
            )
        ]
    ]

    progress_window = sg.Window(
        __gui_msg,
        full_layout,
        use_custom_titlebar=True,
        grab_anywhere=True,
        keep_on_top=True,
        background_color=GUI_LOADER_COLOR,
        titlebar_icon=OEM_ICON,
    )
    event, values = progress_window.read(timeout=0.01)

    read_stdout_queue = True
    read_stderr_queue = True
    read_queues = True
    if USE_THREADING:
        thread = fn(*args, **kwargs)
    else:
        kwargs = {**kwargs, **{"__no_threads": True}}
        result = runner.__getattribute__(fn.__name__)(*args, **kwargs)
    while True:
        # No idea why pylint thingks that UpdateAnimation does not exist in PySimpleGUI
        progress_window["-LOADER-ANIMATION-"].UpdateAnimation(
            LOADER_ANIMATION, time_between_frames=100
        )  # pylint: disable=E1101 (no-member)
        # So we actually need to read the progress window for it to refresh...
        _, _ = progress_window.read(0.01)
        # Read stdout queue
        try:
            stdout_data = stdout_queue.get(timeout=0.01)
        except queue.Empty:
            pass
        else:
            if stdout_data is None:
                logger.debug("gui_thread_runner got stdout queue close signal")
                read_stdout_queue = False
            else:
                progress_window["-OPERATIONS-PROGRESS-STDOUT-"].Update(
                    f"\n{stdout_data}", append=True
                )

        # Read stderr queue
        try:
            stderr_data = stderr_queue.get(timeout=0.01)
        except queue.Empty:
            pass
        else:
            if stderr_data is None:
                logger.debug("gui_thread_runner got stderr queue close signal")
                read_stderr_queue = False
            else:
                stderr_has_messages = True
                if __compact:
                    for key in progress_window.AllKeysDict:
                        progress_window[key].Update(visible=True)
                progress_window["-OPERATIONS-PROGRESS-STDERR-"].Update(
                    f"\n{stderr_data}", append=True
                )

        read_queues = read_stdout_queue or read_stderr_queue

        if not read_queues:
            # Arbitrary wait time so window get's time to get fully drawn
            sleep(0.2)
            break

        if stderr_has_messages:
            _upgrade_from_compact_view()
            # Make sure we will keep the window visible since we have errors
            __autoclose = False

    # Keep the window open until user has done something
    progress_window["-LOADER-ANIMATION-"].Update(visible=False)
    if not __autoclose or stderr_has_messages:
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
