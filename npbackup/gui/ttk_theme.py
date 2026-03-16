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

# Python 3.8 doesn't have sv_ttk theme
try:
    import sv_ttk

    HAVE_TTK_THEME = True
except ImportError:
    sv_ttk = None
    HAVE_TTK_THEME = False
if HAVE_TTK_THEME:
    from tkinter import ttk
    from reskinner import reskin
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
    scaling = float(os.environ.get("NPBACKUP_SCALING", None))
except (TypeError, ValueError):
    scaling = 1.0
if scaling:
    sg.set_options(scaling=scaling)
theme = os.environ.get("NPBACKUP_THEME", "light").lower()
if theme == "dark":
    CURRENT_THEME = SIMPLEGUI_DARK_THEME
    CURRENT_TTK_THEME = "sun-valley-dark"
else:
    CURRENT_THEME = SIMPLEGUI_THEME
    CURRENT_TTK_THEME = "sun-valley-light"

# Get actual pixel size for scaling
root = sg.tk.Tk()
scale = 96 / root.winfo_fpixels("1i")  # Format your layout if when 96 DPI
root.destroy()


def scaled(pixels):
    return round(scale * pixels)


sg.theme(CURRENT_THEME)
if HAVE_TTK_THEME:
    sg.DEFAULT_TTK_THEME = CURRENT_TTK_THEME
    sg.ADDITIONAL_TTK_STYLING_PATHS = os.path.join(
        os.path.dirname(sv_ttk.__file__), "sv.tcl"
    )
# sg.DEFAULT_TTK_THEME = "azure-light"
# sg.ADDITIONAL_TTK_STYLING_PATHS = os.path.join(os.path.dirname(__file__), "azure/azure.tcl")
sg.USE_TTK_BUTTONS = False

RESKIN_WINDOW = None


def change_sg_theme(window=None):
    global CURRENT_THEME
    if sg.theme() != SIMPLEGUI_DARK_THEME:
        CURRENT_THEME = SIMPLEGUI_DARK_THEME
        if HAVE_TTK_THEME:
            sg.DEFAULT_TTK_THEME = "sun-valley-dark"
    else:
        CURRENT_THEME = SIMPLEGUI_THEME
        if HAVE_TTK_THEME:
            sg.DEFAULT_TTK_THEME = "sun-valley-light"
    if HAVE_TTK_THEME:
        style = ttk.Style(window.hidden_master_root)
        sg._change_ttk_theme(style, sg.DEFAULT_TTK_THEME)
    reskin(
        window=window,
        new_theme=CURRENT_THEME,
        theme_function=sg.theme,
        lf_table=sg.LOOK_AND_FEEL_TABLE,
    )
