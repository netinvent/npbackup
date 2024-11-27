#! /usr/bin/env python3
#  -*- coding: utf-8 -*-


__intname__ = "npbackup_cli_tests"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2024112701"
__compat__ = "python3.6+"


"""
Simple test where we launch the CLI and hope it doesn't die
Should be improved with much stronger tests
Missing:
- VSS test
- backup minimum size tests
- proper retention policy tests
"""

import sys
import os
from pathlib import Path
import shutil
from io import StringIO
import json

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from npbackup import __main__
from npbackup.path_helper import CURRENT_DIR, CURRENT_EXECUTABLE
from npbackup.configuration import load_config, get_repo_config

if os.name == "nt":
    CONF_FILE = "npbackup-cli-test-windows.yaml"
else:
    CONF_FILE = "npbackup-cli-test-linux.yaml"

CONF_FILE = Path(CURRENT_DIR).absolute().joinpath(CONF_FILE)
full_config = load_config(CONF_FILE)
repo_config, _ = get_repo_config(full_config)


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
    sys.argv = [""]  # Make sure we don't get any pytest args
    try:
        with RedirectedStdout() as logs:
            __main__.main()
    except SystemExit:
        print(str(logs))
        assert "CRITICAL :: Cannot run without configuration file" in str(
            logs
        ), "There should be a critical error when config file is not given"


def test_npbackup_cli_wrong_config_path():
    sys.argv = ["", "-c", "npbackup-non-existent.conf"]
    try:
        with RedirectedStdout() as logs:
            __main__.main()
    except SystemExit:
        print(str(logs))
        assert "Config file npbackup-non-existent.conf cannot be read" in str(
            logs
        ), "There should be a critical error when config file is not given"


def test_npbackup_cli_show_config():
    sys.argv = ["", "-c", str(CONF_FILE), "--show-config"]
    try:
        with RedirectedStdout() as logs:
            __main__.main()
    except SystemExit:
        print(str(logs))
        assert "__(o_O)__" in str(logs), "Obfuscation does not work"


def test_npbackup_cli_create_backup():
    sys.argv = ["", "-c", str(CONF_FILE), "-b"]
    # Make sure there is no existing repository

    repo_uri = Path(repo_config.g("repo_uri"))
    if repo_uri.is_dir():
        shutil.rmtree(repo_uri)
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(str(logs))


def test_npbackup_cli_unlock():
    sys.argv = ["", "-c", str(CONF_FILE), "--unlock"]
    # Make sure there is no existing repository
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(str(logs))
        assert "Repo successfully unlocked" in str(logs), "Could not unlock repo"


def test_npbackup_cli_snapshots():
    sys.argv = ["", "-c", str(CONF_FILE), "--snapshots", "--json"]
    try:
        with RedirectedStdout() as logs:
            __main__.main()
    except SystemExit:
        print(str(logs))
        json_logs = json.loads(str(logs))
        assert json_logs["result"], "Bad snapshot result"
        assert (
            json_logs["operation"] == "snapshots"
        ), "Bogus operation name for snapshots"
        assert len(json_logs["output"]) == 1, "More than one snapshot present"


def test_npbackup_cli_restore():
    sys.argv = ["", "-c", str(CONF_FILE), "-r", "./restored"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(str(logs))
        assert "Successfully restored data" in str(
            logs
        ), "Logs don't show successful restore"
        assert Path(
            "./restored/npbackup/npbackup/__version__.py"
        ).is_file(), "Restored snapshot does not contain our data"


def test_npbackup_cli_list():
    sys.argv = ["", "-c", str(CONF_FILE), "--ls", "latest", "--json"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        json_logs = json.loads(str(logs))
        assert json_logs["result"], "Bad ls result"
        assert json_logs["operation"] == "ls", "Bogus operation name for ls"
        assert "/npbackup/npbackup/gui/__main__.py" in str(
            logs
        ), "Missing main gui in list"


def test_npbackup_cli_retention():
    sys.argv = ["", "-c", str(CONF_FILE), "--policy"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        assert "Successfully applied retention policy" in str(
            logs
        ), "Failed applying retention policy"


if __name__ == "__main__":
    test_npbackup_cli_no_config()
    test_npbackup_cli_wrong_config_path()
    test_npbackup_cli_show_config()
    test_npbackup_cli_create_backup()
    test_npbackup_cli_unlock()
    test_npbackup_cli_snapshots()
    test_npbackup_cli_restore()
    test_npbackup_cli_list()
    # This one should is pretty hard to test without having repo with multiple different date snapshots
    # We need to create a "fake" repo starting in let's say 2020 and put our date back to 2023 to test our standard
    # policy
    # We can also have a forget test which should fail because of bogus permissions
    test_npbackup_cli_retention()
