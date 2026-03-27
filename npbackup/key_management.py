#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.key_management"


import sys
import os
from logging import getLogger
from command_runner import command_runner
from cryptidy.symmetric_encryption import generate_key
from resources.audience import CURRENT_AUDIENCE

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))


logger = getLogger()

if CURRENT_AUDIENCE == "public":
    # pylint: disable=W0404 (reimported)
    from npbackup.secret_keys import AES_KEY
    from npbackup.obfuscation import obfuscation

    # When running as public, we don't need pubkeys for migration
    PUBLIC_AES_KEYS_FOR_PRIVATE_MIGRATION = None
    public_obfuscation = obfuscation
    try:
        from npbackup.secret_keys import EARLIER_AES_KEYS
    except ImportError:
        EARLIER_AES_KEYS = None
else:
    try:
        from PRIVATE.secret_keys import AES_KEY
        from PRIVATE.obfuscation import obfuscation

        try:
            from PRIVATE.secret_keys import EARLIER_AES_KEYS
        except ImportError:
            EARLIER_AES_KEYS = None
        try:
            from PRIVATE.secret_keys import PUBLIC_AES_KEYS_FOR_PRIVATE_MIGRATION
            from npbackup.obfuscation import obfuscation as public_obfuscation
        except ImportError:
            PUBLIC_AES_KEYS_FOR_PRIVATE_MIGRATION = None

            def public_obfuscation(key):
                logger.info("No public audience key function found")
                return key

    except ImportError as exc:
        print(f"{__file__}: No private audience customization found")
        print(exc)
        sys.exit(1)


if not AES_KEY:
    print(
        f"{__file__}: No AES_KEY found in secret_keys file. Please read documentation."
    )
    sys.exit(1)


def get_aes_key():
    """
    Get encryption key from environment variable or file
    """
    key = None

    try:
        key_location = os.environ.get("NPBACKUP_KEY_LOCATION", None)
        if key_location and os.path.isfile(key_location):
            try:
                with open(key_location, "rb") as key_file:
                    key = key_file.read()
                    msg = "Encryption key file read"
            except OSError as exc:
                msg = f"Cannot read encryption key file: {exc}"
                return False, msg
        else:
            key_command = os.environ.get("NPBACKUP_KEY_COMMAND", None)
            if key_command:
                exit_code, output = command_runner(
                    key_command, encoding=False, shell=True
                )
                if exit_code != 0:
                    msg = f"Cannot run encryption key command: {output}"
                    return False, msg
                key = bytes(output)
                msg = "Encryption key read from command"
    except Exception as exc:
        msg = f"Error reading encryption key: {exc}"
        return False, msg
    if key:
        return obfuscation(key), msg
    return None, ""


def create_key_file(key_location: str):
    try:
        with open(key_location, "wb") as key_file:
            key_file.write(obfuscation(generate_key()))
            logger.info(f"Encryption key file created at {key_location}")
            return True
    except OSError as exc:
        logger.critical(f"Cannot create encryption key file: {exc}")
        return False
