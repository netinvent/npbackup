#! /usr/bin/env python3
#  -*- coding: utf-8 -*-

__intname__ = "npbackup_task_arguments_tests"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2026 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2026101602"


"""
Scheduled tasks run arguments the command line accepts
Tasks created by earlier builds ran --check --quick, --check --full and a bare --forget,
which the command line refuses, so those tasks never ran

Crontab tasks start from the first run date and time chosen, as Task Scheduler ones do,
and show their next run as start date, since cron keeps none
"""

import sys
import os
import subprocess
import datetime
import pytest

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

import npbackup.task
from npbackup.task import SCHEDULER_TASKS, LEGACY_SCHEDULER_TASKS, get_task_args

CLI = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "bin", "npbackup-cli")
)


def refusal(task_args, tmp_path):
    """
    Run the command line as a scheduled task does (the GUI launcher drops --run-as-cli first),
    with a configuration file that does not exist: argparse decides before anything else
    Returns argparse's complaint, or None when the arguments were accepted
    """
    command = (
        [sys.executable, CLI, "-c", str(tmp_path / "missing.conf")]
        + task_args.split()
        + ["--repo-name", "default"]
    )
    result = subprocess.run(
        command,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    for line in result.stderr.splitlines():
        if "error: argument" in line or "unrecognized arguments" in line:
            return line
    return None


def test_every_scheduled_task_runs_arguments_the_command_line_accepts(tmp_path):
    for task_type in SCHEDULER_TASKS:
        for force in (True, False) if task_type == "backup" else (True,):
            task_args = get_task_args(task_type, force)
            assert refusal(task_args, tmp_path) is None, task_args


def test_the_arguments_earlier_builds_wrote_are_refused(tmp_path):
    for legacy in LEGACY_SCHEDULER_TASKS.values():
        assert refusal(f"--{legacy}", tmp_path) is not None, legacy


@pytest.mark.skipif(os.name == "nt", reason="crontab tasks are created off Windows only")
def test_crontab_tasks_start_from_the_first_run_date_chosen(tmp_path, monkeypatch):
    seen = {}

    def create_scheduled_task_unix(*args, **kwargs):
        seen.update(kwargs)
        return True

    monkeypatch.setattr(
        npbackup.task, "create_scheduled_task_unix", create_scheduled_task_unix
    )
    first_run = datetime.datetime(2026, 10, 19, 22, 30)
    assert npbackup.task.create_scheduled_task(
        tmp_path / "npbackup.conf",
        "full_check",
        "repos",
        "default",
        start_date_time=first_run,
        interval=1,
        interval_unit="weeks",
        days=[],
    )
    assert seen["start_date_time"] == first_run


def test_a_cron_job_shows_its_next_run_as_its_start_date():
    # Wednesday 14 October 2026, 10:00
    now = datetime.datetime(2026, 10, 14, 10, 0)
    for fields, expected in (
        # Daily: its time
        ("30 22 * * *", datetime.datetime(2026, 10, 14, 22, 30)),
        # Weekly: its weekday
        ("30 22 * * MON", datetime.datetime(2026, 10, 19, 22, 30)),
        # The weekdays ticked
        ("0 9 * * MON,WED,FRI", datetime.datetime(2026, 10, 16, 9, 0)),
        # Every 3 months from January: its day of the month
        ("0 3 15 */3 *", datetime.datetime(2026, 10, 15, 3, 0)),
        ("0 3 31 * *", datetime.datetime(2026, 10, 31, 3, 0)),
        # Every 4 hours: its minute
        ("10 */4 * * *", datetime.datetime(2026, 10, 14, 12, 10)),
        ("*/15 * * * *", datetime.datetime(2026, 10, 14, 10, 0)),
    ):
        assert npbackup.task._cron_next_run(*fields.split(), now=now) == expected, fields
    # Not a form npbackup writes
    assert npbackup.task._cron_next_run("0", "3", "1-7", "*", "*", now=now) is None
