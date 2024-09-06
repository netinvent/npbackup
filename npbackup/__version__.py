#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup"
__author__ = "Orsiris de Jong"
__site__ = "https://www.netperfect.fr/npbackup"
__description__ = "NetPerfect Backup Client"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024090601"
__version__ = "3.0.0-rc5"


import sys
import psutil
from ofunctions.platform import python_arch, get_os_identifier
from npbackup.configuration import IS_PRIV_BUILD
from npbackup.core.nuitka_helper import IS_COMPILED

try:
    CURRENT_USER = psutil.Process().username()
except Exception:
    CURRENT_USER = "unknown"
version_string = f"{__intname__} v{__version__}-{'priv' if IS_PRIV_BUILD else 'pub'}-{sys.version_info[0]}.{sys.version_info[1]}-{python_arch()} {__build__} - {__copyright__} running as {CURRENT_USER}"
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
