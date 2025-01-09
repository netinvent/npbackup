#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup"
__author__ = "Orsiris de Jong"
__site__ = "https://www.netperfect.fr/npbackup"
__description__ = "NetPerfect Backup Client"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025010901"
__version__ = "3.0.0-rc13"


import sys
import psutil
from ofunctions.platform import python_arch, get_os_identifier
from npbackup.configuration import IS_PRIV_BUILD
from npbackup.core.nuitka_helper import IS_COMPILED
from npbackup.path_helper import IS_LEGACY

try:
    CURRENT_USER = psutil.Process().username()
except Exception:
    CURRENT_USER = "unknown"
version_string = f"{__intname__} v{__version__}-{'priv' if IS_PRIV_BUILD else 'pub'}-{sys.version_info[0]}.{sys.version_info[1]}-{python_arch()}{'-legacy' if IS_LEGACY else ''}{'-c' if IS_COMPILED else '-i'} {__build__} - {__copyright__} running as {CURRENT_USER}"
version_dict = {
    "name": __intname__,
    "version": __version__,
    "buildtype": "priv" if IS_PRIV_BUILD else "pub",
    "os": get_os_identifier(),
    "arch": python_arch(),
    "pv": sys.version_info,
    "comp": IS_COMPILED,
    "build": __build__,
    "copyright": __copyright__,
}


# Python 3.7 versions are considered legacy since they don't support msgspec
# Pytohn 3.9 has some issues with msgspec.struct (using a struct decoder will fail with "msgspec.ValidationError: Expected `LsNode`, got `dict`")
IS_LEGACY = True if sys.version_info[1] < 10 else False
