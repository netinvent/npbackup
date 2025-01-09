#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.path_helper"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2024091701"


# This file must exist at the root of the package, for basedir to be detected as root


import sys
import os


# This is the path to a python script, a standalone or a onefile nuitka generated binary
# When running python interpreter without any script, sys.argv is empty hence CURRENT_EXECUTABLE would become current directory
CURRENT_EXECUTABLE = os.path.abspath(sys.argv[0])
CURRENT_DIR = os.path.dirname(CURRENT_EXECUTABLE)
# When run with nuitka onefile, this will be the temp directory, else, this will be the path to current file
BASEDIR = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))

