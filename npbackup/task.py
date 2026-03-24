#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.task"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026032001"


import sys
import os
import re
import json
from typing import List, Optional
import logging
import tempfile
import datetime
from resources.customization import TASK_AUTHOR, TASK_URI, PROGRAM_NAME
from npbackup.path_helper import CURRENT_DIR, CURRENT_EXECUTABLE, sanitize_filename
from npbackup.__version__ import IS_COMPILED
import npbackup.configuration
from npbackup.gui.constants import combo_boxes

if os.name == "nt":
    # pylint: disable=E0401 (import-error)
    from windows_tools.powershell import PowerShellRunner

    class CronTab:
        pass

else:
    from crontab import CronTab

    class PowerShellRunner:
        pass


logger = logging.getLogger()

SCHEDULER_TASKS = {
    "backup": "backup",
    "housekeeping": "housekeeping",
    "quick_check": "check --quick",
    "full_check": "check --full",
    "forget": "forget",
    "prune": "prune",
}


#### OS ABSTRACTION LAYER ####
def read_existing_scheduled_tasks(
    config_file: str,
    full_config: dict,
    operation: str = None,
) -> List[dict]:
    """
    Reads existing scheduled tasks for NPBackup and checks if a task with the same config file, task type and repo/group already exists
    """
    # Transform possible PosixPath to string
    config_file = str(config_file)
    # Make sure we have a full path to config_file if relative path is given
    if not os.path.isabs(config_file):
        config_file = os.path.join(CURRENT_DIR, config_file)

    if os.name == "nt":
        return _read_existing_scheduled_task_windows(
            config_file,
            full_config,
            operation,
        )
    else:
        return _read_existing_scheduled_task_unix(config_file, full_config, operation)


def create_scheduled_task(
    config_file: str,
    task_type: str,
    object_type: str,
    object_name: str,
    as_current_user: bool = False,
    start_date_time: datetime.datetime = None,
    interval: int = None,
    interval_unit: str = None,
    days: List[str] = None,
    force: bool = True,
):
    """
    Creates a scheduled task for NPBackup
    """

    # Transform possible PosixPath to string
    config_file = str(config_file)

    try:
        if interval is not None:
            interval = int(interval)
    except ValueError:
        logger.error(f"Bogus interval given: {interval}")
        return False

    if task_type not in SCHEDULER_TASKS.keys():
        logger.error(f"Undefined task type: {task_type}")
        return False

    if isinstance(interval, int) and interval < 1:
        logger.error(f"Too small interval given: {interval}")
        return False
    if interval is None:
        logger.error("No interval")
        return False
    if interval_unit not in combo_boxes["backup_interval_unit"].keys():
        logger.error(f"Bogus interval unit {interval_unit} given")
        return False

    if days:
        for day in days:
            if day not in [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ]:
                logger.error(f"Bogus day {day} given")
                return False

    # Make sure we have a full path to config_file if relative path is given
    if not os.path.isabs(config_file):
        config_file = os.path.join(CURRENT_DIR, config_file)

    logger.info(
        f"Creating scheduled task {task_type} for {object_type} {object_name} to run every {interval} {interval_unit}"
    )

    if os.name == "nt":
        return create_scheduled_task_windows(
            config_file,
            task_type,
            object_type,
            object_name,
            as_current_user,
            CURRENT_EXECUTABLE,
            start_date_time=start_date_time,
            interval=interval,
            interval_unit=interval_unit,
            days=days,
            force=force,
        )
    else:
        return create_scheduled_task_unix(
            config_file,
            task_type,
            object_type,
            object_name,
            as_current_user,
            CURRENT_EXECUTABLE,
            interval=interval,
            interval_unit=interval_unit,
            days=days,
            force=force,
        )


def delete_scheduled_task(
    config_file: str,
    task_type: str,
    object_type: str,
    object_name: str,
):
    config_file = str(config_file)
    if not os.path.isabs(config_file):
        config_file = os.path.join(CURRENT_DIR, config_file)

    if os.name == "nt":
        return _delete_scheduled_task_windows(
            config_file, task_type, object_type, object_name
        )
    else:
        return _delete_scheduled_task_unix(
            config_file, task_type, object_type, object_name
        )


