#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup._customization"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026031601"

from npbackup.audience import CURRENT_AUDIENCE

import importlib
import sys

try:
    _customization = importlib.import_module(f"PRIVATE.{CURRENT_AUDIENCE}._customization", package=None)
except ModuleNotFoundError:
    print(f"{__file__}: No customization module found for audience '{CURRENT_AUDIENCE}'")
    sys.exit(244)

for attr in dir(_customization):
    if not attr.startswith("__"):
        globals()[attr] = getattr(_customization, attr)