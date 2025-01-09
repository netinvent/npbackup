#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.viewer"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"


from npbackup.gui.__main__ import main_gui


def viewer_gui():
    main_gui(viewer_mode=True)


if __name__ == "__main__":
    viewer_gui()
