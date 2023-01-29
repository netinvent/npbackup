#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.secret_keys"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2022120401"


# Encryption key to keep repo settings safe in plain text yaml config file

# This is the default key that comes with NPBackup.. You should change it (and keep a backup copy in case you need to decrypt a config file data)
# You can overwrite this by copying this file to `_private_secret_keys.py` and generating a new key
# Obtain a new key with:
# from cryptidy.symmetric_encryption import generate_key
# print(generate_key(32))

AES_KEY = b"\x9e\xbck\xe4\xc5nkT\x1e\xbf\xb5o\x06\xd3\xc6(\x0e:'i\x1bT\xb3\xf0\x1aC e\x9bd\xa5\xc6"
ADMIN_PASSWORD = "NPBackup_00"
