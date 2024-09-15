#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.restic_wrapper.schema"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2024 NetInvent"
__license__ = "GPL-3.0-only"
__description__ = "Restic json output schemas"


from typing import Optional
from datetime import datetime

try:
    from msgspec import Struct
    from enum import StrEnum
    MSGSPEC = True
except ImportError:

    class Struct:
        def __init_subclass__(self, *args, **kwargs):
            pass
        pass
    class StrEnum:
        pass

    MSGSPEC = False


class LsNodeType(StrEnum):
    FILE = "file"
    DIR = "dir"
    SYMLINK = "symlink"
    IRREGULAR = "irregular"


class LsNode(Struct, omit_defaults=True):
    """
    restic ls outputs lines of
    {"name": "b458b848.2024-04-28-13h07.gz", "type": "file", "path": "/path/b458b848.2024-04-28-13h07.gz", "uid": 0, "gid": 0, "size": 82638431, "mode": 438, "permissions": "-rw-rw-rw-", "mtime": "2024-04-29T10:32:18+02:00", "atime": "2024-04-29T10:32:18+02:00", "ctime": "2024-04-29T10:32:18+02:00", "message_type": "node", "struct_type": "node"}
    # In order to save some memory in GUI, let's drop unused data
    """

    # name: str  # We don't need name, we have path from which we extract name, which is more memory efficient
    type: LsNodeType
    path: str
    mtime: datetime
    size: Optional[int] = None
