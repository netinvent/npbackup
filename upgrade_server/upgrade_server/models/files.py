#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_server.models.files"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025011601"


from typing import Optional
from enum import Enum
from pydantic import BaseModel, constr


class Platform(Enum):
    windows = "windows"
    linux = "linux"


class Arch(Enum):
    x86 = "x86"
    x64 = "x64"


class BuildType(Enum):
    gui = "gui"
    cli = "cli"


class Audience(Enum):
    public = "public"
    private = "private"


class ClientTargetIdentification(BaseModel):
    arch: Arch
    platform: Platform
    build_type: BuildType
    audience: Audience
    auto_upgrade_host_identity: Optional[str] = None
    installed_version: Optional[str] = None
    group: Optional[str] = None


class FileGet(ClientTargetIdentification):
    pass


class FileSend(ClientTargetIdentification):
    sha256sum: constr(min_length=64, max_length=64)
    filename: str
    file_length: int
