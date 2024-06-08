#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.task"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024060501"


import sys
import os
from logging import getLogger
import tempfile
from command_runner import command_runner
import datetime
from resources.customization import TASK_AUTHOR, TASK_URI, PROGRAM_NAME
from npbackup.path_helper import CURRENT_DIR
from npbackup.__version__ import IS_COMPILED

logger = getLogger()


def create_scheduled_task(
    config_file: str, interval_minutes: int = None, hour: int = None, minute: int = None
):
    """
    Creates a scheduled task for NPBackup
    if interval_minutes is given, npbackup will run every interval minutes, but only backup if minimum_backup_age is reached
    if hour and minute are given, npbackup will run regardless of minimum_backup_age
    """

    try:
        if interval_minutes:
            interval_minutes = int(interval_minutes)
        if hour:
            hour = int(hour)
            minute = int(minute)
    except ValueError:
        logger.error("Bogus interval given")
        return False

    if isinstance(interval_minutes, int) and interval_minutes < 1:
        logger.error("Bogus interval given")
        return False
    if isinstance(hour, int) and isinstance(minute, int):
        if hour > 24 or minute > 60 or hour < 0 or minute < 0:
            logger.error("Bogus hour or minute given")
            return False
    if interval_minutes is None and (hour is None or minute is None):
        logger.error("No interval or time given")
        return False

    if os.name == "nt":
        possible_paths = [
            CURRENT_DIR,
            os.path.join(os.path.dirname(CURRENT_DIR), "npbackup-cli"),
            os.path.join(os.environ["PROGRAMFILES"], PROGRAM_NAME),
            os.path.join(os.environ["PROGRAMFILES(X86)"], PROGRAM_NAME),
        ]
    else:
        possible_paths = [
            CURRENT_DIR,
            os.path.join(os.path.dirname(CURRENT_DIR), "npbackup-cli"),
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
        ]

    cli_executable = "npbackup-cli" + (
        ".exe" if os.name == "nt" and IS_COMPILED else ""
    )
    cli_executable_path = None
    for path in possible_paths:
        possible_cli_executable_path = os.path.join(path, cli_executable)
        if os.path.exists(os.path.join(path, possible_cli_executable_path)):
            cli_executable_path = possible_cli_executable_path
            break
    if not cli_executable_path:
        logger.error("Could not find path for npbackup-cli executable")
        return False

    # Make sure we have a full path to config_file if relative path is given
    if not os.path.isabs(config_file):
        config_file = os.path.join(CURRENT_DIR, config_file)

    if os.name == "nt":
        return create_scheduled_task_windows(
            config_file, cli_executable_path, interval_minutes, hour, minute
        )
    else:
        return create_scheduled_task_unix(
            config_file, cli_executable_path, interval_minutes, hour, minute
        )


def create_scheduled_task_unix(
    config_file,
    cli_executable_path,
    interval_minutes: int = None,
    hour: int = None,
    minute: int = None,
):
    executable_dir = os.path.dirname(cli_executable_path)
    if "python" in sys.executable and not IS_COMPILED:
        cli_executable_path = f'"{sys.executable}" "{cli_executable_path}"'
    else:
        cli_executable_path = f'"{cli_executable_path}"'
    cron_file = "/etc/cron.d/npbackup"
    if interval_minutes is not None:
        TASK_ARGS = f'-c "{config_file}" --backup'
        trigger = f"*/{interval_minutes} * * * *"
    elif hour is not None and minute is not None:
        TASK_ARGS = f'-c "{config_file}" --backup --force'
        trigger = f"{minute} {hour} * * * root"
    else:
        raise ValueError("Bogus trigger given")

    crontab_entry = (
        f'{trigger} cd "{executable_dir}" && {cli_executable_path} {TASK_ARGS}\n'
    )
    try:
        with open(cron_file, "w") as file_handle:
            file_handle.write(crontab_entry)
    except OSError as exc:
        logger.error("Could not write to file  {}: {}".format(cron_file, exc))
        return False
    logger.info(f"Task created successfully as {cron_file}")
    return True


