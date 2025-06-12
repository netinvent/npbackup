#! /usr/bin/env python3
#  -*- coding: utf-8 -*-


__intname__ = "npbackup_cli_tests"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2024121001"


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
import requests
import tempfile
import bz2
from pprint import pprint

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from npbackup import __main__
from npbackup.path_helper import BASEDIR
from npbackup.configuration import load_config, get_repo_config
from RESTIC_SOURCE_FILES.update_restic import download_restic_binaries_for_arch


if os.name == "nt":
    ORIGINAL_CONF_FILE = "npbackup-cli-test-windows.yaml"
else:
    ORIGINAL_CONF_FILE = "npbackup-cli-test-linux.yaml"

ORIGINAL_CONF_FILE_PATH = (
    Path(BASEDIR).absolute().parent.joinpath("tests").joinpath(ORIGINAL_CONF_FILE)
)
CONF_FILE = Path(tempfile.gettempdir()).absolute().joinpath(ORIGINAL_CONF_FILE)
# Now that we got the path to the config file, we need to replace repo_uri with a temporary directory
# Danger: THIS WILL NEED SOME ADJUSTMENT FOR multi repo tests

temp_repo_dir = Path(tempfile.mkdtemp(prefix="npbackup_test_repo_"))
restore_dir = Path(tempfile.mkdtemp(prefix="npbackup_test_restore_"))

raw_config = ORIGINAL_CONF_FILE_PATH.read_text().replace(
    "repo_uri: ./test", f"repo_uri: {temp_repo_dir}"
)
CONF_FILE.write_text(raw_config)

full_config = load_config(CONF_FILE)
repo_config, _ = get_repo_config(full_config)


# File we will request in dump mode
DUMP_FILE = "__version__.py"


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


def test_download_restic_binaries():
    """
    We must first download latest restic binaries to make sure we can run all tests
    Currently we only run these on amd64
    """
    assert download_restic_binaries_for_arch(), "Could not download restic binaries"


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
        assert (
            "Config file npbackup-non-existent.conf cannot be read or does not exist"
            in str(logs)
        ), "There should be a critical error when config file is not given"


def test_npbackup_cli_show_config():
    sys.argv = ["", "-c", str(CONF_FILE), "--show-config"]
    try:
        with RedirectedStdout() as logs:
            __main__.main()
    except SystemExit:
        print(str(logs))
        assert "__(o_O)__" in str(logs), "Obfuscation does not work"


