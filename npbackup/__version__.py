#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup"
__author__ = "Orsiris de Jong"
__site__ = "https://www.netperfect.fr/npbackup"
__description__ = "NetPerfect Backup Client"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023121001"
__version__ = "2.3.0-dev"


import sys
from ofunctions.platform import python_arch
from npbackup.configuration import IS_PRIV_BUILD

version_string = "{} v{}{}{}-{} {} - {}".format(
    __intname__,
    __version__,
    "-PRIV" if IS_PRIV_BUILD else "",
    "-P{}".format(sys.version_info[1]),
    python_arch(),
    __build__,
    __copyright__,
)
