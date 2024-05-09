#! /usr/bin/env python3
#  -*- coding: utf-8 -*-


__intname__ = "npbackup_cli_tests"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2024042301"
__compat__ = "python3.6+"


"""
Simple test where we launch the GUI and hope it doesn't die
"""

import sys
import os
from io import StringIO
from npbackup import __main__
from npbackup.path_helper import CURRENT_DIR, CURRENT_EXECUTABLE


if os.name == 'nt':
    CONF_FILE = "npbackup-cli-test-windows.yaml"
else:
    CONF_FILE = "npbackup-cli-test-windows.yaml"
CONF_FILE = os.path.join(CURRENT_DIR, CONF_FILE)


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


def test_npbackup_cli_show_config():
    sys.argv = ['', '-c', CONF_FILE, '--show-config']
    try:
        with RedirectedStdout() as logs:
            __main__.main()
    except SystemExit:
        print(str(logs))
        assert "__(o_O)__" not in str(logs), "Obfuscation does not work"
    

def _no_test_npbackup_cli_create_backup():
    sys.argv = ['', '-c' './npbackup-cli-test.conf', '-b']
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)


def _no_test_npbackup_cli_snapshots():
    sys.argv = ['', '-c', 'npbackup-test.conf', '--snapshots']
    try:
        with RedirectedStdout() as logs:
            __main__.main()
    except SystemExit:
        print(logs)


def _no_test_npbackup_cli_restore():
    sys.argv = ['', '-c' './npbackup-cli-test.conf', '-r', './restored']
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)


def _no_test_npbackup_cli_list():
    sys.argv = ['', '-c' './npbackup-cli-test.conf', '--ls snapshots']
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)


if __name__ == "__main__":
    test_npbackup_cli_no_config()
    test_npbackup_cli_wrong_config_path()
    test_npbackup_cli_show_config()
    # TODO
    #test_npbackup_cli_create_backup()
    #test_npbackup_cli_snapshots()
    #test_npbackup_cli_restore()
    #test_npbackup_cli_list()
    # This one should is pretty hard to test without having repo with multiple different date snapshots
    # We need to create a "fake" repo starting in let's say 2020 and put our date back to 2023 to test our standard
    # policy
    # We can also have a forget test which should fail because of bogus permissions
    #test_npbackup_cli_forget()