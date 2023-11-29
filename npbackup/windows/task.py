#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.windows.task"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023020201"


import sys
import os
from logging import getLogger
import tempfile
from command_runner import command_runner
from npbackup.customization import PROGRAM_NAME

logger = getLogger()


# This is the path to a onefile executable binary
CURRENT_EXECUTABLE = os.path.abspath(sys.argv[0])
CURRENT_DIR = os.path.dirname(CURRENT_EXECUTABLE)
# When run with nuitka onefile, this will be the temp directory
# CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))


TASK_AUTHOR = "NetPerfect R1 Research"
TASK_URI = "\\{}".format(PROGRAM_NAME)
TASK_ARGS = "--backup"
TEMP_TASKFILE = os.path.join(tempfile.gettempdir(), "backup_task.xml")


def create_scheduled_task(executable_path, interval_minutes: int):
    if os.name != "nt":
        logger.error("Can only create a scheduled task on Windows")
        return False

    try:
        interval_minutes = int(interval_minutes)
    except ValueError:
        logger.error("Bogus interval given")
        return False

    executable_dir = os.path.dirname(executable_path)

    SCHEDULED_TASK_FILE_CONTENT = """<?xml version="1.0" encoding="UTF-16"?>
    <Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
    <RegistrationInfo>
        <Date>2023-01-01T13:37:00.1234567</Date>
        <Author>{}</Author>
        <URI>\{}</URI>
    </RegistrationInfo>
    <Triggers>
        <TimeTrigger>
        <Repetition>
            <Interval>PT{}M</Interval>
            <StopAtDurationEnd>false</StopAtDurationEnd>
        </Repetition>
        <StartBoundary>2023-01-30T09:00:00</StartBoundary>
        <ExecutionTimeLimit>P1D</ExecutionTimeLimit>
        <Enabled>true</Enabled>
        </TimeTrigger>
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
        <Command>"{}"</Command>
        <Arguments>{}</Arguments>
        <WorkingDirectory>{}</WorkingDirectory>
        </Exec>
    </Actions>
    </Task>""".format(
        TASK_AUTHOR,
        TASK_URI,
        interval_minutes,
        executable_path,
        TASK_ARGS,
        executable_dir,
    )
    # Create task file
    try:
        with open(TEMP_TASKFILE, "w") as file_handle:
            file_handle.write(SCHEDULED_TASK_FILE_CONTENT)
    except OSError as exc:
        logger.error(
            "Could not create temporary scheduled task file {}: {}".format(
                TEMP_TASKFILE, exc
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
            PROGRAM_NAME, TEMP_TASKFILE
        ),
        windows_no_window=True,
        encoding="cp437",
    )
    if exit_code != 0:
        logger.error("Could not create new task: {}".format(output))
        return False

    try:
        os.remove(TEMP_TASKFILE)
    except OSError as exc:
        logger.warning(
            "Could not remove temporary task file {}: {}".format(TEMP_TASKFILE, exc)
        )
        return False
    logger.info("Scheduled task created.")
    return True
