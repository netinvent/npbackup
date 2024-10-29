#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.task"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024102901"


from typing import List
import sys
import os
from logging import getLogger
import tempfile
from command_runner import command_runner
import datetime
from resources.customization import TASK_AUTHOR, TASK_URI, PROGRAM_NAME
from npbackup.path_helper import CURRENT_DIR, CURRENT_EXECUTABLE
from npbackup.__version__ import IS_COMPILED

logger = getLogger()


def _scheduled_task_exists_unix(config_file: str, type: str, object_args: str) -> bool:
    cron_file = "/etc/cron.d/npbackup"
    try:
        with open(cron_file, "r", encoding="utf-8") as file_handle:
            current_crontab = file_handle.readlines()
            for line in current_crontab:
                if f"--{type}" in line and config_file in line and object_args in line:
                    logger.info(f"Found existing {type} task")
                    return True
    except OSError as exc:
        logger.error("Could not read file {}: {}".format(cron_file, exc))
    return False


def create_scheduled_task(
    config_file: str,
    type: str,
    repo: str = None,
    group: str = None,
    interval_minutes: int = None,
    hour: int = None,
    minute: int = None,
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

    if type not in ("backup", "housekeeping"):
        logger.error("Undefined task type")
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

    # Make sure we have a full path to config_file if relative path is given
    if not os.path.isabs(config_file):
        config_file = os.path.join(CURRENT_DIR, config_file)

    if repo:
        subject = f"repo_name {repo}"
        object_args = f" --repo-name {repo}"
    elif group:
        subject = f"group_name {group}"
        object_args = f" --repo-group {group}"
    else:
        subject = f"repo_name default"
        object_args = ""
    if interval_minutes:
        logger.info(
            f"Creating scheduled task {type} for {subject} to run every {interval_minutes} minutes"
        )
    elif hour and minute:
        logger.info(
            f"Creating scheduled task {type} for {subject} to run at everyday at {hour}h{minute}"
        )

    if os.name == "nt":
        return create_scheduled_task_windows(
            config_file,
            type,
            CURRENT_EXECUTABLE,
            subject,
            object_args,
            interval_minutes,
            hour,
            minute,
        )
    else:
        return create_scheduled_task_unix(
            config_file,
            type,
            CURRENT_EXECUTABLE,
            subject,
            object_args,
            interval_minutes,
            hour,
            minute,
        )


def create_scheduled_task_unix(
    config_file: str,
    type: str,
    cli_executable_path: str,
    subject: str,
    object_args: str,
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
        TASK_ARGS = f'-c "{config_file}" --{type} --run-as-cli{object_args}'
        trigger = f"*/{interval_minutes} * * * *"
    elif hour is not None and minute is not None:
        if type == "backup":
            force_opt = " --force"
        else:
            force_opt = ""
        TASK_ARGS = f'-c "{config_file}" --{type}{force_opt} --run-as-cli{object_args}'
        trigger = f"{minute} {hour} * * * root"
    else:
        raise ValueError("Bogus trigger given")

    crontab_entry = (
        f'{trigger} cd "{executable_dir}" && {cli_executable_path} {TASK_ARGS}\n'
    )

    crontab_file = []

    try:
        replaced = False
        with open(cron_file, "r", encoding="utf-8") as file_handle:
            current_crontab = file_handle.readlines()
            for line in current_crontab:
                if f"--{type}" in line and config_file in line and object_args in line:
                    logger.info(f"Replacing existing {type} task")
                    if replaced:
                        logger.info(f"Skipping duplicate {type} task")
                        continue
                    crontab_file.append(crontab_entry)
                    replaced = True
                else:
                    crontab_file.append(line)
            if not replaced:
                logger.info(f"Adding new {type} task")
                crontab_file.append(crontab_entry)
    except OSError as exc:
        crontab_file.append(crontab_entry)

    try:
        with open(cron_file, "w", encoding="utf-8") as file_handle:
            file_handle.writelines(crontab_file)
    except OSError as exc:
        logger.error("Could not write to file  {}: {}".format(cron_file, exc))
        return False
    logger.info(f"Task created successfully as {cron_file}")
    return True


def _get_scheduled_task_name_windows(type: str, subject: str) -> str:
    return f"{PROGRAM_NAME} - {type.capitalize()} {subject}"


def create_scheduled_task_windows(
    config_file: str,
    type: str,
    cli_executable_path: str,
    subject: str,
    object_args: str,
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
    temp_task_file = os.path.join(tempfile.gettempdir(), "npbackup_task.xml")

    task_name = _get_scheduled_task_name_windows(type, subject)

    if interval_minutes is not None:
        task_args = f'{task_args}-c "{config_file}" --{type} --run-as-cli{object_args}'
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
        task_args = (
            f'{task_args}-c "{config_file}" --{type} --force --run-as-cli{object_args}'
        )
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
        'schtasks /DELETE /TN "{}" /F'.format(task_name),
        valid_exit_codes=[0, 1],
        windows_no_window=True,
        encoding="cp437",
    )
    logger.info("Creating scheduled task {}".format(task_name))
    exit_code, output = command_runner(
        'schtasks /CREATE /TN "{}" /XML "{}" /RU System /F'.format(
            task_name, temp_task_file
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
