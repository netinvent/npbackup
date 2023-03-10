#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.restic_source_binary"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023011701"


import os
import glob
from npbackup.path_helper import BASEDIR


RESTIC_SOURCE_FILES_DIR = os.path.join(BASEDIR, os.pardir, "RESTIC_SOURCE_FILES")


def get_restic_internal_binary(arch):
    binary = None
    if os.path.isdir(RESTIC_SOURCE_FILES_DIR):
        if os.name == "nt":
            if arch == "x64":
                binary = "restic_*_windows_amd64.exe"
            else:
                binary = "restic_*_windows_386.exe"
        else:
            if arch == "x64":
                binary = "restic_*_linux_amd64"
            else:
                binary = "restic_*_linux_386"
    if binary:
        guessed_path = glob.glob(os.path.join(RESTIC_SOURCE_FILES_DIR, binary))
        if guessed_path:
            return guessed_path[0]
