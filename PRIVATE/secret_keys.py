#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup._private_secret_keys"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026031001"

from npbackup.audience import CURRENT_AUDIENCE

import importlib
import sys

try:
    _private_secret_keys = importlib.import_module(f"PRIVATE.{CURRENT_AUDIENCE}._private_secret_keys", package=None)
except ModuleNotFoundError:
    print(f"{__file__}: No customization module found for audience '{CURRENT_AUDIENCE}'")
    sys.exit(244)

AES_KEY = _private_secret_keys.AES_KEY
EARLIER_AES_KEYS = _private_secret_keys.EARLIER_AES_KEYS
try:
    PUBLIC_AES_KEYS_FOR_PRIVATE_MIGRATION = _private_secret_keys.PUBLIC_AES_KEYS_FOR_PRIVATE_MIGRATION
except AttributeError:
    PUBLIC_AES_KEYS_FOR_PRIVATE_MIGRATION = []