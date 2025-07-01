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
__build__ = "2025062601"
__version__ = "3.0.3"


import sys
import psutil
from ofunctions.platform import python_arch, get_os
import npbackup.__env__
from npbackup.key_management import IS_PRIV_BUILD
from npbackup.core.nuitka_helper import IS_COMPILED


# Python 3.7 versions are considered legacy since they don't support msgspec
# msgspec is only supported on Python 3.8 64-bit and above
# Since development currently follows Python 3.12, let's consider anything below 3.12 as legacy
IS_LEGACY = True if (sys.version_info[1] < 12 or python_arch() == "x86") else False


try:
    CURRENT_USER = psutil.Process().username()
except Exception:
    CURRENT_USER = "unknown"
version_dict = {
    "name": __intname__,
    "version": __version__,
    "build_type": npbackup.__env__.BUILD_TYPE,
    "audience": "private" if IS_PRIV_BUILD else "public",
    "os": get_os().lower(),
    "arch": python_arch() + ("-legacy" if IS_LEGACY else ""),
    "pv": sys.version_info,
    "comp": IS_COMPILED,
    "build": __build__,
    "copyright": __copyright__,
}
version_string = f"{version_dict['name']} {version_dict['version']}-{version_dict['os']}-{version_dict['build_type']}-{version_dict['arch']}-{version_dict['audience']}-{version_dict['pv'][0]}.{version_dict['pv'][1]}-{'c' if IS_COMPILED else 'i'} {version_dict['build']} - {version_dict['copyright']} running as {CURRENT_USER}"