def create_scheduled_task_windows(
    config_file,
    cli_executable_path,
    interval_minutes: int = None,
    hour: int = None,
    minute: int = None,
):
    executable_dir = os.path.dirname(cli_executable_path)
    if "python" in sys.executable and not IS_COMPILED:
        runner = sys.executable
        task_args = f'"{cli_executable_path}" '
    else:
        runner = cli_executable_path
        task_args = ""
    temp_task_file = os.path.join(tempfile.gettempdir(), "backup_task.xml")
    if interval_minutes is not None:
        task_args = f'{task_args}-c "{config_file}" --backup'
        start_date = datetime.datetime.now().replace(microsecond=0).isoformat()
        trigger = f"""<TimeTrigger>
            <Repetition>
                <Interval>PT{interval_minutes}M</Interval>
                <StopAtDurationEnd>false</StopAtDurationEnd>
            </Repetition>
            <StartBoundary>{start_date}</StartBoundary>
            <ExecutionTimeLimit>P1D</ExecutionTimeLimit>
            <Enabled>true</Enabled>
            </TimeTrigger>"""
    elif hour is not None and minute is not None:
        task_args = f'{task_args}-c "{config_file}" --backup --force'
        start_date = (
            datetime.datetime.now()
            .replace(microsecond=0, hour=hour, minute=minute, second=0)
            .isoformat()
        )
        trigger = f"""<CalendarTrigger>
            <StartBoundary>{start_date}</StartBoundary>
            <Enabled>true</Enabled>
            <ScheduleByDay>
                <DaysInterval>1</DaysInterval>
            </ScheduleByDay>
            </CalendarTrigger>"""
    else:
        raise ValueError("Bogus trigger given")

    SCHEDULED_TASK_FILE_CONTENT = f"""<?xml version="1.0" encoding="UTF-16"?>
    <Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
    <RegistrationInfo>
        <Date>2023-01-01T13:37:00.1234567</Date>
        <Author>{TASK_AUTHOR}</Author>
        <URI>\\{TASK_URI}</URI>
    </RegistrationInfo>
    <Triggers>
        {trigger}
    </Triggers>
    <Principals>
        <Principal id="Author">
        <UserId>S-1-5-18</UserId>
        <RunLevel>HighestAvailable</RunLevel>
        </Principal>
    </Principals>
    <Settings>
        <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
        <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
        <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
        <AllowHardTerminate>true</AllowHardTerminate>
        <StartWhenAvailable>true</StartWhenAvailable>
        <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
        <IdleSettings>
        <StopOnIdleEnd>true</StopOnIdleEnd>
        <RestartOnIdle>false</RestartOnIdle>
        </IdleSettings>
        <AllowStartOnDemand>true</AllowStartOnDemand>
        <Enabled>true</Enabled>
        <Hidden>false</Hidden>
        <RunOnlyIfIdle>false</RunOnlyIfIdle>
        <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
        <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
        <WakeToRun>false</WakeToRun>
        <ExecutionTimeLimit>P1D</ExecutionTimeLimit>
        <Priority>7</Priority>
    </Settings>
    <Actions Context="Author">
        <Exec>
        <Command>"{runner}"</Command>
        <Arguments>{task_args}</Arguments>
        <WorkingDirectory>{executable_dir}</WorkingDirectory>
        </Exec>
    </Actions>
    </Task>"""
    # Create task file
    try:
        with open(temp_task_file, "w") as file_handle:
            file_handle.write(SCHEDULED_TASK_FILE_CONTENT)
    except OSError as exc:
        logger.error(
            "Could not create temporary scheduled task file {}: {}".format(
                temp_task_file, exc
            )
        )
        return False

    # Setup task
    command_runner(
        'schtasks /DELETE /TN "{}" /F'.format(PROGRAM_NAME),
        valid_exit_codes=[0, 1],
        windows_no_window=True,
        encoding="cp437",
    )
    logger.info("Creating scheduled task {}".format(PROGRAM_NAME))
    exit_code, output = command_runner(
        'schtasks /CREATE /TN "{}" /XML "{}" /RU System /F'.format(
            PROGRAM_NAME, temp_task_file
        ),
        windows_no_window=True,
        encoding="cp437",
    )
    if exit_code != 0:
        logger.error("Could not create new task: {}".format(output))
        return False

    try:
        os.remove(temp_task_file)
    except OSError as exc:
        logger.warning(
            "Could not remove temporary task file {}: {}".format(temp_task_file, exc)
        )
        return False
    logger.info("Scheduled task created.")
    return True
