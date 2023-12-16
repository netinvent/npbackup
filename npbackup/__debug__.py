#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.__debug__"
__author__ = "Orsiris de Jong"
__site__ = "https://www.netperfect.fr/npbackup"
__description__ = "NetPerfect Backup Client"
__copyright__ = "Copyright (C) 2023 NetInvent"


import os


# If set, debugging will be enabled by setting envrionment variable to __SPECIAL_DEBUG_STRING content
# Else, a simple true or false will suffice
__SPECIAL_DEBUG_STRING = ""
__debug_os_env = os.environ.get("_DEBUG", "False").strip("'\"")

try:
    _DEBUG
except NameError:
    _DEBUG = False
    if __SPECIAL_DEBUG_STRING:
        if __debug_os_env == __SPECIAL_DEBUG_STRING:
            _DEBUG = True
    elif __debug_os_env.capitalize() == "True":
        _DEBUG = True
