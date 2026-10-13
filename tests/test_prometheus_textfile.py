#! /usr/bin/env python3
#  -*- coding: utf-8 -*-

__intname__ = "npbackup_prometheus_textfile_tests"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2026 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2026101201"


"""
Prometheus text files: one per repository and operation, each run replacing its own
"""

import sys
import os

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from npbackup.core.monitoring.prometheus import PrometheusMonitor


class DotConfig(dict):
    """
    Stand-in for npbackup's configuration objects: g() reads dotted keys
    """

    def g(self, key):
        node = self
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node


def monitor(destination, repo_name):
    repo_config = DotConfig(name=repo_name)
    monitoring_config = DotConfig(
        global_prometheus={"enabled": True, "destination": destination}
    )
    # append_mode as a group run sets it: text files must not append any more
    return PrometheusMonitor(repo_config, monitoring_config, append_mode=True)


def test_metrics_filename_carries_repo_name_and_action():
    directory = os.path.join("var", "lib", "node_exporter")
    assert PrometheusMonitor.metrics_filename(
        os.path.join(directory, "npbackup.prom"), "default", "backup"
    ) == os.path.join(directory, "npbackup___repo_name=default___action=backup.prom")
    assert (
        PrometheusMonitor.metrics_filename("metrics", "a", "check")
        == "metrics___repo_name=a___action=check"
    )


def test_characters_a_file_name_cannot_hold_are_replaced():
    assert (
        PrometheusMonitor.metrics_filename("npbackup.prom", "D:\\data: <1>", "backup")
        == "npbackup___repo_name=D__data_ _1____action=backup.prom"
    )


def test_each_repo_and_action_keeps_its_own_file(tmp_path):
    destination = str(tmp_path / "npbackup.prom")
    for repo_name, operation, state in (
        ("repo_one", "backup", 0),
        ("repo_two", "backup", 2),
        ("repo_one", "prune", 1),
        ("repo_one", "backup", 1),
    ):
        assert monitor(destination, repo_name).send_metrics(
            {"npbackup_exec_state": state}, operation
        )

    assert sorted(os.listdir(tmp_path)) == [
        "npbackup___repo_name=repo_one___action=backup.prom",
        "npbackup___repo_name=repo_one___action=prune.prom",
        "npbackup___repo_name=repo_two___action=backup.prom",
    ]
    with open(
        tmp_path / "npbackup___repo_name=repo_one___action=backup.prom",
        encoding="utf-8",
    ) as file_handle:
        lines = file_handle.read().splitlines()
    # Replaced by the latest run, not appended to
    assert len(lines) == 1
    assert lines[0].endswith(" 1")
