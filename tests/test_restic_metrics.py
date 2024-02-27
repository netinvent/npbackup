#! /usr/bin/env python3
#  -*- coding: utf-8 -*-


__intname__ = "restic_metrics_tests"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2024010101"
__description__ = "Converts restic command line output to a text file node_exporter can scrape"
__compat__ = "python3.6+"

import sys
import os
from pathlib import Path
import shutil
import re
import json
import tempfile
from ofunctions.platform import os_arch
from command_runner import command_runner
try:
    from npbackup.restic_metrics import *
except ImportError:  # would be ModuleNotFoundError in Python 3+
    # In case we run tests without actually having installed command_runner
    sys.path.insert(0, os.path.abspath(os.path.join(__file__, os.pardir, os.pardir)))
    from npbackup.restic_metrics import *
from npbackup.core.restic_source_binary import get_restic_internal_binary

restic_json_outputs = {}
restic_json_outputs["v0.16.2"] = \
"""{"message_type":"summary","files_new":5,"files_changed":15,"files_unmodified":6058,"dirs_new":0,"dirs_changed":27,"dirs_unmodified":866,"data_blobs":17,"tree_blobs":28,"data_added":281097,"total_files_processed":6078,"total_bytes_processed":122342158,"total_duration":1.2836983,"snapshot_id":"360333437921660a5228a9c1b65a2d97381f0bc135499c6e851acb0ab84b0b0a"}
"""

restic_str_outputs = {}
# log file from restic v0.16.2
restic_str_outputs["v0.16.2"] = \
"""repository 962d5924 opened (version 2, compression level auto)
using parent snapshot 325a2fa1
[0:00] 100.00%  4 / 4 index files loaded

Files:         216 new,    21 changed,  5836 unmodified
Dirs:           29 new,    47 changed,   817 unmodified
Added to the repository: 4.425 MiB (1.431 MiB stored)

processed 6073 files, 116.657 MiB in 0:03
snapshot b28b0901 saved
"""

    # log file from restic v0.14.0
restic_str_outputs["v0.14.0"] = \
"""using parent snapshot df60db01

Files:        1584 new,   269 changed, 235933 unmodified
Dirs:          258 new,   714 changed, 37066 unmodified
Added to the repo: 493.649 MiB

processed 237786 files, 85.487 GiB in 11:12"
"""

    # log file form restic v0.9.4
restic_str_outputs["v0.9.4"] = \
"""
Files:           9 new,    32 changed, 110340 unmodified
Dirs:            0 new,     2 changed,     0 unmodified
Added to the repo: 196.568 MiB
processed 110381 files, 107.331 GiB in 0:36
"""

# restic_metrics_v1 prometheus output
expected_results_V1 = [
    r'restic_repo_files{instance="test",backup_job="some_nas",state="new"} (\d+)',
    r'restic_repo_files{instance="test",backup_job="some_nas",state="changed"} (\d+)',
    r'restic_repo_files{instance="test",backup_job="some_nas",state="unmodified"} (\d+)',
    r'restic_repo_dirs{instance="test",backup_job="some_nas",state="new"} (\d+)',
    r'restic_repo_dirs{instance="test",backup_job="some_nas",state="changed"} (\d+)',
    r'restic_repo_dirs{instance="test",backup_job="some_nas",state="unmodified"} (\d+)',
    r'restic_repo_files{instance="test",backup_job="some_nas",state="total"} (\d+)',
    r'restic_repo_size_bytes{instance="test",backup_job="some_nas",state="total"} (\d+)',
    r'restic_backup_duration_seconds{instance="test",backup_job="some_nas",action="backup"} (\d+)',
]

# restic_metrics_v2 prometheus output
expected_results_V2 = [
    r'restic_files{instance="test",backup_job="some_nas",state="new",action="backup"} (\d+)',
    r'restic_files{instance="test",backup_job="some_nas",state="changed",action="backup"} (\d+)',
    r'restic_files{instance="test",backup_job="some_nas",state="unmodified",action="backup"} (\d+)',
    r'restic_dirs{instance="test",backup_job="some_nas",state="new",action="backup"} (\d+)',
    r'restic_dirs{instance="test",backup_job="some_nas",state="changed",action="backup"} (\d+)',
    r'restic_dirs{instance="test",backup_job="some_nas",state="unmodified",action="backup"} (\d+)',
    r'restic_files{instance="test",backup_job="some_nas",state="total",action="backup"} (\d+)',
    r'restic_snasphot_size_bytes{instance="test",backup_job="some_nas",action="backup",type="processed"} (\d+)',
    r'restic_total_duration_seconds{instance="test",backup_job="some_nas",action="backup"} (\d+)',
]


