#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.ttk_theme"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2025-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025112101"

import os
import FreeSimpleGUI as sg
import sv_ttk
from tkinter import ttk
from reskinner import reskin
from resources.customization import SIMPLEGUI_THEME, SIMPLEGUI_DARK_THEME

# Make app DPI aware on Windows
# Balantly stolen from https://github.com/PySimpleGUI/PySimpleGUI/issues/3880#issuecomment-775990455
# WIP: We might want this to be optional
# WIP: Dcumentation
if os.environ.get("NPBACKUP_DPI_AWARENESS", "True").lower() == "true":
    pass
sg.set_options(dpi_awareness=True)
try:
    scaling = float(os.environ.get("NPBACKUP_SCALING", "1.0"))
except (TypeError, ValueError):
    scaling = None
if scaling:
    sg.set_options(scaling=scaling)
theme = os.environ.get("NPBACKUP_THEME", "light").lower()
if theme == "dark":
    CURRENT_THEME = SIMPLEGUI_DARK_THEME
    CURRENT_TTK_THEME = "sun-valley-dark"
else:
    CURRENT_THEME = SIMPLEGUI_THEME
    CURRENT_TTK_THEME = "sun-valley-light"

root = sg.tk.Tk()
scale = 96/root.winfo_fpixels('1i')     # Format your layout if when 96 DPI
root.destroy()

def scaled(pixels):
    return round(scale*pixels)

sg.theme(CURRENT_THEME)
sg.DEFAULT_TTK_THEME = CURRENT_TTK_THEME
sg.ADDITIONAL_TTK_STYLING_PATHS = os.path.join(os.path.dirname(sv_ttk.__file__), "sv.tcl")
#sg.DEFAULT_TTK_THEME = "azure-light"
#sg.ADDITIONAL_TTK_STYLING_PATHS = os.path.join(os.path.dirname(__file__), "azure/azure.tcl")
sg.USE_TTK_BUTTONS = False

CURRENT_THEME = SIMPLEGUI_THEME
RESKIN_WINDOW = None

def reskin_job(window=None, theme=None):
    global CURRENT_THEME
    global RESKIN_WINDOW

    RESKIN_WINDOW = window
    CURRENT_THEME = theme
    if RESKIN_WINDOW:
        reskin(
            window=RESKIN_WINDOW,
            new_theme=CURRENT_THEME,
            theme_function=sg.theme,
            lf_table=sg.LOOK_AND_FEEL_TABLE,
        )
        sg.DEFAULT_TTK_THEME = "sun-valley-dark" if CURRENT_THEME == SIMPLEGUI_DARK_THEME else "sun-valley-light"
        #sg.DEFAULT_TTK_THEME = "azure-dark" if CURRENT_THEME == SIMPLEGUI_DARK_THEME else "azure-light"
        
        # We must force SimpleGUI to update it's ttk theme as well
        style = ttk.Style(window.hidden_master_root)
        sg._change_ttk_theme(style, sg.DEFAULT_TTK_THEME)

    RESKIN_WINDOW.TKroot.after(60000, reskin_job)