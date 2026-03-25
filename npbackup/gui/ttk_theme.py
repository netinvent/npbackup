#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.ttk_theme"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2025-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026031601"

import os
import FreeSimpleGUI as sg

from reskinner import reskin, colorizer
from npbackup.path_helper import BASEDIR
from npbackup.gui.buttons import _after_element
from resources.customization import (
    SIMPLEGUI_THEME,
    SIMPLEGUI_DARK_THEME,
    STANDARD_FONT,
    SUBTITLE_FONT,  # Is needed for imports by other gui files
    TITLE_FONT,  # Is needed for imports by other gui files
)

try:
    from resources.customization import SG_CUSTOM_THEME, SG_CUSTOM_DARK_THEME

    # Override current theme names with ours
    sg.theme_add_new(SIMPLEGUI_THEME, SG_CUSTOM_THEME)
    sg.theme_add_new(SIMPLEGUI_DARK_THEME, SG_CUSTOM_DARK_THEME)
except ImportError:
    pass

ttk_theme_path = os.path.join(
    os.path.dirname(BASEDIR), "npbackup", "gui", "sv_ttk", "sv.tcl"
)
if os.path.isfile(ttk_theme_path):
    HAVE_TTK_THEME = True
    from tkinter import ttk
else:
    HAVE_TTK_THEME = False

CURRENT_THEME = SIMPLEGUI_THEME
sg.DEFAULT_FONT = STANDARD_FONT

# Make app DPI aware on Windows
# Blatantly stolen from https://github.com/PySimpleGUI/PySimpleGUI/issues/3880#issuecomment-775990455
# WIP: We might want this to be optional
# WIP: Documentation
# WIP: add darkdetect
if os.environ.get("NPBACKUP_DPI_AWARENESS", "True").lower() == "true":
    sg.set_options(dpi_awareness=True)

try:
    WINDOW_SCALING = float(os.environ.get("NPBACKUP_SCALING", None))
except (TypeError, ValueError):
    WINDOW_SCALING = 1.0
if WINDOW_SCALING:
    sg.set_options(scaling=WINDOW_SCALING)
theme = os.environ.get("NPBACKUP_THEME", "light").lower()
if theme == "dark":
    CURRENT_THEME = SIMPLEGUI_DARK_THEME
    CURRENT_TTK_THEME = "sun-valley-dark"
else:
    CURRENT_THEME = SIMPLEGUI_THEME
    CURRENT_TTK_THEME = "sun-valley-light"

if HAVE_TTK_THEME:
    sg.DEFAULT_TTK_THEME = CURRENT_TTK_THEME
    sg.ADDITIONAL_TTK_STYLING_PATHS = ttk_theme_path
    sg.USE_TTK_BUTTONS = False

# Get actual pixel size for scaling
root = sg.tk.Tk()
scale = 96 / root.winfo_fpixels("1i")  # Format your layout if when 96 DPI
root.destroy()


def scaled(pixels):
    return round(scale * pixels)


sg.theme(CURRENT_THEME)

RESKIN_WINDOW = None


def change_sg_theme(window=None, refresh: bool = False):
    global CURRENT_THEME
    if not refresh:
        if sg.theme() != SIMPLEGUI_DARK_THEME:
            CURRENT_THEME = SIMPLEGUI_DARK_THEME
            if HAVE_TTK_THEME:
                sg.DEFAULT_TTK_THEME = "sun-valley-dark"
        else:
            CURRENT_THEME = SIMPLEGUI_THEME
            if HAVE_TTK_THEME:
                sg.DEFAULT_TTK_THEME = "sun-valley-light"
    if HAVE_TTK_THEME:
        # pylint: disable=E0606 (possibly-used-before-assignment)
        style = ttk.Style(window.hidden_master_root)
        sg._change_ttk_theme(style, sg.DEFAULT_TTK_THEME)
    reskin(
        window=window,
        new_theme=CURRENT_THEME,
        theme_function=sg.theme,
        lf_table=sg.LOOK_AND_FEEL_TABLE,
        duration=300,
        after_element=_after_element,
    )
    window.refresh()
