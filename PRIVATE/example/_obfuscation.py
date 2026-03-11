#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.obfuscation"


# NPF-SEC-00011: Default AES key obfuscation

# You can replace the obfuscation function with your own implementation,
# as long as it is symmetric (i.e. applying it twice returns the original value).
# You may also kust change the default keywoard

KEYWORD = b"/*YOUR FAVORITE STRING*/"


def obfuscation(key: bytes) -> bytes:
    """
    Symmetric obfuscation of bytes
    """
    if key:
        key_length = len(KEYWORD)
        return bytes(c ^ KEYWORD[i % key_length] for i, c in enumerate(key))
    return key
