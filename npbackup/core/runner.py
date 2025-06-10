#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.runner"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025061001"


from typing import Optional, Callable, Union, List, Tuple
import os
import logging
import tempfile
import pidfile
import queue
from datetime import datetime, timedelta, timezone
from functools import wraps
from copy import deepcopy
from random import randint
from command_runner import command_runner
from ofunctions.threading import threaded
from ofunctions.platform import os_arch
from ofunctions.misc import fn_name
import ntplib
from npbackup.restic_metrics import (
    restic_str_output_to_json,
    restic_json_to_prometheus,
    upload_metrics,
    write_metrics_file,
)
from npbackup.restic_wrapper import ResticRunner
from npbackup.core.restic_source_binary import get_restic_internal_binary
from npbackup.core import jobs
from npbackup.path_helper import CURRENT_DIR, BASEDIR
from npbackup.__version__ import __intname__ as NAME, version_dict
from npbackup.__debug__ import _DEBUG, exception_to_string
from npbackup.__env__ import MAX_ALLOWED_NTP_OFFSET


logger = logging.getLogger()


required_permissions = {
    "init": ["backup", "restore", "full"],
    "backup": ["backup", "restore", "full"],
    "has_recent_snapshot": ["backup", "restore", "restore_only", "full"],
    "snapshots": ["backup", "restore", "restore_only", "full"],
    "stats": ["backup", "restore", "full"],
    "ls": ["backup", "restore", "restore_only", "full"],
    "find": ["backup", "restore", "restore_only", "full"],
    "restore": ["restore", "restore_only", "full"],
    "dump": ["restore", "retore_only", "full"],
    "check": ["restore", "full"],
    "recover": ["restore", "full"],
    "list": ["full"],
    "unlock": ["full", "restore", "backup"],
    "repair": ["full"],
    "forget": ["full"],
    "housekeeping": ["full"],
    "prune": ["full"],
    "raw": ["full"],
}

# Specific operations that should never be run concurrently
locking_operations = [
    "backup",
    "repair",
    "forget",
    "prune",
    "raw",
    "unlock",
]

# Specific operations that should not lock the repository (--no-lock)
non_locking_operations = [
    "snapshots",
    "stats",
    "list",
    "ls",
    "find",
    # check should not be locking, but we definitely don't want to play with fire here
    # "check"
]


def metric_analyser(
    repo_config: dict,
    restic_result: bool,
    result_string: str,
    operation: str,
    dry_run: bool,
    append_metrics_file: bool,
    exec_time: Optional[float] = None,
    analyze_only: bool = False,
) -> Tuple[bool, bool]:
    """
    Tries to get operation success and backup to small booleans from restic output
    Returns op success, backup too small
    """
    operation_success = True
    backup_too_small = False
    metrics = []

    try:
        repo_name = repo_config.g("name")
        labels = {
            "npversion": f"{NAME}{version_dict['version']}-{version_dict['build_type']}",
            "repo_name": repo_name,
            "action": operation,
        }
        if repo_config.g("prometheus.metrics"):
            labels["instance"] = repo_config.g("prometheus.instance")
            labels["backup_job"] = repo_config.g("prometheus.backup_job")
            labels["group"] = repo_config.g("prometheus.group")
            no_cert_verify = repo_config.g("prometheus.no_cert_verify")
            destination = repo_config.g("prometheus.destination")
            prometheus_additional_labels = repo_config.g("prometheus.additional_labels")

            if isinstance(prometheus_additional_labels, dict):
                for k, v in prometheus_additional_labels.items():
                    labels[k] = v
            else:
                logger.error(
                    f"Bogus value in configuration for prometheus additional labels: {prometheus_additional_labels}"
                )
        else:
            destination = None
            no_cert_verify = False

        # We only analyse backup output of restic
        if operation == "backup":
            minimum_backup_size_error = repo_config.g(
                "backup_opts.minimum_backup_size_error"
            )
            # If result was a str, we need to transform it into json first
            if isinstance(result_string, str):
                restic_result = restic_str_output_to_json(restic_result, result_string)

            operation_success, metrics, backup_too_small = restic_json_to_prometheus(
                restic_result=restic_result,
                restic_json=restic_result,
                labels=labels,
                minimum_backup_size_error=minimum_backup_size_error,
            )
        if not operation_success or not restic_result:
            logger.error("Backend finished with errors.")

        """
        Add a metric for informing if any warning raised while executing npbackup_tasks

        CRITICAL = 50 will be 3 in this metric, but should not really exist
        ERROR = 40 will be 2 in this metric
        WARNING = 30 will be 1 in this metric
        INFO = 20 will be 0
        """
        worst_exec_level = logger.get_worst_logger_level()
        if worst_exec_level == 50:
            exec_state = 3
        elif worst_exec_level == 40:
            exec_state = 2
        elif worst_exec_level == 30:
            exec_state = 1
        else:
            exec_state = 0

        # exec_state update according to metric_analyser
        if not operation_success or backup_too_small:
            exec_state = 2

        _labels = []
        for key, value in labels.items():
            if value:
                _labels.append(f'{key.strip()}="{value.strip()}"')
        labels = ",".join(list(set(_labels)))

        metrics.append(
            f'npbackup_exec_state{{{labels},timestamp="{int(datetime.now(timezone.utc).timestamp())}"}} {exec_state}'
        )

        # Add upgrade state if upgrades activated
        upgrade_state = os.environ.get("NPBACKUP_UPGRADE_STATE", None)
        try:
            upgrade_state = int(upgrade_state)
            _labels = []
            labels["action"] = "upgrade"
            for key, value in labels.items():
                if value:
                    _labels.append(f'{key.strip()}="{value.strip()}"')
            labels = ",".join(list(set(_labels)))
            metrics.append(
                f'npbackup_exec_state{{{labels},timestamp="{int(datetime.now(timezone.utc).timestamp())}"}} {upgrade_state}'
            )
        except (ValueError, TypeError):
            pass
        if isinstance(exec_time, (int, float)):
            try:
                metrics.append(
                    f'npbackup_exec_time{{{labels},timestamp="{int(datetime.now(timezone.utc).timestamp())}"}} {exec_time}'
                )
            except (ValueError, TypeError):
                logger.warning("Cannot get exec time from environment")

        if not analyze_only:
            logger.debug("Metrics computed:\n{}".format("\n".join(metrics)))
            if destination and dry_run:
                logger.info("Dry run mode. Not sending metrics.")
            elif destination:
                logger.debug("Sending metrics to {}".format(destination))
                dest = destination.lower()
                if dest.startswith("http"):
                    if not "metrics" in dest:
                        logger.error(
                            "Destination does not contain 'metrics' keyword. Not uploading."
                        )
                        return backup_too_small
                    if not "job" in dest:
                        logger.error(
                            "Destination does not contain 'job' keyword. Not uploading."
                        )
                        return backup_too_small
                    try:
                        authentication = (
                            repo_config.g("prometheus.http_username"),
                            repo_config.g("prometheus.http_password"),
                        )
                    except KeyError:
                        logger.info("No metrics authentication present.")
                        authentication = None

                    # Fix for #150, job name needs to be unique in order to avoid overwriting previous job in push gateway
                    destination = (
                        f"{destination}___repo_name={repo_name}___action={operation}"
                    )
                    upload_metrics(destination, authentication, no_cert_verify, metrics)
                else:
                    write_metrics_file(destination, metrics, append=append_metrics_file)
            else:
                logger.debug("No metrics destination set. Not sending metrics")
    except KeyError as exc:
        logger.info("Metrics error: {}".format(exc))
        logger.debug("Trace:", exc_info=True)
    except OSError as exc:
        logger.error("Metrics OS error: ".format(exc))
        logger.debug("Trace:", exc_info=True)
    return operation_success, backup_too_small


