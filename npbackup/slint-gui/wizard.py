#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup-gui"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"


from logging import root
import slint
import tkinter as tk
from tkinter import filedialog


def xaddsourcefile():
    print("MGOO")
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename()
    print(file_path)
    return file_path

def xaddsourcefolder():
    root = tk.Tk()
    root.withdraw()
    folder_path= filedialog.askdirectory()
    print(folder_path)
    return folder_path

class MainWindow(slint.loader.gallery.App):
    @slint.callback
    def add_source_folder(self):
        xaddsourcefolder()



main_window = MainWindow()
main_window.show()
main_window.run()