#### GENERIC FUNCTIONS ####
def get_object_args(object_type: str, object_name: str) -> str:
    object_args = " --repo-name default"
    if object_name:
        if object_type == "repos":
            object_args = f" --repo-name {object_name}"
        elif object_type == "groups":
            object_args = f" --repo-group {object_name}"
    return object_args


#### UNIX TASK MANAGEMENT ####

# Mapping from lowercase day names to cron 3-letter abbreviations
_DOW_TO_CRON = {
    "monday": "MON",
    "tuesday": "TUE",
    "wednesday": "WED",
    "thursday": "THU",
    "friday": "FRI",
    "saturday": "SAT",
    "sunday": "SUN",
}
# Reverse mapping: cron DOW integer (0=Sun) to lowercase day name
_DOW_FROM_INT = {
    0: "sunday",
    1: "monday",
    2: "tuesday",
    3: "wednesday",
    4: "thursday",
    5: "friday",
    6: "saturday",
}


def _get_cron_comment(
    config_file: str, task_type: str, object_type: str, object_name: str
) -> str:
    """Generate a unique comment identifier for a cron job, mirroring the Windows task name."""
    config_file = str(config_file)
    if not object_name:
        object_name = "default"
        object_type = "repos"
    config_file_sanitized = sanitize_filename(config_file)
    return f"{PROGRAM_NAME} - {task_type} {object_type} {object_name} in {config_file_sanitized}"


def _get_crontab(as_current_user: bool) -> CronTab:
    """Return a CronTab instance for the current user or root."""
    if as_current_user:
        return CronTab(user=True)
    return CronTab(user="root")


def _read_existing_scheduled_task_unix(
    config_file: str, full_config: dict, operation: str
) -> List[dict]:
    tasks = []
    # Check both current user and root crontabs
    for crontab_user in [True, "root"]:
        try:
            cron = CronTab(user=crontab_user)
        except Exception as exc:
            logger.debug(f"Could not read crontab for user {crontab_user}: {exc}")
            continue

        for (
            object_name,
            object_type,
        ) in npbackup.configuration.get_object_names_and_types(full_config).items():
            for task_type in SCHEDULER_TASKS.keys():
                if operation and task_type != operation:
                    continue
                comment = _get_cron_comment(
                    config_file, task_type, object_type, object_name
                )
                for job in cron.find_comment(comment):
                    if not job.is_enabled():
                        continue

                    task_info = {
                        "object_type": None,
                        "object_name": None,
                        "task_type": task_type,
                        "interval": None,
                        "interval_unit": None,
                        "start_date": None,  # cron has no start date concept
                        "days_of_week": [],
                    }

                    # Extract object info from command
                    cmd = str(job.command)
                    repo_match = re.search(r"--repo-name\s+(\S+)", cmd)
                    if repo_match:
                        task_info["object_type"] = "repos"
                        task_info["object_name"] = repo_match.group(1)
                    else:
                        group_match = re.search(r"--repo-group\s+(\S+)", cmd)
                        if group_match:
                            task_info["object_type"] = "groups"
                            task_info["object_name"] = group_match.group(1)

                    # Extract frequency from cron schedule fields
                    minute_str = str(job.minute)
                    hour_str = str(job.hour)
                    dom_str = str(job.dom)
                    month_str = str(job.month)

                    if minute_str.startswith("*/"):
                        task_info["interval"] = int(minute_str[2:])
                        task_info["interval_unit"] = "minutes"
                    elif hour_str.startswith("*/"):
                        task_info["interval"] = int(hour_str[2:])
                        task_info["interval_unit"] = "hours"
                    elif dom_str.startswith("*/"):
                        task_info["interval"] = int(dom_str[2:])
                        task_info["interval_unit"] = "days"
                    elif month_str.startswith("*/"):
                        task_info["interval"] = int(month_str[2:])
                        task_info["interval_unit"] = "months"
                    elif str(job.dow) != "*":
                        task_info["interval"] = 7  # weekly
                        task_info["interval_unit"] = "weeks"
                    else:
                        task_info["interval"] = 1
                        task_info["interval_unit"] = "days"

                    # Extract days of week
                    dow_str = str(job.dow)
                    if dow_str != "*":
                        for part in dow_str.split(","):
                            part = part.strip()
                            if part.isdigit() and int(part) in _DOW_FROM_INT:
                                task_info["days_of_week"].append(
                                    _DOW_FROM_INT[int(part)]
                                )

                    logger.info(f"Found existing cron job: {comment}")
                    tasks.append(task_info)
    return tasks


