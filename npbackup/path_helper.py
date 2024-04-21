#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.path_helper"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2024 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2023012201"


# This file must exist at the root of the package, for basedir to be detected as root


import sys
import os


# This is the path to a onefile executable binary
CURRENT_EXECUTABLE = os.path.abspath(sys.argv[0])
CURRENT_DIR = os.path.dirname(CURRENT_EXECUTABLE)
# When run with nuitka onefile, this will be the temp directory, else, this will be the path to current file
BASEDIR = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
