#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.PRIVATE.audiences"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026031101"
__version__ = "1.0.0"

# This file decides what kind of build we are running
# Public builds exist on github
# Private builds can be added in PRIVATE/{audience_name} directories
# and can be used to include customizations and secrets for specific audiences, without risking them being leaked in public builds

import os

AUDIENCES = ["public", "example"]
CURRENT_AUDIENCE = "example"

# Allow overriding audience via environment variable, for testing purposes. This is not intended for production use.
override_audience = os.environ.get("_NPBACKUP_AUDIENCE", None)
if override_audience:
    CURRENT_AUDIENCE = override_audience