def create_scheduled_task_unix(
    config_file: str,
    task_type: str,
    object_type: str,
    object_name: str,
    as_current_user: bool,
    cli_executable_path: str,
    start_date_time: datetime.datetime = None,
    interval: int = None,
    interval_unit: str = None,
    days: List[str] = None,
    force: bool = True,
):
    logger.debug(f"Creating task {task_type} for {object_type} {object_name}")
    executable_dir = os.path.dirname(cli_executable_path)
    if "python" in sys.executable and not IS_COMPILED:
        cli_executable_path = f'"{sys.executable}" "{cli_executable_path}"'
    else:
        cli_executable_path = f'"{cli_executable_path}"'

    object_args = get_object_args(object_type, object_name)
    if task_type == "backup":
        if force:
            task_arg = "--backup --force"
        else:
            task_arg = "--backup"
    else:
        task_arg = f"--{task_type}"
    task_args = f'-c "{config_file}" {task_arg} --run-as-cli{object_args}'
    command = f'cd "{executable_dir}" && {cli_executable_path} {task_args}'
    comment = _get_cron_comment(config_file, task_type, object_type, object_name)

    # Reference time for hour/minute in cron schedule
    ref_time = start_date_time if start_date_time else datetime.datetime.now()

    try:
        cron = _get_crontab(as_current_user)
    except Exception as exc:
        logger.error(f"Could not access crontab: {exc}")
        return False

    # Remove existing job with same comment (replace semantics)
    cron.remove_all(comment=comment)

    job = cron.new(command=command, comment=comment)

    use_repetition = interval is not None and interval_unit in ("minutes", "hours")

    if days and use_repetition:
        # Weekly + intra-day repetition (e.g. every Sunday every 20 min)
        dow_values = [_DOW_TO_CRON[d] for d in days]
        job.dow.on(*dow_values)
        if interval_unit == "minutes":
            job.minute.every(interval)
        else:  # hours
            job.minute.on(ref_time.minute)
            job.hour.every(interval)
    elif days:
        # Weekly schedule, once per day at specified time
        dow_values = [_DOW_TO_CRON[d] for d in days]
        job.dow.on(*dow_values)
        job.minute.on(ref_time.minute)
        job.hour.on(ref_time.hour)
    elif use_repetition:
        # Repeat every N minutes/hours, all days
        if interval_unit == "minutes":
            job.minute.every(interval)
        else:  # hours
            job.minute.on(ref_time.minute)
            job.hour.every(interval)
    elif interval is not None and interval_unit == "days":
        # Every N days at specified time
        job.minute.on(ref_time.minute)
        job.hour.on(ref_time.hour)
        job.dom.every(interval)
    elif interval is not None and interval_unit == "weeks":
        # Every N weeks — cron cannot express multi-week intervals natively
        if interval > 1:
            logger.warning(
                f"Cron cannot express 'every {interval} weeks' precisely. Using weekly schedule."
            )
        # Use the start day's weekday
        cron_dow = (
            ref_time.weekday() + 1
        ) % 7  # Python weekday (Mon=0) → cron DOW (Sun=0)
        job.minute.on(ref_time.minute)
        job.hour.on(ref_time.hour)
        job.dow.on(cron_dow)
    elif interval is not None and interval_unit == "months":
        # Every N months on the start day's day-of-month
        job.minute.on(ref_time.minute)
        job.hour.on(ref_time.hour)
        job.dom.on(ref_time.day)
        job.month.every(interval)
    else:
        # Daily at specified time (default fallback)
        job.minute.on(ref_time.minute)
        job.hour.on(ref_time.hour)

    if not job.is_valid():
        logger.error(f"Invalid cron schedule generated: {job}")
        return False

    try:
        cron.write()
    except Exception as exc:
        logger.error(f"Could not write crontab: {exc}")
        return False

    logger.info(f"Cron job created: {job}")
    return True


