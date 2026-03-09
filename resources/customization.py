#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.customization"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025022601"
__version__ = "1.0.0"


## This file switches customization depending on if the PRIVATE directory contains customization.py or not

try:
    from PRIVATE.resources._customization import *
except ImportError:
    from resources._customization import *