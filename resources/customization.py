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


## This file switches customization depending on audience

import sys
from resources.audience import CURRENT_AUDIENCE

if CURRENT_AUDIENCE == "public":
    from resources._customization import *
else:
    try:
        from PRIVATE.customization import *
    except ImportError as exc:
        print(f"{__file__}: No private audience with name '{CURRENT_AUDIENCE}' customization found")
        print(exc)
        sys.exit(1)