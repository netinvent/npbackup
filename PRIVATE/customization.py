#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup._customization"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023032601"

from npbackup.path_helper import NPBACKUP_ROOT_DIR
from resources.audience import CURRENT_AUDIENCE

import importlib.util
import sys
import os


MODULE_PATH = os.path.abspath(f"{NPBACKUP_ROOT_DIR}/../PRIVATE/{CURRENT_AUDIENCE}/_customization.py")
if not os.path.isfile(MODULE_PATH):
    print(f"{__file__}: No customization file found for audience '{CURRENT_AUDIENCE}' at expected location: {MODULE_PATH}")
    sys.exit(1)
spec = importlib.util.spec_from_file_location("module.name", MODULE_PATH)
_customization = importlib.util.module_from_spec(spec)
sys.modules["module.name"] = _customization
spec.loader.exec_module(_customization)

# Now load all variables from the _customization module into the current namespace
for attr in dir(_customization):
    if not attr.startswith("__"):
        globals()[attr] = getattr(_customization, attr)