def _delete_scheduled_task_unix(
    config_file: str,
    task_type: str,
    object_type: str,
    object_name: str,
):
    comment = _get_cron_comment(config_file, task_type, object_type, object_name)
    deleted = False
    # Try both current user and root crontabs
    for crontab_user in [True, "root"]:
        try:
            cron = CronTab(user=crontab_user)
        except Exception as exc:
            logger.debug(f"Could not access crontab for user {crontab_user}: {exc}")
            continue
        jobs = list(cron.find_comment(comment))
        if jobs:
            cron.remove_all(comment=comment)
            try:
                cron.write()
                deleted = True
                logger.info(f"Deleted {len(jobs)} cron job(s) for: {comment}")
            except Exception as exc:
                logger.error(f"Could not write crontab for user {crontab_user}: {exc}")
    if not deleted:
        logger.info(f"No cron job found for: {comment}")
    return deleted


#### WINDOWS TASK MANAGEMENT ####
def _parse_iso_duration_to_minutes(duration: str) -> Optional[int]:
    """Parse ISO 8601 duration (e.g. PT15M, PT1H30M, P1D) to total minutes."""
    match = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", duration)
    if not match:
        return None
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    return days * 1440 + hours * 60 + minutes


def _get_scheduled_task_name_windows(
    config_file: str, task_type: str, object_type: str, object_name: str
) -> str:
    """
    We need to have unique identifiers for our tasks depending on their config file, task name and object
    in order to identify them later
    """
    config_file = str(config_file)
    if not object_name:
        object_name = "default"
        object_type = "repos"
    # Sanitize config_file name but keep path in case we might encounter multiple config files with same path
    config_file = sanitize_filename(config_file)
    return f"{PROGRAM_NAME} - {task_type.capitalize()} {object_type} {object_name} in {config_file}"


