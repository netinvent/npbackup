#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.runner"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024061101"


from typing import Optional, Callable, Union, List
import os
import logging
import tempfile
import pidfile
import queue
from datetime import datetime, timedelta, timezone
from functools import wraps
import queue
from copy import deepcopy
from command_runner import command_runner
from ofunctions.threading import threaded
from ofunctions.platform import os_arch
from ofunctions.misc import BytesConverter, fn_name
import ntplib
from npbackup.restic_metrics import (
    restic_str_output_to_json,
    restic_json_to_prometheus,
    upload_metrics,
)
from npbackup.restic_wrapper import ResticRunner
from npbackup.core.restic_source_binary import get_restic_internal_binary
from npbackup.path_helper import CURRENT_DIR, BASEDIR
from npbackup.__version__ import __intname__ as NAME, __version__ as VERSION
from npbackup.__debug__ import _DEBUG


logger = logging.getLogger()


def metric_writer(
    repo_config: dict,
    restic_result: bool,
    result_string: str,
    operation: str,
    dry_run: bool,
) -> bool:
    backup_too_small = False
    operation_success = True
    metrics = []

    try:
        labels = {"npversion": f"{NAME}{VERSION}"}
        if repo_config.g("prometheus.metrics"):
            labels["instance"] = repo_config.g("prometheus.instance")
            labels["backup_job"] = repo_config.g("prometheus.backup_job")
            labels["group"] = repo_config.g("prometheus.group")
            no_cert_verify = repo_config.g("prometheus.no_cert_verify")
            destination = repo_config.g("prometheus.destination")
            prometheus_additional_labels = repo_config.g("prometheus.additional_labels")
            repo_name = repo_config.g("name")

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
            repo_name = None

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
            logger.error("Restic finished with errors.")

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

        _labels = []
        for key, value in labels.items():
            if value:
                _labels.append(f'{key.strip()}="{value.strip()}"')
        labels = ",".join(_labels)

        if operation != "backup":
            metrics.append(
                f'npbackup_oper_state{{{labels},action="{operation}",repo="{repo_name}"}} {0 if restic_result else 1}'
            )
        metrics.append(f"npbackup_exec_state{{{labels}}} {exec_state}")
        logger.debug("Metrics computed:\n{}".format("\n".join(metrics)))
        if destination:
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
                if not dry_run:
                    upload_metrics(destination, authentication, no_cert_verify, metrics)
                else:
                    logger.info("Not uploading metrics in dry run mode")
            else:
                try:
                    # We use append so if prometheus text collector did not get data yet, we'll not wipe it
                    with open(destination, "a", encoding="utf-8") as file_handle:
                        for metric in metrics:
                            file_handle.write(metric + "\n")
                except OSError as exc:
                    logger.error(
                        "Cannot write metrics file {}: {}".format(destination, exc)
                    )
    except KeyError as exc:
        logger.info("Metrics error: {}".format(exc))
        logger.debug("Trace:", exc_info=True)
    except OSError as exc:
        logger.error("Cannot write metric file: ".format(exc))
        logger.debug("Trace:", exc_info=True)
    return backup_too_small


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
    except Exception as exc:
        logger.error(f"Cannot reach NTP server {ntp_server}: {exc}")
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
        self._binary = None
        self._no_cache = False
        self.restic_runner = None
        self.minimum_backup_age = None
        self._exec_time = None

    @property
    def repo_config(self) -> dict:
        return self._repo_config

    @repo_config.setter
    def repo_config(self, value: dict):
        if not isinstance(value, dict):
            msg = f"Bogus repo config object given"
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
    def exec_time(self):
        return self._exec_time

    @exec_time.setter
    def exec_time(self, value: int):
        self._exec_time = value

    def write_logs(self, msg: str, level: str, raise_error: str = None):
        """
        Write logs to log file and stdout / stderr queues if exist for GUI usage
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
            raise ValueError("Bogus log level given {level}")

        if msg is None:
            raise ValueError("None log message received")
        if self.stdout and (level == "info" or (level == "debug" and _DEBUG)):
            self.stdout.put(f"\n{msg}")
        if self.stderr and level in ("critical", "error", "warning"):
            self.stderr.put(f"\n{msg}")

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
                msg = f"Runner cannot execute, backend not ready"
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
        - backup:   Backup and list backups
        - restore:  Backup, restore and list snapshots
        - full:     Full permissions

        Only one permission can be set per repo
        When no permission is set, assume full permissions
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            required_permissions = {
                "backup": ["backup", "restore", "full"],
                "has_recent_snapshot": ["backup", "restore", "full"],
                "snapshots": ["backup", "restore", "full"],
                "stats": ["backup", "restore", "full"],
                "ls": ["backup", "restore", "full"],
                "find": ["backup", "restore", "full"],
                "restore": ["restore", "full"],
                "dump": ["restore", "full"],
                "check": ["restore", "full"],
                "init": ["full"],
                "list": ["full"],
                "unlock": ["full"],
                "repair": ["full"],
                "forget": ["full"],
                "prune": ["full"],
                "raw": ["full"],
            }
            try:
                # When running group_runner, we need to extract operation from kwargs
                # else, operarion is just the wrapped function name
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
            if self.dry_run:
                logger.warning("Running in dry mode. No modifications will be done")
            # pylint: disable=E1102 (not-callable)
            return fn(self, *args, **kwargs)

        return wrapper

    def check_concurrency(fn: Callable):
        """
        Make sure there we don't allow concurrent actions
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            locking_operations = [
                "backup",
                "repair",
                "forget",
                "prune",
                "raw",
                "unlock",
            ]
            # pylint: disable=E1101 (no-member)
            if fn.__name__ == "group_runner":
                operation = kwargs.get("operation")
            else:
                # pylint: disable=E1101 (no-member)
                operation = fn.__name__
            if operation in locking_operations:
                pid_file = os.path.join(
                    tempfile.gettempdir(), "{}.pid".format(__intname__)
                )
                try:
                    with pidfile.PIDFile(pid_file):
                        # pylint: disable=E1102 (not-callable)
                        result = fn(self, *args, **kwargs)
                except pidfile.AlreadyRunningError:
                    self.write_logs(
                        f"There is already an {operation} operation running by NPBackup. Will not continue",
                        level="critical",
                    )
                    return False
            else:
                result = fn(  # pylint: disable=E1102 (not-callable)
                    self, *args, **kwargs
                )
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
                    f"Function {operation} failed with: {exc}", level="error"
                )
                logger.debug("Trace:", exc_info=True)
                # In case of error, we really need to write metrics
                # pylint: disable=E1101 (no-member)
                metric_writer(self.repo_config, False, None, fn.__name__, self.dry_run)
                if self.json_output:
                    js = {
                        "result": False,
                        "operation": operation,
                        "reason": f"Exception: {exc}",
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
            metric_writer(self.repo_config, result, None, fn.__name__, self.dry_run)
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
            self.write_logs("Bogus backend connections value given.", level="erorr")
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

        env_variables += encrypted_env_variables
        expanded_env_vars = {}
        if isinstance(env_variables, list):
            for env_variable in env_variables:
                if isinstance(env_variable, dict):
                    for k, v in env_variable.items():
                        v = os.path.expanduser(v)
                        v = os.path.expandvars(v)
                        expanded_env_vars[k.strip()] = v.strip()

        try:
            self.restic_runner.environment_variables = expanded_env_vars
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
        self.restic_runner.live_output = self.live_output
        self.restic_runner.json_output = self.json_output
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
        return True

    def convert_to_json_output(
        self,
        result: bool,
        output: str = None,
        backend_js: dict = None,
        warnings: str = None,
    ):
        if self.json_output:
            if backend_js:
                js = backend_js
            if isinstance(result, dict):
                js = result
            else:
                js = {
                    "result": result,
                }
            if warnings:
                js["warnings"] = warnings
            if result:
                js["output"] = output
            else:
                js["reason"] = output
            return js
        return result

    ###########################
    # ACTUAL RUNNER FUNCTIONS #
    ###########################

    # Decorator order is important
    # Since we want a concurrent.futures.Future result, we need to put the @threaded decorator
    # before any other decorator that would change the results
    # @close_queues should come second, since we want to close queues only once the lower functions are finished
    # @exec_timer is next, since we want to calc max exec time (except the close_queues and threaded overhead)
    # All others are in no particular order
    # but @catch_exceptions should come last, since we aren't supposed to have errors in decorators

    @threaded
    @catch_exceptions
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def init(self) -> bool:
        self.write_logs(
            f"Initializing repo  {self.repo_config.g('name')}", level="info"
        )
        return self.restic_runner.init()

    @threaded
    @catch_exceptions
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def snapshots(self) -> Optional[dict]:
        self.write_logs(
            f"Listing snapshots of repo {self.repo_config.g('name')}", level="info"
        )
        snapshots = self.restic_runner.snapshots()
        return snapshots

    @threaded
    @catch_exceptions
    @close_queues
    @exec_timer
    @check_concurrency
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
    @catch_exceptions
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def find(self, path: str) -> bool:
        self.write_logs(
            f"Searching for path {path} in repo {self.repo_config.g('name')}",
            level="info",
        )
        result = self.restic_runner.find(path=path)
        if result:
            self.write_logs(f"Found path in:\n{result}", level="info")
        return self.convert_to_json_output(result, None)

    @threaded
    @catch_exceptions
    @close_queues
    @exec_timer
    @check_concurrency
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
    @catch_exceptions
    @close_queues
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
    @catch_exceptions
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def backup(
        self,
        force: bool = False,
        read_from_stdin: bool = False,
        stdin_filename: str = "stdin.data",
    ) -> bool:
        """
        Run backup after checking if no recent backup exists, unless force == True
        """
        # Possible warnings to add to json output
        warnings = []

        # Preflight checks
        if not read_from_stdin:
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
            except KeyError:
                msg = f"No backup source given for repo {self.repo_config.g('name')}"
                self.write_logs(msg, level="critical")
                return self.convert_to_json_output(False, msg)

            source_type = self.repo_config.g("backup_opts.source_type")

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

        additional_backup_only_parameters = self.repo_config.g(
            "backup_opts.additional_backup_only_parameters"
        )

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

        # Run backup here
        if not read_from_stdin:
            if source_type not in ["folder_list", None]:
                self.write_logs(
                    f"Running backup of files in {paths} list to repo {self.repo_config.g('name')}",
                    level="info",
                )
            else:
                self.write_logs(
                    f"Running backup of {paths} to repo {self.repo_config.g('name')}",
                    level="info",
                )
        else:
            self.write_logs(
                f"Running backup of piped stdin data as name {stdin_filename} to repo {self.repo_config.g('name')}",
                level="info",
            )

        pre_exec_commands_success = True
        if pre_exec_commands:
            for pre_exec_command in pre_exec_commands:
                exit_code, output = command_runner(
                    pre_exec_command, shell=True, timeout=pre_exec_per_command_timeout
                )
                if exit_code != 0:
                    msg = f"Pre-execution of command {pre_exec_command} failed with:\n{output}"
                    self.write_logs(msg, level="error")
                    if pre_exec_failure_is_fatal:
                        return self.convert_to_json_output(False, msg)
                    else:
                        warnings.append(msg)
                    pre_exec_commands_success = False
                else:
                    self.write_logs(
                        f"Pre-execution of command {pre_exec_command} succeeded with:\n{output}",
                        level="info",
                    )

        if not read_from_stdin:
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
        else:
            result = self.restic_runner.backup(
                read_from_stdin=read_from_stdin,
                stdin_filename=stdin_filename,
                tags=tags,
                additional_backup_only_parameters=additional_backup_only_parameters,
            )

        self.write_logs(
            f"Restic output:\n{self.restic_runner.backup_result_content}", level="debug"
        )

        # Extract backup size from result_string
        # Metrics will not be in json format, since we need to diag cloud issues until
        # there is a fix for https://github.com/restic/restic/issues/4155
        backup_too_small = metric_writer(
            self.repo_config,
            result,
            self.restic_runner.backup_result_content,
            "backup",
            self.restic_runner.dry_run,
        )
        if backup_too_small:
            self.write_logs(
                "Backup is smaller than configured minmium backup size", level="error"
            )

        post_exec_commands_success = True
        if post_exec_commands:
            for post_exec_command in post_exec_commands:
                exit_code, output = command_runner(
                    post_exec_command, shell=True, timeout=post_exec_per_command_timeout
                )
                if exit_code != 0:
                    msg = f"Post-execution of command {post_exec_command} failed with:\n{output}"
                    self.write_logs(msg, level="error")
                    post_exec_commands_success = False
                    if post_exec_failure_is_fatal:
                        return self.convert_to_json_output(False, msg)
                    else:
                        warnings.append(msg)
                else:
                    self.write_logs(
                        f"Post-execution of command {post_exec_command} succeeded with:\n{output}",
                        level="info",
                    )

        operation_result = (
            result
            and pre_exec_commands_success
            and post_exec_commands_success
            and not backup_too_small
        )
        msg = f"Operation finished with {'success' if operation_result else 'failure'}"
        self.write_logs(
            msg,
            level="info" if operation_result else "error",
        )
        if not operation_result:
            # patch result if json
            if isinstance(result, dict):
                result["result"] = False
            # Don't overwrite backend output in case of failure
            return self.convert_to_json_output(result)
        return self.convert_to_json_output(result, msg)

    @threaded
    @catch_exceptions
    @metrics
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def restore(self, snapshot: str, target: str, restore_includes: List[str]) -> bool:
        self.write_logs(f"Launching restore to {target}", level="info")
        return self.restic_runner.restore(
            snapshot=snapshot,
            target=target,
            includes=restore_includes,
        )

    @threaded
    @catch_exceptions
    @metrics
    @close_queues
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
                offset = get_ntp_offset(ntp_server)
                if not offset or offset >= 600:
                    msg = f"Offset from NTP server {ntp_server} is too high: {int(offset)} seconds. Won't apply policy"
                    self.write_logs(msg, level="critical")
                    return self.convert_to_json_output(False, msg)

            # Build policiy from config
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
                msg = f"Empty retention policy. Won't run"
                self.write_logs(msg, level="error")
                return self.convert_to_json_output(False, msg)
            self.write_logs(
                f"Forgetting snapshots using retention policy: {policy}", level="info"
            )
            result = self.restic_runner.forget(policy=policy)
        else:
            self.write_logs(
                "Bogus options given to forget: snapshots={snapshots}, policy={policy}",
                level="critical",
                raise_error=True,
            )
            result = False
        return self.convert_to_json_output(result)

    @threaded
    @catch_exceptions
    @metrics
    @close_queues
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
    @catch_exceptions
    @metrics
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def prune(self, max: bool = False) -> bool:
        self.write_logs(
            f"Pruning snapshots for repo {self.repo_config.g('name')}", level="info"
        )
        if max:
            max_unused = self.repo_config.g("prune_max_unused")
            max_repack_size = self.repo_config.g("prune_max_repack_size")
            result = self.restic_runner.prune(
                max_unused=max_unused, max_repack_size=max_repack_size
            )
        else:
            result = self.restic_runner.prune()
        return result

    @threaded
    @catch_exceptions
    @metrics
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def repair(self, subject: str) -> bool:
        self.write_logs(
            f"Repairing {subject} in repo {self.repo_config.g('name')}", level="info"
        )
        return self.restic_runner.repair(subject)

    @threaded
    @catch_exceptions
    @metrics
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def unlock(self) -> bool:
        self.write_logs(f"Unlocking repo {self.repo_config.g('name')}", level="info")
        return self.restic_runner.unlock()

    @threaded
    @catch_exceptions
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def dump(self, path: str) -> bool:
        self.write_logs(
            f"Dumping {path} from {self.repo_config.g('name')}", level="info"
        )
        result = self.restic_runner.dump(path)
        return result

    @threaded
    @catch_exceptions
    @close_queues
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
    @catch_exceptions
    @metrics
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def raw(self, command: str) -> bool:
        self.write_logs(f"Running raw command: {command}", level="info")
        return self.restic_runner.raw(command=command)

    @threaded
    @catch_exceptions
    @close_queues
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

        js = {"result": None, "details": []}

        for repo_config in repo_config_list:
            repo_name = repo_config.g("name")
            self.write_logs(f"Running {operation} for repo {repo_name}", level="info")
            self.repo_config = repo_config
            result = self.__getattribute__(operation)(**kwargs)
            if self.json_output:
                js["details"].append({repo_name: result})
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
            metric_writer(repo_config, result, None, operation, self.dry_run)
        self.write_logs("Finished execution group operations", level="info")
        if self.json_output:
            js["result"] = group_result
            return js
        return group_result
