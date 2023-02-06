#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.window_reducer"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023020601"


import sys
import os


def minimize_current_window():
    """
    Minimizes current commandline window in GUI mode
    """
    if os.name == "nt":
        import win32gui
        import win32con
        current_executable = os.path.abspath(sys.argv[0])
        # console window will have the name of current executable
        hwndMain = win32gui.FindWindow(None, current_executable)
        if hwndMain:
            win32gui.ShowWindow(hwndMain, win32con.SW_MINIMIZE)
