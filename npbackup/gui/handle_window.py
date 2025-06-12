#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.windows_gui_helper"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025061201"


import sys
import os
from logging import getLogger

logger = getLogger()


def handle_current_window(action: str = "minimize") -> None:
    """
    Minimizes / hides current commandline window in GUI mode
    This helps when Nuitka cmdline hide action does not work
    """
    if os.name == "nt":
        # pylint: disable=E0401 (import-error)
        import win32gui

        # pylint: disable=E0401 (import-error)
        import win32con

        current_executable = os.path.abspath(sys.argv[0])
        # console window will have the name of current executable
        hwndMain = win32gui.FindWindow(None, current_executable)
        if not hwndMain:
            logger.debug(
                "No hwndmain found for current executable, trying foreground window"
            )
            hwndMain = win32gui.GetForegroundWindow()
        if hwndMain:
            if action == "minimize":
                win32gui.ShowWindow(hwndMain, win32con.SW_MINIMIZE)
            elif action == "hide":
                win32gui.ShowWindow(hwndMain, win32con.SW_HIDE)
            else:
                raise ValueError(
                    f"Bad action parameter for handling current window: {action}"
                )
        else:
            logger.debug(
                f"No window found for current executable {current_executable}, cannot minimize/hide"
            )
