#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.get_key"


import os
from logging import getLogger
from command_runner import command_runner
from cryptidy.symmetric_encryption import generate_key
from npbackup.obfuscation import obfuscation


logger = getLogger()


def get_aes_key():
    """
    Get encryption key from environment variable or file
    """
    key = None

    key_location = os.environ.get("NPBACKUP_KEY_LOCATION", None)
    if key_location and os.path.isfile(key_location):
        try:
            with open(key_location, "rb") as key_file:
                key = key_file.read()
        except OSError as exc:
            msg = f"Cannot read encryption key file: {exc}"
            return False, msg
    else:
        key_command = os.environ.get("NPBACKUP_KEY_COMMAND", None)
        if key_command:
            exit_code, output = command_runner(key_command, encoding=False, shell=True)
            if exit_code != 0:
                msg = f"Cannot run encryption key command: {output}"
                return False, msg
            key = bytes(output)
    return obfuscation(key)


def create_key_file(key_location: str):
    try:
        with open(key_location, "wb") as key_file:
            key_file.write(obfuscation(generate_key()))
            logger.info(f"Encryption key file created at {key_location}")
            return True
    except OSError as exc:
        logger.critical(f"Cannot create encryption key file: {exc}")
        return False
