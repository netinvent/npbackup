#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.helpers"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023083101"


from typing import Tuple
import re


def get_anon_repo_uri(repository: str) -> Tuple[str, str]:
    """
    Remove user / password part from repository uri
    """
    backend_type = repository.split(":")[0].upper()
    if backend_type.upper() in ["REST", "SFTP"]:
        res = re.match(
            r"(sftp|rest)(.*:\/\/)(.*):?(.*)@(.*)", repository, re.IGNORECASE
        )
        if res:
            backend_uri = res.group(1) + res.group(2) + res.group(5)
        else:
            backend_uri = repository
    elif backend_type.upper() in [
        "S3",
        "B2",
        "SWIFT",
        "AZURE",
        "GS",
        "RCLONE",
    ]:
        backend_uri = repository
    else:
        backend_type = "LOCAL"
        backend_uri = repository
    return backend_type, backend_uri
