#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.restic_source_binary"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023061102"


import os
import sys
import glob
from npbackup.path_helper import BASEDIR, IS_LEGACY


RESTIC_SOURCE_FILES_DIR = os.path.join(BASEDIR, os.pardir, "RESTIC_SOURCE_FILES")


def get_restic_internal_binary(arch: str) -> str:
    binary = None
    if os.path.isdir(RESTIC_SOURCE_FILES_DIR):
        if os.name == "nt":
            if IS_LEGACY and arch == "x86":
                # Last compatible restic binary for Windows 7, see https://github.com/restic/restic/issues/5065
                binary = "restic_0.16.2_windows_386.exe"
            if arch == "x64":
                binary = "restic_*_windows_amd64.exe"
            else:
                binary = "restic_*_windows_386.exe"
        elif sys.platform.lower() == "darwin":
            if arch == "arm64":
                binary = "restic_*_darwin_arm64"
            else:
                binary = "restic_*_darwin_amd64"
        else:
            if arch == "arm":
                binary = "restic_*_linux_arm"
            elif arch == "arm64":
                binary = "restic_*_linux_arm64"
            elif arch == "x64":
                binary = "restic_*_linux_amd64"
            else:
                binary = "restic_*_linux_386"
    if binary:
        guessed_path = glob.glob(os.path.join(RESTIC_SOURCE_FILES_DIR, binary))
        if guessed_path:
            # Take glob results reversed so we get newer version
            # Does not always compute, but is g00denough(TM) for our dev
            return guessed_path[-1]
    return None
