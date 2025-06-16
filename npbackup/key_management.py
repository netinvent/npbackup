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
from npbackup.obfuscation import obfuscation

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))


logger = getLogger()


# Try to import a private key, if not available, fallback to the default key
try:
    from PRIVATE._private_secret_keys import AES_KEY
    from PRIVATE._obfuscation import obfuscation

    AES_KEY = obfuscation(AES_KEY)
    IS_PRIV_BUILD = True
    try:
        from PRIVATE._private_secret_keys import EARLIER_AES_KEY

        EARLIER_AES_KEY = obfuscation(EARLIER_AES_KEY)
    except ImportError:
        EARLIER_AES_KEY = None
except ImportError:
    # If no private keys are used, then let's use the public ones
    try:
        from npbackup.secret_keys import AES_KEY
        from npbackup.obfuscation import obfuscation

        AES_KEY = obfuscation(AES_KEY)
        IS_PRIV_BUILD = False
        try:
            from npbackup.secret_keys import EARLIER_AES_KEY
        except ImportError:
            EARLIER_AES_KEY = None
    except ImportError:
        print("No secret_keys file. Please read documentation.")
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
                msg = f"Encryption key read from command"
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
