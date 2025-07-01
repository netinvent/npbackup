#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.restic_source_binary"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025021401"


import os
import sys
import glob
from logging import getLogger
from npbackup.__version__ import IS_LEGACY
from npbackup.path_helper import BASEDIR

logger = getLogger()

RESTIC_SOURCE_FILES_DIR = os.path.join(BASEDIR, os.pardir, "RESTIC_SOURCE_FILES")


def get_restic_internal_binary(arch: str) -> str:
    binary = None
    if os.path.isdir(RESTIC_SOURCE_FILES_DIR):
        if os.name == "nt":
            if IS_LEGACY or "legacy" in "arch":
                # Last compatible restic binary for Windows 7, see https://github.com/restic/restic/issues/5065
                # We build a legacy version of restic for windows 7 and Server 2008R2
                logger.info(
                    "Dealing with special case for Windows 7 32 bits that doesn't run with restic >= 0.16.2"
                )
                if arch == "x86":
                    binary = "restic_*_windows_legacy_386.exe"
                else:
                    binary = "restic_*_windows_legacy_amd64.exe"
            elif arch == "x86":
                binary = "restic_*_windows_386.exe"
            else:
                binary = "restic_*_windows_amd64.exe"
        else:
            # We don't have restic legacy builds for unixes
            # so we can drop the -legacy suffix
            arch = arch.replace("-legacy", "")
            if sys.platform.lower() == "darwin":
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
    else:
        logger.info("Internal binary directory not set")
        return None
    if binary:
        guessed_path = glob.glob(os.path.join(RESTIC_SOURCE_FILES_DIR, binary))
        if guessed_path:
            # Take glob results reversed so we get newer version
            # Does not always compute, but is g00denough(TM) for our dev
            return guessed_path[-1]
        logger.info(
            f"Could not find internal restic binary, guess {os.path.join(RESTIC_SOURCE_FILES_DIR, binary)} in {guessed_path}"
        )
    return None
