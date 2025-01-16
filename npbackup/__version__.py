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
__build__ = "2025011501"
__version__ = "3.0.0-rc14"


import sys
import psutil
from ofunctions.platform import python_arch, get_os_identifier
from npbackup.configuration import IS_PRIV_BUILD
from npbackup.core.nuitka_helper import IS_COMPILED


# Python 3.7 versions are considered legacy since they don't support msgspec
# Since developpment currently follows Python 3.12, let's consider anything below 3.12 as legacy
IS_LEGACY = True if sys.version_info[1] < 12 else False

try:
    CURRENT_USER = psutil.Process().username()
except Exception:
    CURRENT_USER = "unknown"
version_dict = {
    "name": __intname__,
    "version": __version__,
    "build_type": "priv" if IS_PRIV_BUILD else "pub",
    "os": get_os_identifier(),
    "arch": python_arch() + ("-legacy" if IS_LEGACY else ""),
    "pv": sys.version_info,
    "comp": IS_COMPILED,
    "build": __build__,
    "copyright": __copyright__,
}
version_string = f"{version_dict['name']} {version_dict['version']}-{version_dict['buildtype']}-{version_dict['pv'][0]}.{version_dict['pv'][1]}-{version_dict['arch']}{'-c' if IS_COMPILED else '-i'} {version_dict['build']} - {version_dict['copyright']} running as {CURRENT_USER}"
