#! /usr/bin/env python3
#  -*- coding: utf-8 -*-


__intname__ = "npbackup_cli_tests"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__licence__ = "BSD-3-Clause"
__build__ = "2024011501"
__compat__ = "python3.6+"


"""
Simple test where we launch the GUI and hope it doesn't die
"""

import sys
from io import StringIO
from npbackup import __main__


class RedirectedStdout:
    """
    Balantly copied from https://stackoverflow.com/a/45899925/2635443
    """
    def __init__(self):
        self._stdout = None
        self._string_io = None

    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._string_io = StringIO()
        return self

    def __exit__(self, type, value, traceback):
        sys.stdout = self._stdout

    def __str__(self):
        return self._string_io.getvalue()


def test_npbackup_cli_no_config():
    sys.argv = ['']  # Make sure we don't get any pytest args
    try:
        with RedirectedStdout() as logs:
            __main__.main()
    except SystemExit:
        assert 'CRITICAL :: Cannot run without configuration file' in str(logs), "There should be a critical error when config file is not given"


def test_npbackup_cli_wrong_config_path():
    sys.argv = ['', '-c', 'npbackup-non-existent.conf']
    try:
        with RedirectedStdout() as logs:
            __main__.main()
    except SystemExit:
        assert 'Config file npbackup-non-existent.conf cannot be read' in str(logs), "There should be a critical error when config file is not given"


def test_npbackup_cli_snapshots():
    sys.argv = ['', '-c', 'npbackup-test.conf', '--snapshots']
    try:
        with RedirectedStdout() as logs:
            __main__.main()
    except SystemExit:
        print(logs)



if __name__ == "__main__":
    test_npbackup_cli_no_config()
    test_npbackup_cli_wrong_config_path()
    test_npbackup_cli_snapshots()