def get_ntp_offset(ntp_server: str) -> Optional[float]:
    """
    Get current time offset from ntp server
    """
    try:
        client = ntplib.NTPClient()
        response = client.request(ntp_server)
        return response.offset
    except ntplib.NTPException as exc:
        logger.error(f"Cannot get NTP offset from {ntp_server}: {exc}")
        logger.debug("Trace:", exc_info=True)
    except Exception as exc:
        logger.error(f"Cannot reach NTP server {ntp_server}: {exc}")
        logger.debug("Trace:", exc_info=True)
    return None


class NPBackupRunner:
    """
    Wraps ResticRunner into a class that is usable by NPBackup
    """

    # NPF-SEC-00002: password commands, pre_exec and post_exec commands will be executed with npbackup privileges
    # This can lead to a problem when the config file can be written by users other than npbackup

    def __init__(self):
        self._stdout = None
        self._stderr = None

        self._is_ready = False

        self._repo_config = None

        self._dry_run = False
        self._verbose = False
        self._live_output = False
        self._json_output = False
        # struct_output is msgspec.Struct instead of json, which is less memory consuming
        # struct_output needs json_output to be True
        self._struct_output = False
        self._binary = None
        self._no_cache = False
        self._no_lock = False
        self.restic_runner = None
        self.minimum_backup_age = None
        self._exec_time = None

        # Error /warning messages to add for json output
        self.errors_for_json = []
        self.warnings_for_json = []

        self._produce_metrics = True
        self._append_metrics_file = False
        self._canceled = False

        # Allow running multiple npbackup instances
        self._concurrency = False

    @property
    def repo_config(self) -> dict:
        return self._repo_config

    @repo_config.setter
    def repo_config(self, value: dict):
        if not isinstance(value, dict):
            msg = "Bogus repo config object given"
            self.write_logs(msg, level="critical", raise_error="ValueError")
        self._repo_config = deepcopy(value)
        # Create an instance of restic wrapper
        self.create_restic_runner()

    @property
    def backend_version(self) -> bool:
        if self._is_ready:
            return self.restic_runner.binary_version
        return None

    @property
    def dry_run(self):
        return self._dry_run

    @dry_run.setter
    def dry_run(self, value):
        if not isinstance(value, bool):
            msg = f"Bogus dry_run parameter given: {value}"
            self.write_logs(msg, level="critical", raise_error="ValueError")
        self._dry_run = value

    @property
    def no_cache(self):
        return self._no_cache

    @no_cache.setter
    def no_cache(self, value):
        if not isinstance(value, bool):
            msg = f"Bogus no_cache parameter given: {value}"
            self.write_logs(msg, level="critical", raise_error="ValueError")
        self._no_cache = value

    @property
    def no_lock(self) -> bool:
        return self._no_lock

    @no_lock.setter
    def no_lock(self, value: bool):
        if not isinstance(value, bool):
            msg = f"Bogus no_lock parameter given: {value}"
            self.write_logs(msg, level="critical", raise_error="ValueError")
        self._no_lock = value

    @property
    def verbose(self):
        return self._verbose

    @verbose.setter
    def verbose(self, value):
        if not isinstance(value, bool):
            msg = f"Bogus verbose parameter given: {value}"
            self.write_logs(msg, level="critical", raise_error="ValueError")
        self._verbose = value

    @property
    def live_output(self):
        return self._live_output

    @live_output.setter
    def live_output(self, value):
        if not isinstance(value, bool):
            msg = f"Bogus live_output parameter given: {value}"
            self.write_logs(msg, level="critical", raise_error="ValueError")
        self._live_output = value

    @property
    def json_output(self):
        return self._json_output

    @json_output.setter
    def json_output(self, value):
        if not isinstance(value, bool):
            msg = f"Bogus json_output parameter given: {value}"
            self.write_logs(msg, level="critical", raise_error="ValueError")
        self._json_output = value

    @property
    def struct_output(self):
        return self._struct_output

    @struct_output.setter
    def struct_output(self, value):
        if not isinstance(value, bool):
            msg = f"Bogus struct_output parameter given: {value}"
            self.write_logs(msg, level="critical", raise_error="ValueError")
        self._struct_output = value

    @property
    def stdout(self):
        return self._stdout

    @stdout.setter
    def stdout(self, value):
        if (
            not isinstance(value, str)
            and not isinstance(value, int)
            and not isinstance(value, Callable)
            and not isinstance(value, queue.Queue)
        ):
            raise ValueError("Bogus stdout parameter given: {}".format(value))
        self._stdout = value

    @property
    def stderr(self):
        return self._stderr

    @stderr.setter
    def stderr(self, value):
        if (
            not isinstance(value, str)
            and not isinstance(value, int)
            and not isinstance(value, Callable)
            and not isinstance(value, queue.Queue)
        ):
            raise ValueError("Bogus stdout parameter given: {}".format(value))
        self._stderr = value

    @property
    def binary(self):
        return self._binary

    @binary.setter
    def binary(self, value):
        if not isinstance(value, str) or not os.path.isfile(value):
            raise ValueError("Backend binary {value} is not readable")
        self._binary = value

    @property
    def has_binary(self) -> bool:
        if self._is_ready:
            return True if self.restic_runner.binary else False
        return False

    @property
    def produce_metrics(self):
        return self._produce_metrics

    @produce_metrics.setter
    def produce_metrics(self, value):
        if not isinstance(value, bool):
            raise ValueError("produce_metrics value {value} is not a boolean")
        self._produce_metrics = value

    @property
    def concurrency(self):
        return self._concurrency

    @concurrency.setter
    def concurrency(self, value):
        if not isinstance(value, bool):
            raise ValueError("concurrency value {value} is not a boolean")
        self._concurrency = value

    @property
    def append_metrics_file(self):
        return self._append_metrics_file

    @append_metrics_file.setter
    def append_metrics_file(self, value):
        if not isinstance(value, bool):
            raise ValueError("append_metrics_file value {value} is not a boolean")
        self._append_metrics_file = value

    @property
    def exec_time(self):
        return self._exec_time

    @exec_time.setter
    def exec_time(self, value: int):
        self._exec_time = value

    def write_logs(
        self,
        msg: str,
        level: str,
        raise_error: str = None,
        ignore_additional_json: bool = False,
    ):
        """
        Write logs to log file and stdout / stderr queues if exist for GUI usage
        Also collect errors and warnings for json output
        """
        if level == "warning":
            logger.warning(msg)
        elif level == "error":
            logger.error(msg)
        elif level == "critical":
            logger.critical(msg)
        elif level == "info":
            logger.info(msg)
        elif level == "debug":
            logger.debug(msg)
        else:
            raise ValueError(f"Bogus log level given {level}")

        if msg is None:
            raise ValueError("None log message received")
        if self.stdout and (level == "info" or (level == "debug" and _DEBUG)):
            self.stdout.put(f"\n{msg}")
        if self.stderr and level in ("critical", "error", "warning"):
            self.stderr.put(f"\n{msg}")

        if not ignore_additional_json:
            if level in ("critical", "error"):
                self.errors_for_json.append(msg)
            if level == "warning":
                self.warnings_for_json.append(msg)

        if raise_error == "ValueError":
            raise ValueError(msg)
        if raise_error:
            raise Exception(msg)

    # pylint does not understand why this function does not take a self parameter
    # It's a decorator, and the inner function will have the self argument instead
    # pylint: disable=no-self-argument
    def exec_timer(fn: Callable):
        """
        Decorator that calculates time of a function execution
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            start_time = datetime.now(timezone.utc)
            # pylint: disable=E1102 (not-callable)
            result = fn(self, *args, **kwargs)
            self.exec_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            # Optional patch result with exec time
            if (
                self.restic_runner
                and self.restic_runner.json_output
                and isinstance(result, dict)
            ):
                result["exec_time"] = self.exec_time
            # pylint: disable=E1101 (no-member)
            self.write_logs(
                f"Runner took {self.exec_time} seconds for {fn.__name__}", level="info"
            )
            return result

        return wrapper

    def close_queues(fn: Callable):
        """
        Decorator that sends None to both stdout and stderr queues so GUI gets proper results
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            close_queues = kwargs.pop("__close_queues", True)
            # pylint: disable=E1102 (not-callable)
            result = fn(self, *args, **kwargs)
            if close_queues:
                if self.stdout:
                    self.stdout.put(None)
                if self.stderr:
                    self.stderr.put(None)
            return result

        return wrapper

    def is_ready(fn: Callable):
        """
        Decorator that checks if NPBackupRunner is ready to run, and logs accordingly
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            if not self._is_ready:
                # pylint: disable=E1101 (no-member)
                if fn.__name__ == "group_runner":
                    operation = kwargs.get("operation")
                else:
                    # pylint: disable=E1101 (no-member)
                    operation = fn.__name__
                msg = "Runner cannot execute, backend not ready"
                if self.stderr:
                    self.stderr.put(msg)
                if self.json_output:
                    js = {
                        "result": False,
                        "operation": operation,
                        "reason": msg,
                    }
                    return js
                self.write_logs(
                    msg,
                    level="error",
                )
                return False
            # pylint: disable=E1102 (not-callable)
            return fn(self, *args, **kwargs)

        return wrapper

    def has_permission(fn: Callable):
        """
        Decorator that checks permissions before running functions

        Possible permissions are:
        - backup:   Init, Backup, list backups and unlock
        - restore:  Init, Backup, restore, recover and list snapshots
        - restore_only: Restore only
        - full:     Full permissions

        Only one permission can be set per repo
        When no permission is set, assume full permissions
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            try:
                # When running group_runner, we need to extract operation from kwargs
                # else, operation is just the wrapped function name
                # pylint: disable=E1101 (no-member)
                if fn.__name__ == "group_runner":
                    operation = kwargs.get("operation")
                else:
                    # pylint: disable=E1101 (no-member)
                    operation = fn.__name__

                if self.repo_config:
                    current_permissions = self.repo_config.g("permissions")
                    if (
                        current_permissions
                        and not current_permissions in required_permissions[operation]
                    ):
                        self.write_logs(
                            f"Required permissions for operation '{operation}' must be one of {', '.join(required_permissions[operation])}, current permission is '{current_permissions}'",
                            level="critical",
                        )
                        raise PermissionError
                else:
                    # This happens in viewer mode
                    self.write_logs(
                        "No repo config. Ignoring permission check", level="info"
                    )
            except (IndexError, KeyError, PermissionError):
                self.write_logs(
                    "You don't have sufficient permissions", level="critical"
                )
                if self.json_output:
                    js = {
                        "result": False,
                        "operation": operation,
                        "reason": "Not enough permissions",
                    }
                    return js
                return False
            # pylint: disable=E1102 (not-callable)
            return fn(self, *args, **kwargs)

        return wrapper

    def apply_config_to_restic_runner(fn: Callable):
        """
        Decorator to update backend before every run
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            result = self._apply_config_to_restic_runner()
            if not result:
                if self.json_output:
                    js = {
                        "result": False,
                        "operation": "_apply_config_to_restic_runner",
                        "reason": "Cannot apply config to backend. See logs for more",
                    }
                    return js
                return False
            # pylint: disable=E1102 (not-callable)
            return fn(self, *args, **kwargs)

        return wrapper

    def check_concurrency(fn: Callable):
        """
        Make sure there we don't allow concurrent actions
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):

            __check_concurrency = kwargs.pop("__check_concurrency", True)

            # pylint: disable=E1101 (no-member)
            if fn.__name__ == "group_runner":
                operation = kwargs.get("operation")
            else:
                # pylint: disable=E1101 (no-member)
                operation = fn.__name__
            if __check_concurrency and operation in locking_operations:
                pid_file = os.path.join(
                    tempfile.gettempdir(), "{}.pid".format(__intname__)
                )
                try:
                    with pidfile.PIDFile(pid_file):
                        # pylint: disable=E1102 (not-callable)
                        result = fn(self, *args, **kwargs)
                except pidfile.AlreadyRunningError:
                    if self.concurrency:
                        self.write_logs(
                            f"There is already an operation running by NPBackup, but concurrency is allowed",
                            level="info",
                        )
                        # pylint: disable=E1102 (not-callable)
                        result = fn(self, *args, **kwargs)
                    else:
                        self.write_logs(
                            f"There is already an operation running by NPBackup. Will not launch operation {operation} to avoid concurrency",
                            level="critical",
                        )
                        return False
            else:
                result = fn(  # pylint: disable=E1102 (not-callable)
                    self, *args, **kwargs
                )
            return result

        return wrapper

    def no_aquire_lock(fn: Callable):
        """
        Don't lock some operations
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            # pylint: disable=E1101 (no-member)
            if fn.__name__ == "group_runner":
                operation = kwargs.get("operation")
            else:
                # pylint: disable=E1101 (no-member)
                operation = fn.__name__

            no_lock = self._no_lock
            if operation in non_locking_operations:
                self._no_lock = True
            # pylint: disable=E1102 (not-callable)
            result = fn(self, *args, **kwargs)
            self._no_lock = no_lock
            return result

        return wrapper

    def catch_exceptions(fn: Callable):
        """
        Catch any exception and log it so we don't loose exceptions in thread
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            try:
                # pylint: disable=E1102 (not-callable)
                return fn(self, *args, **kwargs)
            except Exception as exc:
                # pylint: disable=E1101 (no-member)
                if fn.__name__ == "group_runner":
                    operation = kwargs.get("operation")
                else:
                    # pylint: disable=E1101 (no-member)
                    operation = fn.__name__
                self.write_logs(
                    f"Runner: Function {operation} failed with: {exc}", level="error"
                )
                logger.error("Trace:", exc_info=True)

                # In case of error, we really need to write metrics
                # pylint: disable=E1101 (no-member)
                metric_analyser(
                    self.repo_config,
                    False,
                    self.restic_runner.backup_result_content,
                    fn.__name__,
                    self.dry_run,
                    self.append_metrics_file,
                    self.exec_time,
                    analyze_only=False,
                )
                # We need to reset backup result content once it's parsed
                self.restic_runner.backup_result_content = None
                # We need to append to metric file once we begin writing to it
                self.append_metrics_file = True
                if self.json_output:
                    js = {
                        "result": False,
                        "operation": operation,
                        "reason": f"Runner caught exception: {exception_to_string(exc)}",
                    }
                    return js
                return False

        return wrapper

    def metrics(fn: Callable):
        """
        Write prometheus metrics
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            # pylint: disable=E1102 (not-callable)
            result = fn(self, *args, **kwargs)
            # pylint: disable=E1101 (no-member)
            if self.produce_metrics:
                metric_analyser(
                    self.repo_config,
                    result,
                    self.restic_runner.backup_result_content,
                    fn.__name__,
                    self.dry_run,
                    self.append_metrics_file,
                    self.exec_time,
                    analyze_only=False,
                )
                # We need to reset backup result content once it's parsed
                self.restic_runner.backup_result_content = None
                # We need to append to metric file once we begin writing to it
                self.append_metrics_file = True
            else:
                self.write_logs(
                    f"Metrics disabled for call {fn.__name__}", level="debug"
                )
            return result

        return wrapper

    def create_restic_runner(self) -> bool:
        can_run = True
        try:
            repository = self.repo_config.g("repo_uri")
            if not repository:
                raise KeyError
        except (KeyError, AttributeError):
            self.write_logs("Repo cannot be empty", level="error")
            can_run = False
        try:
            password = self.repo_config.g("repo_opts.repo_password")
        except (KeyError, AttributeError):
            self.write_logs("Repo password cannot be empty", level="error")
            can_run = False
        if not password or password == "":
            try:
                password_command = self.repo_config.g("repo_opts.repo_password_command")
                if password_command and password_command != "":
                    # NPF-SEC-00003: Avoid password command divulgation
                    cr_logger = logging.getLogger("command_runner")
                    cr_loglevel = cr_logger.getEffectiveLevel()
                    cr_logger.setLevel(logging.ERROR)
                    exit_code, output = command_runner(
                        password_command, shell=True, timeout=30
                    )
                    cr_logger.setLevel(cr_loglevel)
                    if exit_code != 0 or output == "":
                        self.write_logs(
                            f"Password command failed to produce output:\n{output}",
                            level="error",
                        )
                        can_run = False
                    elif "\n" in output.strip():
                        self.write_logs(
                            "Password command returned multiline content instead of a string",
                            level="error",
                        )
                        can_run = False
                    else:
                        password = output
                else:
                    self.write_logs(
                        "No password nor password command given. Repo password cannot be empty",
                        level="error",
                    )
                    can_run = False
            except KeyError:
                self.write_logs(
                    "No password nor password command given. Repo password cannot be empty",
                    level="error",
                )
                can_run = False
        self._is_ready = can_run
        if not can_run:
            return False
        self.restic_runner = ResticRunner(
            repository=repository,
            password=password,
            binary_search_paths=[BASEDIR, CURRENT_DIR],
        )

    def _apply_config_to_restic_runner(self) -> bool:
        if not isinstance(self.restic_runner, ResticRunner):
            self.write_logs("Backend not ready", level="error")
            return False
        try:
            if self.repo_config.g("repo_opts.upload_speed"):
                self.restic_runner.limit_upload = self.repo_config.g(
                    "repo_opts.upload_speed"
                )
        except KeyError:
            pass
        except ValueError:
            self.write_logs("Bogus upload limit given.", level="error")
        try:
            if self.repo_config.g("repo_opts.download_speed"):
                self.restic_runner.limit_download = self.repo_config.g(
                    "repo_opts.download_speed"
                )
        except KeyError:
            pass
        except ValueError:
            self.write_logs("Bogus download limit given.", level="error")
        try:
            if self.repo_config.g("repo_opts.backend_connections"):
                self.restic_runner.backend_connections = self.repo_config.g(
                    "repo_opts.backend_connections"
                )
        except KeyError:
            pass
        except ValueError:
            self.write_logs("Bogus backend connections value given.", level="error")
        try:
            if self.repo_config.g("backup_opts.priority"):
                self.restic_runner.priority = self.repo_config.g("backup_opts.priority")
        except KeyError:
            pass
        except ValueError:
            self.write_logs("Bogus backup priority in config file.", level="warning")
        try:
            if self.repo_config.g("backup_opts.ignore_cloud_files"):
                self.restic_runner.ignore_cloud_files = self.repo_config.g(
                    "backup_opts.ignore_cloud_files"
                )
        except KeyError:
            pass
        except ValueError:
            self.write_logs("Bogus ignore_cloud_files value given", level="warning")

        try:
            if self.repo_config.g("backup_opts.additional_parameters"):
                self.restic_runner.additional_parameters = self.repo_config.g(
                    "backup_opts.additional_parameters"
                )
                try:
                    self.restic_runner.additional_parameters = os.path.expanduser(
                        self.restic_runner.additional_parameters
                    )
                    self.restic_runner.additional_parameters = os.path.expandvars(
                        self.restic_runner.additional_parameters
                    )
                except OSError:
                    self.write_logs(
                        f"Failed expansion for additional parameters: {self.restic_runner.additional_parameters}",
                        level="error",
                    )
        except KeyError:
            pass
        except ValueError:
            self.write_logs("Bogus additional parameters given", level="warning")

        try:
            env_variables = self.repo_config.g("env.env_variables")
            if not isinstance(env_variables, list):
                env_variables = [env_variables]
        except KeyError:
            env_variables = []
        try:
            encrypted_env_variables = self.repo_config.g("env.encrypted_env_variables")
            if not isinstance(encrypted_env_variables, list):
                encrypted_env_variables = [encrypted_env_variables]
        except KeyError:
            encrypted_env_variables = []

        expanded_env_vars = {}
        if isinstance(env_variables, list):
            for env_variable in env_variables:
                if isinstance(env_variable, dict):
                    for k, v in env_variable.items():
                        try:
                            v = os.path.expanduser(v)
                            v = os.path.expandvars(v)
                            expanded_env_vars[k.strip()] = v.strip()
                        except Exception as exc:
                            self.write_logs(
                                f"Cannot expand environment variable {k}: {exc}",
                                level="error",
                            )
                            logger.debug("Trace:", exc_info=True)

        expanded_encrypted_env_vars = {}
        if isinstance(encrypted_env_variables, list):
            for encrypted_env_variable in encrypted_env_variables:
                if isinstance(encrypted_env_variable, dict):
                    for k, v in encrypted_env_variable.items():
                        try:
                            v = os.path.expanduser(v)
                            v = os.path.expandvars(v)
                            expanded_encrypted_env_vars[k.strip()] = v.strip()
                        except Exception as exc:
                            self.write_logs(
                                f"Cannot expand encrypted environment variable {k}: {exc}",
                                level="error",
                            )
                            logger.debug("Trace:", exc_info=True)
        try:
            self.restic_runner.environment_variables = expanded_env_vars
            self.restic_runner.encrypted_environment_variables = (
                expanded_encrypted_env_vars
            )
        except ValueError:
            self.write_logs(
                "Cannot initialize additional environment variables", level="error"
            )

        try:
            self.minimum_backup_age = int(
                self.repo_config.g("repo_opts.minimum_backup_age")
            )
        except (KeyError, ValueError, TypeError):
            # In doubt, launch the backup regardless of last backup age
            self.minimum_backup_age = 0

        self.restic_runner.verbose = self.verbose
        self.restic_runner.dry_run = self.dry_run
        self.restic_runner.no_cache = self.no_cache
        self.restic_runner.no_lock = self.no_lock
        self.restic_runner.live_output = self.live_output
        self.restic_runner.json_output = self.json_output
        self.restic_runner.struct_output = self.struct_output
        self.restic_runner.stdout = self.stdout
        self.restic_runner.stderr = self.stderr
        if self.binary:
            self.restic_runner.binary = self.binary

        if self.restic_runner.binary is None:
            # Let's try to load our internal binary for dev purposes
            arch = os_arch()
            binary = get_restic_internal_binary(arch)
            if binary:
                self.restic_runner.binary = binary
            else:
                self.restic_runner._get_binary()
                if self.restic_runner.binary is None:
                    self.write_logs("No backend binary found", level="error")
                    self._is_ready = False
                    return False

        # Add currently in use backend binary to environment variables
        # This is useful for additional parameters / scripts that would directly call the backend
        try:
            os.environ["NPBACKUP_BACKEND_BINARY"] = str(self.restic_runner.binary)
        except OSError:
            self.write_logs(
                f"Cannot set env variable NPBACKUP_BACKEND_BINARY to {self.binary}",
                level="error",
            )
        return True

    def convert_to_json_output(
        self,
        result: Union[bool, dict],
        output: str = None,
    ):
        if self.json_output:
            if isinstance(result, dict):
                js = result
                if not "additional_error_info" in js.keys():
                    js["additional_error_info"] = []
                if not "additional_warning_info" in js.keys():
                    js["additional_warning_info"] = []
            else:
                js = {
                    "result": result,
                    "operation": fn_name,
                    "additional_error_info": [],
                    "additional_warning_info": [],
                }
                if result:
                    js["output"] = output
                else:
                    js["reason"] = output
            if self.errors_for_json:
                js["additional_error_info"] += self.errors_for_json
            if self.warnings_for_json:
                js["additional_warning_info"] += self.warnings_for_json
            if not js["additional_error_info"]:
                js.pop("additional_error_info")
            if not js["additional_warning_info"]:
                js.pop("additional_warning_info")
            return js
        return result

    def check_source_files_present(self, source_type: Optional[str], paths):
        """
        Checks if all specified paths actually exist and are readable
        since restic won't do so https://github.com/restic/restic/issues/4467
        """
        paths_must_be_readable = []
        all_files_are_reabable = True

        if not source_type:
            source_type = "folder_list"
        if source_type == "folder_list":
            paths_must_be_readable = paths
        if source_type in ["files_from_verbatim", "files_from_raw"]:
            for path in paths:
                try:
                    with open(path, "r") as path_file:
                        paths_must_be_readable += path_file.readlines()
                except OSError as exc:
                    self.write_logs(
                        f"Cannot open file {path} for reading: {exc}", level="error"
                    )
                    all_files_are_reabable = False
        for path in paths_must_be_readable:
            if source_type == "files_from_raw":
                path = path.strip("\x00")
            path = path.strip()
            if not os.path.exists(path) or not os.access(path, os.R_OK):
                self.write_logs(
                    f"Path {path} does not exist or is not readable",
                    level="error",
                )
                all_files_are_reabable = False
        return all_files_are_reabable

    ###########################
    # ACTUAL RUNNER FUNCTIONS #
    ###########################

    # Decorator order is important
    # Since we want a concurrent.futures.Future result, we need to put the @threaded decorator
    # before any other decorator that would change the results
    # @close_queues should come second, since we want to close queues only once the lower functions are finished
    # @metrics must be called before @exec_timer, since the metrics will contain exec_time
    # @exec_timer is next, since we want to calc max exec time (except the close_queues and threaded overhead)
    # All others are in no particular order
    # but @catch_exceptions should come last, since we aren't supposed to have errors in decorators

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def init(self) -> bool:
        self.write_logs(f"Initializing repo {self.repo_config.g('name')}", level="info")
        return self.restic_runner.init()

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @no_aquire_lock
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def snapshots(self, id: str = None, errors_allowed: bool = False) -> Optional[dict]:
        self.write_logs(
            f"Listing snapshots of repo {self.repo_config.g('name')}", level="info"
        )
        snapshots = self.restic_runner.snapshots(id=id, errors_allowed=errors_allowed)
        return snapshots

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @no_aquire_lock
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def list(self, subject: str) -> Optional[dict]:
        self.write_logs(
            f"Listing {subject} objects of repo {self.repo_config.g('name')}",
            level="info",
        )
        return self.restic_runner.list(subject)

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @no_aquire_lock
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def find(self, path: str) -> bool:
        self.write_logs(
            f"Searching for path {path} in repo {self.repo_config.g('name')}",
            level="info",
        )
        result = self.restic_runner.find(path=path)
        return self.convert_to_json_output(result, None)

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @no_aquire_lock
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def ls(self, snapshot: str) -> Optional[dict]:
        self.write_logs(
            f"Showing content of snapshot {snapshot} in repo {self.repo_config.g('name')}",
            level="info",
        )
        result = self.restic_runner.ls(snapshot)
        return result

    @threaded
    @close_queues
    @catch_exceptions
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def has_recent_snapshot(self) -> bool:
        """
        Checks for backups in timespan
        Returns True or False if found or not
        Returns None if no information is available
        """
        if self.minimum_backup_age == 0:
            self.write_logs("No minimal backup age set set.", level="info")

        self.write_logs(
            f"Searching for a backup newer than {str(timedelta(minutes=self.minimum_backup_age))} ago",
            level="info",
        )
        # Temporarily disable verbose and enable json result
        self.restic_runner.verbose = False
        # Temporarily disable CLI live output which we don't really need here
        self.restic_runner.live_output = False
        data = self.restic_runner.has_recent_snapshot(self.minimum_backup_age)
        self.restic_runner.verbose = self.verbose
        self.restic_runner.live_output = self.live_output
        if self.json_output:
            return data

        # has_recent_snapshot returns a tuple when not self.json_output
        result = data[0]
        backup_tz = data[1]
        if result:
            self.write_logs(
                f"Most recent backup in repo {self.repo_config.g('name')} is from {backup_tz}",
                level="info",
            )
        elif result is False and backup_tz == datetime(1, 1, 1, 0, 0):
            self.write_logs(
                f"No snapshots found in repo {self.repo_config.g('name')}.",
                level="info",
            )
        elif result is False:
            self.write_logs(
                f"No recent backup found in repo {self.repo_config.g('name')}. Newest is from {backup_tz}",
                level="info",
            )
        elif result is None:
            self.write_logs(
                "Cannot connect to repository or repository empty.", level="error"
            )
        return result, backup_tz

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def backup(
        self,
        force: bool = False,
        read_from_stdin: bool = False,
        stdin_filename: str = None,
    ) -> bool:
        """
        Run backup after checking if no recent backup exists, unless force == True
        """

        start_time = datetime.now(timezone.utc)

        stdin_from_command = self.repo_config.g("backup_opts.stdin_from_command")
        if not stdin_filename:
            stdin_filename = self.repo_config.g("backup_opts.stdin_filename")
            if not stdin_filename:
                stdin_filename = "stdin.data"
        source_type = self.repo_config.g("backup_opts.source_type")
        if source_type in (
            None,
            "folder_list",
            "files_from",
            "files_from_verbatim",
            "files_from_raw",
        ):
            # Preflight checks
            paths = self.repo_config.g("backup_opts.paths")
            if not paths:
                msg = (
                    f"No paths to backup defined for repo {self.repo_config.g('name')}"
                )
                self.write_logs(msg, level="critical")
                return self.convert_to_json_output(False, msg)

            # Make sure we convert paths to list if only one path is give
            # Also make sure we remove trailing and ending spaces
            try:
                if not isinstance(paths, list):
                    paths = [paths]
                paths = [path.strip() for path in paths]
                for path in paths:
                    if path == self.repo_config.g("repo_uri"):
                        msg = f"You cannot backup source into it's own path in repo {self.repo_config.g('name')}. No inception allowed !"
                        self.write_logs(msg, level="critical")
                        return self.convert_to_json_output(False, msg)
            except (AttributeError, KeyError):
                msg = f"No backup source given for repo {self.repo_config.g('name')}"
                self.write_logs(msg, level="critical")
                return self.convert_to_json_output(False, msg)

            # MSWindows does not support one-file-system option
            exclude_patterns = self.repo_config.g("backup_opts.exclude_patterns")
            if not isinstance(exclude_patterns, list):
                exclude_patterns = [exclude_patterns]

            exclude_files = self.repo_config.g("backup_opts.exclude_files")
            if not isinstance(exclude_files, list):
                exclude_files = [exclude_files]

            excludes_case_ignore = self.repo_config.g(
                "backup_opts.excludes_case_ignore"
            )
            exclude_caches = self.repo_config.g("backup_opts.exclude_caches")

            exclude_files_larger_than = self.repo_config.g(
                "backup_opts.exclude_files_larger_than"
            )
            one_file_system = (
                self.repo_config.g("backup_opts.one_file_system")
                if os.name != "nt"
                else False
            )
            use_fs_snapshot = self.repo_config.g("backup_opts.use_fs_snapshot")

        pre_exec_commands = self.repo_config.g("backup_opts.pre_exec_commands")
        pre_exec_per_command_timeout = self.repo_config.g(
            "backup_opts.pre_exec_per_command_timeout"
        )
        pre_exec_failure_is_fatal = self.repo_config.g(
            "backup_opts.pre_exec_failure_is_fatal"
        )

        post_exec_commands = self.repo_config.g("backup_opts.post_exec_commands")
        post_exec_per_command_timeout = self.repo_config.g(
            "backup_opts.post_exec_per_command_timeout"
        )
        post_exec_failure_is_fatal = self.repo_config.g(
            "backup_opts.post_exec_failure_is_fatal"
        )

        # Make sure we convert tag to list if only one tag is given
        try:
            tags = self.repo_config.g("backup_opts.tags")
            if not isinstance(tags, list):
                tags = [tags]
        except KeyError:
            tags = None

        additional_backup_only_parameters = None
        try:
            if self.repo_config.g("backup_opts.additional_backup_only_parameters"):
                additional_backup_only_parameters = self.repo_config.g(
                    "backup_opts.additional_backup_only_parameters"
                )
                try:
                    additional_backup_only_parameters = os.path.expanduser(
                        additional_backup_only_parameters
                    )
                    additional_backup_only_parameters = os.path.expandvars(
                        additional_backup_only_parameters
                    )
                except OSError:
                    self.write_logs(
                        f"Failed expansion for additional backup parameters: {additional_backup_only_parameters}",
                        level="error",
                    )
        except KeyError:
            pass
        except ValueError:
            self.write_logs("Bogus additional backup parameters given", level="warning")

        if not force:
            # Check if backup is required, no need to be verbose, but we'll make sure we don't get a json result here
            self.restic_runner.verbose = False
            json_output = self.json_output
            self.json_output = False
            # Since we don't want to close queues nor create a subthread, we need to change behavior here
            # pylint: disable=E1123 (unexpected-keyword-arg)
            has_recent_snapshots, _ = self.has_recent_snapshot(
                __close_queues=False, __no_threads=True
            )
            self.json_output = json_output
            # We also need to "reapply" the json setting to backend
            self.restic_runner.json_output = json_output
            if has_recent_snapshots:
                msg = "No backup necessary"
                self.write_logs(msg, level="info")
                return self.convert_to_json_output(True, msg)
            self.restic_runner.verbose = self.verbose

        # Run backup preps here
        if source_type in (
            None,
            "folder_list",
            "files_from",
            "files_from_verbatim",
            "files_from_raw",
        ):
            if source_type not in ["folder_list", None]:
                if not source_type or source_type == "folder_list":
                    pretty_source_type = "files and folders"
                else:
                    pretty_source_type = " ".join(source_type.split("_"))
                self.write_logs(
                    f"Running backup of {pretty_source_type}: {paths} to repo {self.repo_config.g('name')}",
                    level="info",
                )
            else:
                self.write_logs(
                    f"Running backup of {paths} to repo {self.repo_config.g('name')}",
                    level="info",
                )
        elif source_type == "stdin_from_command" and stdin_from_command:
            self.write_logs(
                f"Running backup of given command stdout as name {stdin_filename} to repo {self.repo_config.g('name')}",
                level="info",
            )
        elif read_from_stdin:
            self.write_logs(
                f"Running backup of piped stdin data as name {stdin_filename} to repo {self.repo_config.g('name')}",
                level="info",
            )
        else:
            raise ValueError(f"Unknown source type given: {source_type}")

        def _exec_commands(
            exec_type: str,
            command_list: List[str],
            per_command_timeout: int,
            failure_is_fatal: bool,
        ):
            commands_success = True
            if command_list:
                for command in command_list:
                    exit_code, output = command_runner(
                        command, shell=True, timeout=per_command_timeout
                    )
                    if exit_code != 0:
                        msg = f"{exec_type}-execution of command {command} failed with:\n{output}"
                        commands_success = False
                        if not failure_is_fatal:
                            self.write_logs(msg, level="warning")
                        else:
                            self.write_logs(msg, level="error")
                            self.write_logs(
                                "Stopping further execution due to fatal error",
                                level="error",
                            )
                            break
                    else:
                        self.write_logs(
                            f"{exec_type}-execution of command {command} succeeded with:\n{output}",
                            level="info",
                        )
            return commands_success

        pre_exec_commands_success = _exec_commands(
            "Pre",
            pre_exec_commands,
            pre_exec_per_command_timeout,
            pre_exec_failure_is_fatal,
        )

        if pre_exec_failure_is_fatal and not pre_exec_commands_success:
            # This logic is more readable than it's negation, let's just keep it
            result = False
            post_exec_commands_success = None
        else:
            if source_type in (
                None,
                "folder_list",
                "files_from_verbatim",
                "files_from_raw",
            ):
                all_files_present = self.check_source_files_present(source_type, paths)
                if not all_files_present:
                    self.write_logs(
                        f"Not all files/folders are present in backup source",
                        level="error",
                    )

            # Run actual backup here
            if source_type in (
                None,
                "folder_list",
                "files_from",
                "files_from_verbatim",
                "files_from_raw",
            ):
                result = self.restic_runner.backup(
                    paths=paths,
                    source_type=source_type,
                    exclude_patterns=exclude_patterns,
                    exclude_files=exclude_files,
                    excludes_case_ignore=excludes_case_ignore,
                    exclude_caches=exclude_caches,
                    exclude_files_larger_than=exclude_files_larger_than,
                    one_file_system=one_file_system,
                    use_fs_snapshot=use_fs_snapshot,
                    tags=tags,
                    additional_backup_only_parameters=additional_backup_only_parameters,
                )
            elif source_type == "stdin_from_command" and stdin_from_command:
                result = self.restic_runner.backup(
                    stdin_from_command=stdin_from_command,
                    stdin_filename=stdin_filename,
                    tags=tags,
                    additional_backup_only_parameters=additional_backup_only_parameters,
                )
            elif read_from_stdin:
                result = self.restic_runner.backup(
                    read_from_stdin=read_from_stdin,
                    stdin_filename=stdin_filename,
                    tags=tags,
                    additional_backup_only_parameters=additional_backup_only_parameters,
                )
            else:
                raise ValueError("Bogus backup source type given")

            self.write_logs(
                f"Restic output:\n{self.restic_runner.backup_result_content}",
                level="debug",
            )

            post_exec_commands_success = _exec_commands(
                "Post",
                post_exec_commands,
                post_exec_per_command_timeout,
                post_exec_failure_is_fatal,
            )

        # Extract backup size from result_string
        # Metrics will not be in json format, since we need to diag cloud issues until
        # there is a fix for https://github.com/restic/restic/issues/4155
        analyser_result, backup_too_small = metric_analyser(
            self.repo_config,
            result,
            self.restic_runner.backup_result_content,
            "backup",
            self.restic_runner.dry_run,
            self.append_metrics_file,
            self.exec_time,
            analyze_only=True,
        )

        if backup_too_small:
            self.write_logs(
                "Backup is smaller than configured minmium backup size", level="error"
            )

        operation_result = (
            result
            and analyser_result
            and pre_exec_commands_success
            and post_exec_commands_success
            and not backup_too_small
        )
        msg = f"Operation finished with {'success' if operation_result else 'failure'}"
        self.write_logs(
            msg,
            level="info" if operation_result else "error",
            ignore_additional_json=True,
        )

        if operation_result:
            post_backup_housekeeping_percent_chance = self.repo_config.g(
                "backup_opts.post_backup_housekeeping_percent_chance"
            )
            post_backup_housekeeping_interval = self.repo_config.g(
                "backup_opts.post_backup_houskeeping_interval"
            )
            if (
                post_backup_housekeeping_percent_chance
                or post_backup_housekeeping_interval
            ):
                post_backup_op = "housekeeping"

                current_permissions = self.repo_config.g("permissions")
                if (
                    current_permissions
                    and not current_permissions in required_permissions[post_backup_op]
                ):
                    self.write_logs(
                        f"Required permissions for post backup housekeeping must be one of {', '.join(required_permissions[post_backup_op])}, current permission is '{current_permissions}'",
                        level="critical",
                    )
                    raise PermissionError
                elif jobs.schedule_on_chance_or_interval(
                    "housekeeping-after-backup",
                    post_backup_housekeeping_percent_chance,
                    post_backup_housekeeping_interval,
                ):
                    self.write_logs("Running housekeeping after backup", level="info")
                    # Housekeeping after backup needs to run without threads
                    # We need to keep the queues open since we need to report back to GUI
                    # Also, we need to disable concurrency check since we already did
                    # for backup, and concurrency check would fail for unlock, forget and prune
                    # pylint: disable=E1123 (unexpected-keyword-arg)
                    housekeeping_result = self.housekeeping(
                        __no_threads=True,
                        __close_queues=True,
                        __check_concurrency=False,
                        check_concurrency=False,
                    )
                    if not housekeeping_result:
                        self.write_logs(
                            "After backup housekeeping failed", level="error"
                        )

        # housekeeping has it's own metrics, so we won't include them in the operational result of the backup
        if not operation_result:
            # patch result if json
            if isinstance(result, dict):
                result["result"] = False
            else:
                result = False
            # Don't overwrite backend output in case of failure
            return self.convert_to_json_output(result)
        return self.convert_to_json_output(result, msg)

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def restore(self, snapshot: str, target: str, restore_includes: List[str]) -> bool:
        self.write_logs(f"Launching restore to {target}", level="info")

        additional_restore_only_parameters = None
        try:
            if self.repo_config.g("backup_opts.additional_restore_only_parameters"):
                additional_restore_only_parameters = self.repo_config.g(
                    "backup_opts.additional_restore_only_parameters"
                )
                try:
                    additional_restore_only_parameters = os.path.expanduser(
                        additional_restore_only_parameters
                    )
                    additional_restore_only_parameters = os.path.expandvars(
                        additional_restore_only_parameters
                    )
                except OSError:
                    self.write_logs(
                        f"Failed expansion for additional backup parameters: {additional_restore_only_parameters}",
                        level="error",
                    )
        except KeyError:
            pass
        except ValueError:
            self.write_logs("Bogus additional backup parameters given", level="warning")

        return self.restic_runner.restore(
            snapshot=snapshot,
            target=target,
            includes=restore_includes,
            additional_restore_only_parameters=additional_restore_only_parameters,
        )

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def forget(
        self, snapshots: Optional[Union[List[str], str]] = None, use_policy: bool = None
    ) -> bool:
        if snapshots:
            self.write_logs(f"Forgetting snapshots {snapshots}", level="info")
            result = self.restic_runner.forget(snapshots)
        elif use_policy:
            # NPF-SEC-00010
            # Let's check if we can get a valid NTP server offset
            # If offset is too big, we won't apply policy
            # Offset should not be higher than 10 minutes, eg 600 seconds
            ntp_server = self.repo_config.g("repo_opts.retention_policy.ntp_server")
            if ntp_server:
                self.write_logs(
                    f"Checking time against ntp server {ntp_server}", level="info"
                )
                offset = get_ntp_offset(ntp_server)
                if not offset or offset > float(MAX_ALLOWED_NTP_OFFSET):
                    if not offset:
                        msg = f"Offset cannot be obtained from NTP server {ntp_server}"
                    elif offset > float(MAX_ALLOWED_NTP_OFFSET):
                        msg = f"Offset from NTP server {ntp_server} is too high: {offset} seconds. Won't apply policy"
                        self.write_logs(msg, level="critical")
                        return self.convert_to_json_output(False, msg)

            # Build policy from config
            policy = {}
            for entry in ["last", "hourly", "daily", "weekly", "monthly", "yearly"]:
                value = self.repo_config.g(f"repo_opts.retention_policy.{entry}")
                if value:
                    if (
                        not self.repo_config.g("repo_opts.retention_policy.keep_within")
                        or entry == "last"
                    ):
                        policy[f"keep-{entry}"] = value
                    else:
                        # We need to add a type value for keep-within
                        unit = entry[0:1]
                        # Patch weeks to days since restic --keep-within doesn't support weeks
                        if unit == "w":
                            unit = "d"
                            value = value * 7
                        policy[f"keep-within-{entry}"] = f"{value}{unit}"
            keep_tags = self.repo_config.g("repo_opts.retention_policy.tags")
            if not isinstance(keep_tags, list) and keep_tags:
                keep_tags = [keep_tags]
                policy["keep-tags"] = keep_tags
            # Fool proof, don't run without policy, or else we'll get
            if not policy:
                msg = "Empty retention policy. Won't run"
                self.write_logs(msg, level="error")
                return self.convert_to_json_output(False, msg)

            # Convert group by to list
            group_by = []
            for entry in ["host", "paths", "tags"]:
                if self.repo_config.g(f"repo_opts.retention_policy.group_by_{entry}"):
                    group_by.append(entry)

            self.write_logs(
                f"Forgetting snapshots using retention policy: {policy}", level="info"
            )
            result = self.restic_runner.forget(policy=policy, group_by=group_by)
        else:
            self.write_logs(
                "Bogus options given to forget: snapshots={snapshots}, policy={policy}",
                level="critical",
                raise_error=True,
            )
            result = False
        return self.convert_to_json_output(result)

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def housekeeping(self, check_concurrency: bool = True) -> bool:
        """
        Runs unlock, check, forget and prune in one go
        """
        self.write_logs("Running housekeeping", level="info")
        # Add special keywords __no_threads since we're already threaded in housekeeping function
        # Also, pass it as kwargs to make linter happy
        kwargs = {
            "__no_threads": True,
            "__close_queues": False,
            "__check_concurrency": check_concurrency,
        }
        # pylint: disable=E1123 (unexpected-keyword-arg)

        # We need to construct our own result here since this is a wrapper for 3 different subcommandzsz
        js = {
            "result": True,
            "operation": fn_name(0),
            "args": None,
        }

        check_result = None
        forget_result = None
        prune_result = None

        unlock_result = self.unlock(**kwargs)
        if (isinstance(unlock_result, bool) and unlock_result) or (
            isinstance(unlock_result, dict) and unlock_result["result"]
        ):
            check_result = self.check(**kwargs, read_data=False)
            if (isinstance(check_result, bool) and check_result) or (
                isinstance(check_result, dict) and check_result["result"]
            ):
                # pylint: disable=E1123 (unexpected-keyword-arg)
                forget_result = self.forget(use_policy=True, **kwargs)
                if (isinstance(forget_result, bool) and forget_result) or (
                    isinstance(forget_result, dict) and forget_result["result"]
                ):
                    # pylint: disable=E1123 (unexpected-keyword-arg)
                    prune_result = self.prune(**kwargs)
                    result = prune_result
                else:
                    self.write_logs(
                        f"Forget failed. Won't continue housekeeping on repo {self.repo_config.g('name')}",
                        level="error",
                    )
                    result = forget_result
            else:
                self.write_logs(
                    f"Check failed. Won't continue housekeeping on repo {self.repo_config.g('name')}",
                    level="error",
                )
                result = check_result
        else:
            self.write_logs(
                f"Unlock failed. Won't continue housekeeping in repo {self.repo_config.g('name')}",
                level="error",
            )
            result = unlock_result
        if isinstance(result, bool):
            js["result"] = result
        else:
            js["detail"] = {
                "unlock": unlock_result,
                "check": check_result,
                "forget": forget_result,
                "prune": prune_result,
            }
        return self.convert_to_json_output(js)

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def check(self, read_data: bool = True) -> bool:
        if read_data:
            self.write_logs(
                f"Running full data check of repository {self.repo_config.g('name')}",
                level="info",
            )
        else:
            self.write_logs(
                f"Running metadata consistency check of repository {self.repo_config.g('name')}",
                level="info",
            )
        return self.restic_runner.check(read_data)

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def prune(self, prune_max: bool = False) -> bool:
        self.write_logs(
            f"Pruning snapshots for repo {self.repo_config.g('name')}{' at maximum efficiency' if prune_max else ''}",
            level="info",
        )
        max_repack_size = self.repo_config.g("repo_opts.prune_max_repack_size")
        if prune_max:
            max_unused = self.repo_config.g("repo_opts.prune_max_unused")
            result = self.restic_runner.prune(
                max_unused=max_unused, max_repack_size=max_repack_size
            )
        else:
            result = self.restic_runner.prune(max_repack_size=max_repack_size)
        return result

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def repair(self, subject: str, pack_ids: str = None) -> bool:
        self.write_logs(
            f"Repairing {subject} in repo {self.repo_config.g('name')}", level="info"
        )
        return self.restic_runner.repair(subject, pack_ids)

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def recover(self) -> bool:
        self.write_logs(
            f"Recovering snapshots in repo {self.repo_config.g('name')}", level="info"
        )
        return self.restic_runner.recover()

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def unlock(self) -> bool:
        self.write_logs(f"Unlocking repo {self.repo_config.g('name')}", level="info")
        return self.restic_runner.unlock()

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def dump(self, snapshot: str, path: str) -> bool:
        self.write_logs(
            f"Dumping {path} from {self.repo_config.g('name')} snapshot {snapshot}",
            level="info",
        )
        result = self.restic_runner.dump(snapshot, path)
        return result

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def stats(self, subject: str = None) -> bool:
        self.write_logs(
            f"Getting stats of repo {self.repo_config.g('name')}", level="info"
        )
        result = self.restic_runner.stats(subject)
        return result

    @threaded
    @close_queues
    @catch_exceptions
    @metrics
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def raw(self, command: str) -> bool:
        self.write_logs(f"Running raw command: {command}", level="info")
        return self.restic_runner.raw(command=command)

    @threaded
    @close_queues
    @catch_exceptions
    @exec_timer
    def group_runner(self, repo_config_list: List, operation: str, **kwargs) -> bool:
        group_result = True

        # Make sure we don't close the stdout/stderr queues when running multiple operations
        # Also make sure we don't thread functions
        kwargs = {
            **kwargs,
            **{
                "__close_queues": False,
                "__no_threads": True,
            },
        }

        js = {"result": None, "group": True, "output": []}

        for repo_config in repo_config_list:
            if self._canceled:
                self.write_logs("Operations canceled", level="info")
                group_result = False
                break
            repo_name = repo_config.g("name")
            self.write_logs(f"Running {operation} for repo {repo_name}", level="info")
            self.repo_config = repo_config
            try:
                result = self.__getattribute__(operation)(**kwargs)
            except Exception as exc:
                logger.error(
                    f"Operation {operation} for repo {repo_name} failed with: {exc}"
                )
                logger.debug("Trace", exc_info=True)
                result = False
            if self.json_output:
                js["output"].append({repo_name: result})
            else:
                if result:
                    self.write_logs(
                        f"Finished {operation} for repo {repo_name}", level="info"
                    )
                else:
                    self.write_logs(
                        f"Operation {operation} failed for repo {repo_name}",
                        level="error",
                    )
            if not result:
                group_result = False
        self.write_logs("Finished execution of group operations", level="info")
        if self.json_output:
            js["result"] = group_result
            return js
        return group_result

    def cancel(self):
        """
        This is just a shorthand to make sure restic_wrapper receives a cancel signal
        """
        self._canceled = True
        self.restic_runner.cancel()