def _read_existing_scheduled_task_windows(
    config_file: str,
    full_config: dict,
    operation: str,
) -> List[dict]:
    """
    Read existing scheduled tasks on Windows.

    We'll use a single script to query all expected task names at once and return a structured JSON
    We'll try to elevate in order to get system tasks as well
    """
    tasks = []

    # Build a lookup of expected task names -> metadata
    task_lookup = {}
    for object_name, object_type in npbackup.configuration.get_object_names_and_types(
        full_config
    ).items():
        for task_type in SCHEDULER_TASKS.keys():
            if operation and task_type != operation:
                continue
            task_name = _get_scheduled_task_name_windows(
                config_file, task_type, object_type, object_name
            )
            task_lookup[task_name] = {
                "task_type": task_type,
                "object_type": object_type,
                "object_name": object_name,
                "object_args": get_object_args(object_type, object_name),
            }

    if not task_lookup:
        return tasks

    # Build a single PowerShell script that queries all tasks at once.
    # Escape single quotes for PowerShell string literals.
    ps_task_names = ",".join(
        "'{}'".format(name.replace("'", "''")) for name in task_lookup
    )

    # DaysOfWeek in CIM is a UInt16 flags enum:
    #   Sunday=1, Monday=2, Tuesday=4, Wednesday=8,
    #   Thursday=16, Friday=32, Saturday=64
    ps_script = f"""$ErrorActionPreference = 'SilentlyContinue'
$results = @()
$taskNames = @({ps_task_names})
$dayNames = @('Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')
$dayBits  = @(1,2,4,8,16,32,64)
foreach ($name in $taskNames) {{
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($null -eq $task) {{ continue }}
    $arguments = ''
    foreach ($action in $task.Actions) {{
        if ($action.Arguments) {{ $arguments = $action.Arguments; break }}
    }}
    $triggerList = @()
    foreach ($trigger in $task.Triggers) {{
        $tType = $trigger.CimClass.CimClassName
        $tObj = @{{
            type                = $tType
            start_boundary      = $trigger.StartBoundary
            repetition_interval = $null
            days_interval       = $null
            weeks_interval      = $null
            days_of_week        = @()
        }}
        if ($trigger.Repetition -and $trigger.Repetition.Interval) {{
            $tObj['repetition_interval'] = [string]$trigger.Repetition.Interval
        }}
        if ($tType -eq 'MSFT_TaskDailyTrigger') {{
            $tObj['days_interval'] = $trigger.DaysInterval
        }} elseif ($tType -eq 'MSFT_TaskWeeklyTrigger') {{
            $tObj['weeks_interval'] = $trigger.WeeksInterval
            $dowFlags = [int]$trigger.DaysOfWeek
            for ($i = 0; $i -lt 7; $i++) {{
                if ($dowFlags -band $dayBits[$i]) {{
                    $tObj['days_of_week'] += $dayNames[$i]
                }}
            }}
        }}
        $triggerList += [PSCustomObject]$tObj
    }}
    $results += [PSCustomObject]@{{
        task_name = $name
        arguments = $arguments
        triggers  = $triggerList
    }}
}}
if ($results.Count -gt 0) {{
    ConvertTo-Json -InputObject @($results) -Depth 5 -Compress
}} else {{
    Write-Output '[]'
}}
"""
    try:
        runner = PowerShellRunner()
        exit_code, output = runner.run_script(ps_script, elevated=True)
        if exit_code != 0 or not output or not output.strip():
            logger.debug(f"No scheduled tasks found or PowerShell error: {output}")
            return tasks
    except OSError as exc:
        logger.error(f"Could not run PowerShell script: {exc}")
        return tasks

    try:
        raw_tasks = json.loads(output.strip())
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error(f"Could not parse PowerShell JSON output: {exc}")
        logger.debug(f"Raw output: {output}")
        return tasks

    if not isinstance(raw_tasks, list):
        raw_tasks = [raw_tasks]

    for raw_task in raw_tasks:
        task_name = raw_task.get("task_name", "")
        if task_name not in task_lookup:
            continue

        meta = task_lookup[task_name]
        arguments = raw_task.get("arguments", "")

        # Verify tfhe task arguments actually match what we expect
        if (
            f"--{meta['task_type']}" not in arguments
            or config_file not in arguments
            or meta["object_args"] not in arguments
        ):
            logger.debug(f"Arguments not matching, skipping task: {arguments}")
            continue

        logger.info(f"Found existing task: {task_name}")

        task_info = {
            "object_type": None,
            "object_name": None,
            "task_type": meta["task_type"],
            "interval": None,
            "interval_unit": None,
            "start_date": None,
            "days_of_week": [],
        }

        # Extract repo/group from task arguments
        repo_match = re.search(r"--repo-name\s+(\S+)", arguments)
        if repo_match:
            task_info["object_type"] = "repos"
            task_info["object_name"] = repo_match.group(1)
        else:
            group_match = re.search(r"--repo-group\s+(\S+)", arguments)
            if group_match:
                task_info["object_type"] = "groups"
                task_info["object_name"] = group_match.group(1)

        # Process triggers returned by PowerShell
        for trigger in raw_task.get("triggers", []):
            trigger_type = trigger.get("type", "")

            # StartBoundary
            start = trigger.get("start_boundary")
            if start:
                try:
                    task_info["start_date"] = datetime.datetime.fromisoformat(start)
                except ValueError:
                    task_info["start_date"] = start

            # Intra-day repetition interval (applies to any trigger type)
            rep_interval = trigger.get("repetition_interval")
            if rep_interval:
                minutes = _parse_iso_duration_to_minutes(rep_interval)
                if minutes:
                    task_info["interval"] = minutes
                    task_info["interval_unit"] = "minutes"

            # MSFT_TaskTimeTrigger: interval already handled above via repetition

            # MSFT_TaskDailyTrigger
            if trigger_type == "MSFT_TaskDailyTrigger":
                days_interval = trigger.get("days_interval")
                if days_interval and not rep_interval:
                    task_info["interval"] = int(days_interval)
                    task_info["interval_unit"] = "days"

            # MSFT_TaskWeeklyTrigger
            elif trigger_type == "MSFT_TaskWeeklyTrigger":
                task_info["days_of_week"] = trigger.get("days_of_week", [])
                if not rep_interval:
                    weeks_interval = trigger.get("weeks_interval")
                    if weeks_interval:
                        task_info["interval"] = int(weeks_interval) * 7
                        task_info["interval_unit"] = "weeks"

        tasks.append(task_info)
        logger.debug(f"Parsed task info: {task_info}")
    return tasks


