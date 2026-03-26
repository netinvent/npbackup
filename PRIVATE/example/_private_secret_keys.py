#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.secret_keys"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026031201"


# Encryption key to keep repo settings safe in plain text yaml config file

# This is the default key that comes with NPBackup.. You should change it (and keep a backup copy in case you need to decrypt a config file data)
# You can overwrite this by copying this file to `../PRIVATE/_private_secret_keys.py` and generating a new key
# Obtain a new key with:
# python3 -c "from cryptidy import symmetric_encryption as s; print(s.generate_key())"
# You may also create a new keyfile via
# npbackup-cli --create-key keyfile.key
# Given keyfile can then be loaded via environment variables, see documentation for more

# KEY DATE: 2026-03-12
AES_KEY = b"\xd7\x84\xe5\xa9\x82\x8aU\x9b\xf2+\xf9\xf6\x95\xe9\x02\xbf\xce\xb3\xf9\x06\xdc0s\xa6;9\xa9}K:\xc13"

"""
If someday we need to change the AES_KEY, copy it's content to EARLIER_AES_KEYS and generate a new one
Keeping EARLIER_AES_KEYS allows to migrate from old configuration files to new ones
This is also useful if you want to migrate from public audience to a private one
"""
EARLIER_AES_KEYS = [
]

"""
Public AES Keys can be used to migrate public audience configuration files to private audience ones.
If you have a public audience and want to migrate to a private one,
add your public audience AES key here, so that it can be used to decrypt existing configuration files.
"""
PUBLIC_AES_KEYS = []