#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.runner"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024042401"


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
from ofunctions.misc import BytesConverter
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
    repo_config: dict, restic_result: bool, result_string: str, dry_run: bool
) -> bool:
    backup_too_small = False
    minimum_backup_size_error = repo_config.g("backup_opts.minimum_backup_size_error")
    try:
        labels = {"npversion": f"{NAME}{VERSION}"}
        if repo_config.g("prometheus.metrics"):
            labels["instance"] = repo_config.g("prometheus.instance")
            labels["backup_job"] = repo_config.g("prometheus.backup_job")
            labels["group"] = repo_config.g("prometheus.group")
            no_cert_verify = repo_config.g("prometheus.no_cert_verify")
            destination = repo_config.g("prometheus.destination")
            prometheus_additional_labels = repo_config.g("prometheus.additional_labels")

            if not isinstance(prometheus_additional_labels, list):
                prometheus_additional_labels = [prometheus_additional_labels]

            # Configure lables
            try:
                if prometheus_additional_labels:
                    for additional_label in prometheus_additional_labels:
                        if additional_label:
                            try:
                                label, value = additional_label.split("=")
                                labels[label.strip()] = value.strip()
                            except ValueError:
                                logger.error(
                                    'Bogus additional label "{}" defined in configuration.'.format(
                                        additional_label
                                    )
                                )
            except (KeyError, AttributeError, TypeError):
                logger.error("Bogus additional labels defined in configuration.")
                logger.debug("Trace:", exc_info=True)

        # If result was a str, we need to transform it into json first
        if isinstance(result_string, str):
            restic_result = restic_str_output_to_json(restic_result, result_string)

        good_backup, metrics, backup_too_small = restic_json_to_prometheus(
            restic_result=restic_result,
            restic_json=restic_result,
            labels=labels,
            minimum_backup_size_error=minimum_backup_size_error,
        )
        if not good_backup or not restic_result:
            logger.error("Restic finished with errors.")
        if repo_config.g("prometheus.metrics") and destination:
            logger.debug("Uploading metrics to {}".format(destination))
            if destination.lower().startswith("http"):
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
                    with open(destination, "w") as file_handle:
                        for metric in metrics:
                            file_handle.write(metric + "\n")
                except OSError as exc:
                    logger.error(
                        "Cannot write metrics file {}: {}".format(destination, exc)
                    )
    except KeyError as exc:
        logger.info("Metrics not configured: {}".format(exc))
    except OSError as exc:
        logger.error("Cannot write metric file: ".format(exc))
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
            self.stdout.put(msg)
        if self.stderr and level in ("critical", "error", "warning"):
            self.stderr.put(msg)

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
                            f"Required permissions for operation '{operation}' must be in {required_permissions[operation]}, current permission is [{current_permissions}]",
                            level="critical",
                        )
                        raise PermissionError
                else:
                    # This happens in viewer mode
                    self.write_logs("No repo config. Ignoring permission check", level="info")
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
                except pidfile.AlreadyRunningError as exc:
                    self.write_logs(
                        f"There is already an {operation} operation running by NPBackup: {exc}. Will not continue",
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
                logger.info("Trace:", exc_info=True)
                if self.json_output:
                    js = {
                        "result": False,
                        "operation": operation,
                        "reason": f"Exception: {exc}",
                    }
                    return js
                return False

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
            env_variables = self.repo_config.g("env.variables")
            if not isinstance(env_variables, list):
                env_variables = [env_variables]
        except KeyError:
            env_variables = []
        try:
            encrypted_env_variables = self.repo_config.g("env.encrypted_variables")
            if not isinstance(encrypted_env_variables, list):
                encrypted_env_variables = [encrypted_env_variables]
        except KeyError:
            encrypted_env_variables = []

        # TODO use "normal" YAML syntax
        env_variables += encrypted_env_variables
        expanded_env_vars = {}
        try:
            if env_variables:
                for env_variable in env_variables:
                    if env_variable:
                        try:
                            key, value = env_variable.split("=")
                            value = os.path.expanduser(value)
                            value = os.path.expandvars(value)
                            expanded_env_vars[key.strip()] = value.strip()
                        except ValueError:
                            self.write_logs(
                                f'Bogus environment variable "{env_variable}" defined in configuration.',
                                level="error",
                            )
        except (KeyError, AttributeError, TypeError):
            self.write_logs(
                "Bogus environment variables defined in configuration.", level="error"
            )
            logger.error("Trace:", exc_info=True)

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
            if exclude_files_larger_than:
                try:
                    BytesConverter(exclude_files_larger_than)
                except ValueError:
                    warning = f"Bogus unit for exclude_files_larger_than value given: {exclude_files_larger_than}"
                    self.write_logs(warning, level="warning")
                    warnings.append(warning)
                    exclude_files_larger_than = None
                    exclude_files_larger_than = None

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

        # Check if backup is required, no need to be verbose, but we'll make sure we don't get a json result here
        self.restic_runner.verbose = False
        json_output = self.json_output
        self.json_output = False
        # Since we don't want to close queues nor create a subthread, we need to change behavior here
        # pylint: disable=E1123 (unexpected-keyword-arg)
        has_recent_snapshots, backup_tz = self.has_recent_snapshot(
            __close_queues=False, __no_threads=True
        )
        self.json_output = json_output
        # We also need to "reapply" the json setting to backend
        self.restic_runner.json_output = json_output
        if has_recent_snapshots and not force:
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
                        "Pre-execution of command {pre_exec_command} success with:\n{output}.",
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
            self.restic_runner.dry_run,
        )
        if backup_too_small:
            self.write_logs("Backup is smaller than expected", level="error")

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
                        f"Post-execution of command {post_exec_command} success with:\n{output}.",
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
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def restore(self, snapshot: str, target: str, restore_includes: List[str]) -> bool:
        self.write_logs(f"Launching restore to {target}", level="info")
        result = self.restic_runner.restore(
            snapshot=snapshot,
            target=target,
            includes=restore_includes,
        )
        return result

    @threaded
    @catch_exceptions
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
                    if not self.repo_config.g("repo_opts.retention_policy.within"):
                        policy[f"keep-{entry}"] = value
                    else:
                        # We need to add a type value for keep-within
                        policy[f"keep-within-{entry}"] = value
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
        return self.convert_to_json_output(result)

    @threaded
    @catch_exceptions
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
        result = self.restic_runner.check(read_data)
        return result

    @threaded
    @catch_exceptions
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
        result = self.restic_runner.repair(subject)
        return result

    @threaded
    @catch_exceptions
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def unlock(self) -> bool:
        self.write_logs(f"Unlocking repo {self.repo_config.g('name')}", level="info")
        result = self.restic_runner.unlock()
        return result

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
    def stats(self) -> bool:
        self.write_logs(
            f"Getting stats of repo {self.repo_config.g('name')}", level="info"
        )
        result = self.restic_runner.stats()
        return result

    @threaded
    @catch_exceptions
    @close_queues
    @exec_timer
    @check_concurrency
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    def raw(self, command: str) -> bool:
        self.write_logs(f"Running raw command: {command}", level="info")
        result = self.restic_runner.raw(command=command)
        return result

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
        self.write_logs("Finished execution group operations", level="info")
        if self.json_output:
            js["result"] = group_result
            return js
        return group_result