def create_scheduled_task_windows(
    config_file: str,
    task_type: str,
    object_type: str,
    object_name: str,
    as_current_user: bool,
    cli_executable_path: str,
    start_date_time: datetime.datetime = None,
    interval: int = None,
    interval_unit: str = None,
    days: List[str] = None,
    force: bool = True,
):
    logger.debug(f"Creating task {task_type} for {object_type} {object_name}")
    executable_dir = os.path.dirname(cli_executable_path)
    if "python" in sys.executable and not IS_COMPILED:
        runner = sys.executable
        task_args = f'"{ cli_executable_path}" '
    else:
        runner = cli_executable_path
        task_args = ""
    temp_task_file = os.path.join(tempfile.gettempdir(), "npbackup_task.xml")

    task_name = _get_scheduled_task_name_windows(
        config_file, task_type, object_type, object_name
    )
    object_args = get_object_args(object_type, object_name)

    # Compute StartBoundary
    if start_date_time is not None:
        start_date = start_date_time.replace(microsecond=0).isoformat()
    else:
        start_date = datetime.datetime.now().replace(microsecond=0).isoformat()

    if task_type == "backup":
        if force:
            task_arg = "--backup --force"
        else:
            task_arg = "--backup"
    else:
        task_arg = f"--{task_type}"
    task_args = f'{task_args}-c "{config_file}" {task_arg} --run-as-cli{object_args}'

    # For minutes/hours intervals, use Repetition inside a trigger
    # For days/weeks/months, use the appropriate CalendarTrigger schedule
    use_repetition = interval is not None and interval_unit in ("minutes", "hours")

    if use_repetition:
        iso_interval = (
            f"PT{interval}M" if interval_unit == "minutes" else f"PT{interval}H"
        )
        repetition_xml = f"""<Repetition>
                <Interval>{iso_interval}</Interval>
                <Duration>P1D</Duration>
                <StopAtDurationEnd>false</StopAtDurationEnd>
            </Repetition>"""
    else:
        repetition_xml = ""

    if days and use_repetition:
        # Weekly schedule with intra-day repetition (e.g. every Sunday every 20 min)
        days_xml = "\n                ".join(f"<{day.capitalize()} />" for day in days)
        trigger = f"""<CalendarTrigger>
            {repetition_xml}
            <StartBoundary>{start_date}</StartBoundary>
            <Enabled>true</Enabled>
            <ScheduleByWeek>
                <DaysOfWeek>
                {days_xml}
                </DaysOfWeek>
                <WeeksInterval>1</WeeksInterval>
            </ScheduleByWeek>
            </CalendarTrigger>"""
    elif days:
        # Weekly schedule, run once per trigger day
        days_xml = "\n                ".join(f"<{day.capitalize()} />" for day in days)
        trigger = f"""<CalendarTrigger>
            <StartBoundary>{start_date}</StartBoundary>
            <Enabled>true</Enabled>
            <ScheduleByWeek>
                <DaysOfWeek>
                {days_xml}
                </DaysOfWeek>
                <WeeksInterval>1</WeeksInterval>
            </ScheduleByWeek>
            </CalendarTrigger>"""
    elif use_repetition:
        # Repeat every N minutes/hours regardless of day
        trigger = f"""<TimeTrigger>
            {repetition_xml}
            <StartBoundary>{start_date}</StartBoundary>
            <ExecutionTimeLimit>P1D</ExecutionTimeLimit>
            <Enabled>true</Enabled>
            </TimeTrigger>"""
    elif interval is not None and interval_unit == "days":
        # Every N days
        trigger = f"""<CalendarTrigger>
            <StartBoundary>{start_date}</StartBoundary>
            <Enabled>true</Enabled>
            <ScheduleByDay>
                <DaysInterval>{interval}</DaysInterval>
            </ScheduleByDay>
            </CalendarTrigger>"""
    elif interval is not None and interval_unit == "weeks":
        # Every N weeks on the start day's weekday
        ref_date = start_date_time if start_date_time else datetime.datetime.now()
        start_day = ref_date.strftime("%A")
        trigger = f"""<CalendarTrigger>
            <StartBoundary>{start_date}</StartBoundary>
            <Enabled>true</Enabled>
            <ScheduleByWeek>
                <DaysOfWeek>
                <{start_day} />
                </DaysOfWeek>
                <WeeksInterval>{interval}</WeeksInterval>
            </ScheduleByWeek>
            </CalendarTrigger>"""
    elif interval is not None and interval_unit == "months":
        # Every N months on the start day's day-of-month
        all_months = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        selected_months = [all_months[i] for i in range(0, 12, interval)]
        months_xml = "".join(f"<{m} />" for m in selected_months)
        ref_date = start_date_time if start_date_time else datetime.datetime.now()
        trigger = f"""<CalendarTrigger>
            <StartBoundary>{start_date}</StartBoundary>
            <Enabled>true</Enabled>
            <ScheduleByMonth>
                <DaysOfMonth>
                    <Day>{ref_date.day}</Day>
                </DaysOfMonth>
                <Months>
                    {months_xml}
                </Months>
            </ScheduleByMonth>
            </CalendarTrigger>"""
    else:
        # Daily schedule (default fallback)
        trigger = f"""<CalendarTrigger>
            <StartBoundary>{start_date}</StartBoundary>
            <Enabled>true</Enabled>
            <ScheduleByDay>
                <DaysInterval>1</DaysInterval>
            </ScheduleByDay>
            </CalendarTrigger>"""

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
    # Create task XML file with UTF-8 encoding to match XML declaration
    # And yes, we know that we need to write an UTF-8 file with UTF-16 encoding
    # thanks windows
    try:
        with open(temp_task_file, "w", encoding="utf-8") as file_handle:
            file_handle.write(SCHEDULED_TASK_FILE_CONTENT)
    except OSError as exc:
        logger.error(
            f"Could not create temporary scheduled task file {temp_task_file}: {exc}"
        )
        return False

    _delete_scheduled_task_windows(
        config_file,
        task_type,
        object_type,
        object_name,
    )

    # Register task from XML
    logger.info("Creating scheduled task {}".format(task_name))

    user_arg = "-User 'SYSTEM'" if not as_current_user else ""
    ps_cmd = (
        "Register-ScheduledTask -TaskName '{}' "
        "-Xml (Get-Content -LiteralPath '{}' -Raw) {}"
    ).format(task_name, temp_task_file, user_arg)

    try:
        runner = PowerShellRunner()
        exit_code, output = runner.run_script(ps_cmd, elevated=True)
        if exit_code != 0:
            logger.error(
                f"Could not create new task: cmd {ps_cmd}\nexit_code {exit_code}: {output}"
            )
            return False
    except OSError as exc:
        logger.error(f"Could not create new task: {exc}")
        return False

    for temp_file in [temp_task_file]:
        try:
            os.remove(temp_file)
        except OSError as exc:
            logger.warning(
                "Could not remove temporary task file {}: {}".format(temp_file, exc)
            )
    logger.info("Scheduled task created.")
    return True


