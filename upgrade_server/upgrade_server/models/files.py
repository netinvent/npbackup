#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_server.models.files"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "202303101"


from enum import Enum
from pydantic import BaseModel, constr


class Platform(Enum):
    windows = "windows"
    linux = "Linux"


class Arch(Enum):
    x86 = "x86"
    x64 = "x64"


class FileBase(BaseModel):
    arch: Arch
    platform: Platform


class FileGet(FileBase):
    pass


class FileSend(FileBase):
    sha256sum: constr(min_length=64, max_length=64)
    filename: str
    file_length: int
