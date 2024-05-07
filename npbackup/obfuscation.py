#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.obfuscation"


# NPF-SEC-00011: Default AES key obfuscation


def obfuscation(key: bytes) -> bytes:
    """
    Symmetric obfuscation of bytes
    """
    if key:
        keyword = b"/*NPBackup 2024*/"
        key_length = len(keyword)
        return bytes(c ^ keyword[i % key_length] for i, c in enumerate(key))
    return key