def _delete_scheduled_task_windows(
    config_file: str,
    task_type: str,
    object_type: str,
    object_name: str,
):
    task_name = _get_scheduled_task_name_windows(
        config_file, task_type, object_type, object_name
    )

    ps_cmd = "Unregister-ScheduledTask -TaskName '{}' -Confirm:$false -ErrorAction SilentlyContinue".format(
        task_name
    )
    try:
        runner = PowerShellRunner()
        exit_code, output = runner.run_script(
            ps_cmd, elevated=True, valid_exit_codes=[0, 1]
        )
        if not exit_code in [0, 1]:
            logger.error(f"Cannot delete scheduled task {task_name}: {output}")
            return False
    except OSError as exc:
        logger.error(f"Could not run PowerShell script: {exc}")
        return False
    return True


if __name__ == "__main__":
    logger.setLevel("INFO")
    logger.addHandler(logging.StreamHandler())
    # Example usage
    config_file = "npbackup-test.conf"
    full_config = npbackup.configuration.get_default_config()
    task_type = "backup"
    object_type = "repos"
    object_name = "default"
    print(read_existing_scheduled_tasks(config_file, full_config))
    result = create_scheduled_task(
        config_file,
        task_type,
        object_type,
        object_name,
        as_current_user=True,
        interval=60,
        interval_unit="minutes",
    )
    print(f"Task creation result: {result}")
    result = delete_scheduled_task(config_file, task_type, object_type, object_name)
    print(f"Delete scheduled task result: {result}")