def test_npbackup_cli_init():
    shutil.rmtree(repo_config.g("repo_uri"), ignore_errors=True)
    sys.argv = ["", "-c", str(CONF_FILE), "--init"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(str(logs))
        assert "created restic repository" in str(logs), "Did not create repo"
        assert "Repo initialized successfully" in str(logs), "Repo init failed"


def test_npbackup_cli_has_no_recent_snapshots():
    """
    After init, we should not have recent snapshots
    """
    sys.argv = ["", "-c", str(CONF_FILE), "--has-recent-snapshot", "--json"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(str(logs))
        json_logs = json.loads(str(logs))
        assert json_logs["result"] == False, "Should not have recent snapshots"


def test_npbackup_cli_create_backup():
    # Let's remove the repo before creating a backup since backup should auto init the repo
    shutil.rmtree(repo_config.g("repo_uri"), ignore_errors=True)
    sys.argv = ["", "-c", str(CONF_FILE), "-b"]

    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(str(logs))
        assert "Backend finished with success" in str(logs), "Backup failed"


def test_npbackup_cli_has_recent_snapshots():
    """
    After backup, we should have recent snapshots
    """
    sys.argv = ["", "-c", str(CONF_FILE), "--has-recent-snapshot", "--json"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(str(logs))
        json_logs = json.loads(str(logs))
        assert json_logs["result"], "Should  have recent snapshots"


def test_npbackup_cli_unlock():
    sys.argv = ["", "-c", str(CONF_FILE), "--unlock"]

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
    sys.argv = ["", "-c", str(CONF_FILE), "-r", str(restore_dir)]
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
            f"{restore_dir}/npbackup/npbackup/__version__.py"
        ).is_file(), "Restored snapshot does not contain our data"


def test_npbackup_cli_ls():
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


def test_npbackup_cli_list_snapshots():
    sys.argv = ["", "-c", str(CONF_FILE), "--list", "snapshots", "--json"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        json_logs = json.loads(str(logs))
        assert json_logs["result"], "Bad list result"
        assert json_logs["operation"] == "list", "Bogus operation name for list"
        assert len(json_logs["output"]["data"]) == 64, "No snapshot data found"


def test_npbackup_cli_find():
    sys.argv = ["", "-c", str(CONF_FILE), "--find", "__version__.py"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        assert "Found matching entries in snapshot" in str(
            logs
        ), "Did not find match for find"
        assert "__version__.py", "Did not find __version__.py in find"


def test_npbackup_cli_check_quick():
    sys.argv = ["", "-c", str(CONF_FILE), "--check", "quick"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        assert "Running metadata consistency check of repository" in str(
            logs
        ), "Failed quick checking repo"
        print(logs)
        assert "Repo checked successfully" in str(logs), "Quick check failed"


def test_npbackup_cli_check_full():
    sys.argv = ["", "-c", str(CONF_FILE), "--check", "full"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        assert "Running full data check of repository" in str(
            logs
        ), "Failed full checking repo"
        print(logs)
        assert "Repo checked successfully" in str(logs), "Full check failed"


def test_npbackup_cli_repair_index():
    sys.argv = ["", "-c", str(CONF_FILE), "--repair", "index"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        assert "Repairing index in repo" in str(logs), "Index repair failed"
        print(logs)
        assert "Repo successfully repaired:" in str(logs), "Missing repair info"


def test_npbackup_cli_repair_snapshots():
    sys.argv = ["", "-c", str(CONF_FILE), "--repair", "snapshots"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        assert "Repairing snapshots in repo" in str(logs), "Snapshot repair failed"
        print(logs)
        assert "Repo successfully repaired:" in str(logs), "Missing repair info"


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


def test_npbackup_cli_forget():
    sys.argv = ["", "-c", str(CONF_FILE), "--forget", "latest"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        assert "Forgetting snapshots ['latest']" in str(
            logs
        ), "Could not forget snapshot"
        assert "removed snapshot/" in str(logs), "Did not forget snapshot"
        assert "Successfully forgot snapshot" in str(logs), "Forget failed"


def test_npbackup_cli_recover():
    sys.argv = ["", "-c", str(CONF_FILE), "--recover"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        assert "Recovering snapshots in repo default" in str(
            logs
        ), "Could not recover snapshots"
        assert "found 1 unreferenced roots" in str(logs), "Should have found 1 snapshot"
        assert "Recovery finished" in str(logs), "Recovery failed"


def test_npbackup_cli_prune():
    sys.argv = ["", "-c", str(CONF_FILE), "--prune"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        assert "Pruning snapshots for repo" in str(logs), "Could not prune repo"
        assert "unused size after prune" in str(logs), "Did not prune"
        assert "Successfully pruned repository" in str(logs), "Prune failed"


def test_npbackup_cli_housekeeping():
    sys.argv = ["", "-c", str(CONF_FILE), "--housekeeping", "--json"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        json_logs = json.loads(str(logs))
        assert json_logs["result"], "Bad housekeeping result"
        assert (
            json_logs["operation"] == "housekeeping"
        ), "Bogus operation name for housekeeping"
        assert json_logs["detail"]["unlock"]["result"], "Unlock failed in housekeeping"
        assert json_logs["detail"]["check"]["result"], "check failed in housekeeping"
        assert json_logs["detail"]["forget"]["result"], "forget failed in housekeeping"
        assert (
            len(json_logs["detail"]["forget"]["args"]["policy"]) > 4
        ), "policy missing in housekeeping"
        assert json_logs["detail"]["prune"]["result"], "prune failed in housekeeping"


def test_npbackup_cli_raw():
    global DUMP_FILE

    sys.argv = ["", "-c", str(CONF_FILE), "--raw", "ls latest"]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print(logs)
        assert "Running raw command" in str(logs), "Did not run raw command"
        assert "Successfully run raw command" in str(logs), "Did not run raw command"
        assert DUMP_FILE in str(logs), "raw ls output should contain DUMP_FILE name"
        for line in str(logs).split("\n"):
            if DUMP_FILE in line:
                DUMP_FILE = line
                print("FOUND DUMP FILE", DUMP_FILE)
                break


def test_npbackup_cli_dump():
    sys.argv = ["", "-c", str(CONF_FILE), "--dump", DUMP_FILE]
    try:
        with RedirectedStdout() as logs:
            e = __main__.main()
            print(e)
    except SystemExit:
        print("DUMPED FILE", DUMP_FILE)
        print(logs)
        assert '__intname__ = "npbackup"' in str(logs), "version file seems bogus"
        assert '"pv": sys.version_info,' in str(logs), "Version file still seems bogus"


if __name__ == "__main__":
    test_download_restic_binaries()
    test_npbackup_cli_no_config()
    test_npbackup_cli_wrong_config_path()
    test_npbackup_cli_show_config()

    test_npbackup_cli_init()
    test_npbackup_cli_has_no_recent_snapshots()

    # Backup process
    test_npbackup_cli_create_backup()
    test_npbackup_cli_has_recent_snapshots()
    test_npbackup_cli_unlock()
    test_npbackup_cli_snapshots()
    test_npbackup_cli_restore()
    test_npbackup_cli_list_snapshots()
    # This one should is pretty hard to test without having repo with multiple different date snapshots
    # We need to create a "fake" repo starting in let's say 2020 and put our date back to 2023 to test our standard
    # policy
    # We can also have a forget test which should fail because of bogus permissions
    test_npbackup_cli_retention()
    test_npbackup_cli_forget()
    test_npbackup_cli_recover()
    test_npbackup_cli_prune()

    # basic tests for all other commands
    test_npbackup_cli_ls()
    test_npbackup_cli_find()
    test_npbackup_cli_check_quick()
    test_npbackup_cli_check_full()
    test_npbackup_cli_repair_index()
    test_npbackup_cli_repair_snapshots()

    # Repairing packs needs pack ids
    # test_npbackup_cli_repair_packs()

    test_npbackup_cli_housekeeping()

    test_npbackup_cli_raw()
    test_npbackup_cli_dump()
