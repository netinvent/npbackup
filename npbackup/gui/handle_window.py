#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.windows_gui_helper"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025070101"


import sys
import os
from logging import getLogger

logger = getLogger()


def handle_current_window(action: str = "minimize") -> None:
    """
    Minimizes / hides current commandline window in GUI mode
    This helps when Nuitka cmdline hide action does not work

    Solution found on https://stackoverflow.com/a/75523959/2635443
    which also works for Windows 11 since they replaced conhost with the new Windows Terminal.
    """
    try:
        if os.name == "nt":
            # pylint: disable=E0401 (import-error)
            import win32gui

            # pylint: disable=E0401 (import-error)
            import win32con
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32")


            current_executable = os.path.abspath(sys.argv[0])
            # console window will have the name of current executable
            hWnd = win32gui.FindWindow(None, current_executable)
            if not hWnd:
                logger.debug(f"Could not find window with name {current_executable}, trying to get console window.")
                # get the console window
                # pylint: disable=I1101 (c-extension-no-member)
                hWnd = kernel32.GetConsoleWindow()

            if not hWnd:
                logger.debug(f"Console window not found. Cannot {action} it.")
                return
            # set it as foreground
            # pylint: disable=I1101 (c-extension-no-member)
            win32gui.SetForegroundWindow(hWnd)

            # get the foreground window
            # pylint: disable=I1101 (c-extension-no-member)
            hWnd = win32gui.GetForegroundWindow()

            # hide it
            if action == "minimize":
                # pylint: disable=I1101 (c-extension-no-member)
                win32gui.ShowWindow(hWnd, win32con.SW_MINIMIZE)
            elif action == "hide":
                # pylint: disable=I1101 (c-extension-no-member)
                win32gui.ShowWindow(hWnd, win32con.SW_HIDE)
            elif action == "show":
                # pylint: disable=I1101 (c-extension-no-member)
                win32gui.ShowWindow(hWnd, win32con.SW_SHOW)
            else:
                raise ValueError(
                    f"Bad action parameter for handling current window: {action}"
                )
    except Exception as exc:
        logger.info(f"Error handling current window: {exc}")