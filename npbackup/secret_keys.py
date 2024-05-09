#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.secret_keys"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024050901"


# Encryption key to keep repo settings safe in plain text yaml config file

# This is the default key that comes with NPBackup.. You should change it (and keep a backup copy in case you need to decrypt a config file data)
# You can overwrite this by copying this file to `../PRIVATE/_private_secret_keys.py` and generating a new key
# Obtain a new key with:
# npbackup-cli --create-key keyfile.key

AES_KEY = b"\xc3T\xdci\xe3[s\x87o\x96\x8f\xe5\xee.>\xf1,\x94\x8d\xfe\x0f\xea\x11\x05 \xa0\xe9S\xcf\x82\xad|"

"""
If someday we need to change the AES_KEY, copy it's content to EARLIER_AES_KEY and generate a new one
Keeping EARLIER_AES_KEY allows to migrate from old configuration files to new ones
"""
EARLIER_AES_KEY = b"\x9e\xbck\xe4\xc5nkT\x1e\xbf\xb5o\x06\xd3\xc6(\x0e:'i\x1bT\xb3\xf0\x1aC e\x9bd\xa5\xc6"