def running_on_github_actions():
    """
    This is set in github actions workflow with
          env:
        RUNNING_ON_GITHUB_ACTIONS: true
    """
    return os.environ.get("RUNNING_ON_GITHUB_ACTIONS", "False").lower() == "true"


def test_restic_str_output_2_metrics():
    instance = "test"
    backup_job = "some_nas"
    labels = "instance=\"{}\",backup_job=\"{}\"".format(instance, backup_job)
    for version, output in restic_str_outputs.items():
        print(f"Testing V1 parser restic str output from version {version}")
        errors, prom_metrics = restic_output_2_metrics(True, output, labels)
        assert errors is False
        #print(f"Parsed result:\n{prom_metrics}")
        for expected_result in expected_results_V1:
            match_found = False
            #print("Searching for {}".format(expected_result))
            for metric in prom_metrics:
                result = re.match(expected_result, metric)
                if result:
                    match_found = True
                    break
            assert match_found is True, 'No match found for {}'.format(expected_result)


def test_restic_str_output_to_json():
    labels = {
        "instance": "test",
        "backup_job": "some_nas"
    }
    for version, output in restic_str_outputs.items():
        print(f"Testing V2 parser restic str output from version {version}")
        json_metrics = restic_str_output_to_json(True, output)
        assert json_metrics["errors"] == False
        #print(json_metrics)
        _, prom_metrics, _ = restic_json_to_prometheus(True, json_metrics, labels)

        #print(f"Parsed result:\n{prom_metrics}")
        for expected_result in expected_results_V2:
            match_found = False
            #print("Searching for {}".format(expected_result))
            for metric in prom_metrics:
                result = re.match(expected_result, metric)
                if result:
                    match_found = True
                    break
            assert match_found is True, 'No match found for {}'.format(expected_result)


def test_restic_json_output():
    labels = {
        "instance": "test",
        "backup_job": "some_nas"
    }
    for version, json_output in restic_json_outputs.items():
        print(f"Testing V2 direct restic --json output from version {version}")
        restic_json = json.loads(json_output)
        _, prom_metrics, _ = restic_json_to_prometheus(True, restic_json, labels)
        #print(f"Parsed result:\n{prom_metrics}")
        for expected_result in expected_results_V2:
            match_found = False
            #print("Searching for {}".format(expected_result))
            for metric in prom_metrics:
                result = re.match(expected_result, metric)
                if result:
                    match_found = True
                    break
            assert match_found is True, 'No match found for {}'.format(expected_result)


def test_real_restic_output():
    # Don't do the real tests on github actions, since we don't have 
    # the binaries there.
    # TODO: Add download/unzip restic binaries so we can run these tests
    if running_on_github_actions():
        return
    labels = {
        "instance": "test",
        "backup_job": "some_nas"
    }
    restic_binary = get_restic_internal_binary(os_arch())
    print(f"Testing real restic output, Running with restic {restic_binary}")
    assert restic_binary is not None, "No restic binary found"

    for api_arg in ['', ' --json']:

        # Setup repo and run a quick backup
        repo_path = Path(tempfile.gettempdir()) / "repo"
        if repo_path.is_dir():
            shutil.rmtree(repo_path)
            repo_path.mkdir()

        os.environ["RESTIC_REPOSITORY"] = str(repo_path)
        os.environ["RESTIC_PASSWORD"] = "TEST"


        exit_code, output = command_runner(f"{restic_binary} init --repository-version 2", live_output=True)
        # Just backend current directory
        cmd = f"{restic_binary} backup {api_arg} ."
        exit_code, output = command_runner(cmd, timeout=120, live_output=True)
        assert exit_code == 0, "Failed to run restic"
        if not api_arg:
            restic_json = restic_str_output_to_json(True, output)
        else:
            restic_json = output
        _, prom_metrics, _ = restic_json_to_prometheus(True, restic_json, labels)
        #print(f"Parsed result:\n{prom_metrics}")
        for expected_result in expected_results_V2:
            match_found = False
            print("Searching for {}".format(expected_result))
            for metric in prom_metrics:
                result = re.match(expected_result, metric)
                if result:
                    match_found = True
                    break
            assert match_found is True, 'No match found for {}'.format(expected_result)
        

if __name__ == "__main__":
    test_restic_str_output_2_metrics()
    test_restic_str_output_to_json()
    test_restic_json_output()
    test_real_restic_output()