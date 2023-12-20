#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.runner"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023083101"


from typing import Optional, Callable, Union, List
import os
import logging
import queue
from datetime import datetime, timedelta
from functools import wraps
import queue
from copy import deepcopy
from command_runner import command_runner
from ofunctions.threading import threaded
from ofunctions.platform import os_arch
from npbackup.restic_metrics import restic_output_2_metrics, upload_metrics
from npbackup.restic_wrapper import ResticRunner
from npbackup.core.restic_source_binary import get_restic_internal_binary
from npbackup.path_helper import CURRENT_DIR, BASEDIR
from npbackup.__version__ import __intname__ as NAME, __version__ as VERSION
from time import sleep

logger = logging.getLogger()

def metric_writer(
    repo_config: dict, restic_result: bool, result_string: str, dry_run: bool
):
    try:
        labels = {}
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
            label_string = ",".join(
                [f'{key}="{value}"' for key, value in labels.items() if value]
            )
            try:
                if prometheus_additional_labels:
                    for additional_label in prometheus_additional_labels:
                        if additional_label:
                            try:
                                label, value = additional_label.split("=")
                                label_string += ',{}="{}"'.format(
                                    label.strip(), value.strip()
                                )
                            except ValueError:
                                logger.error(
                                    'Bogus additional label "{}" defined in configuration.'.format(
                                        additional_label
                                    )
                                )
            except (KeyError, AttributeError, TypeError):
                logger.error("Bogus additional labels defined in configuration.")
                logger.debug("Trace:", exc_info=True)

            label_string += ',npversion="{}{}"'.format(NAME, VERSION)
            errors, metrics = restic_output_2_metrics(
                restic_result=restic_result, output=result_string, labels=label_string
            )
            if errors or not restic_result:
                logger.error("Restic finished with errors.")
            if destination:
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
                        upload_metrics(
                            destination, authentication, no_cert_verify, metrics
                        )
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
        self._stdout = None
        self.restic_runner = None
        self.minimum_backup_age = None
        self._exec_time = None

        self._using_dev_binary = False


    @property
    def repo_config(self) -> dict:
        return self._repo_config
    
    @repo_config.setter
    def repo_config(self, value: dict):
        if not isinstance(value, dict):
            raise ValueError(f"Bogus repo config given: {value}")
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
            raise ValueError("Bogus dry_run parameter given: {}".format(value))
        self._dry_run = value

    @property
    def verbose(self):
        return self._verbose

    @verbose.setter
    def verbose(self, value):
        if not isinstance(value, bool):
            raise ValueError("Bogus verbose parameter given: {}".format(value))
        self._verbose = value

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

    def write_logs(self, msg: str, level: str = None):
        """
        Write logs to log file and stdout / stderr queues if exist for GUI usage
        """
        if level == 'warning':
            logger.warning(msg)
            if self.stderr:
                self.stderr.put(msg)
        elif level == 'error':
            logger.error(msg)
            if self.stderr:
                self.stderr.put(msg)
        elif level == 'critical':
            logger.critical(msg)
            if self.stderr:
                self.stderr.put(msg)
        else:
            logger.info(msg)
            if self.stdout:
                self.stdout.put(msg)


    # pylint does not understand why this function does not take a self parameter
    # It's a decorator, and the inner function will have the self argument instead
    # pylint: disable=no-self-argument
    def exec_timer(fn: Callable):
        """
        Decorator that calculates time of a function execution
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            start_time = datetime.utcnow()
            # pylint: disable=E1102 (not-callable)
            result = fn(self, *args, **kwargs)
            self.exec_time = (datetime.utcnow() - start_time).total_seconds()
            self.write_logs(f"Runner took {self.exec_time} seconds for {fn.__name__}")
            return result

        return wrapper

    def close_queues(fn: Callable):
        """
        Decorator that sends None to both stdout and stderr queues so GUI gets proper results
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            close_queues = kwargs.pop("close_queues", True)
            result = fn(self, *args, **kwargs)
            if close_queues:
                if self.stdout:
                    self.stdout.put(None)
                if self.stderr:
                    self.stderr.put(None)
            return result

        return wrapper

    def is_ready(fn: Callable):
        """ "
        Decorator that checks if NPBackupRunner is ready to run, and logs accordingly
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            if not self._is_ready:
                self.write_logs(
                    f"Runner cannot execute {fn.__name__}. Backend not ready",
                    level="error",
                )
                return False
            return fn(self, *args, **kwargs)

        return wrapper

    def has_permission(fn: Callable):
        """
        Decorator that checks permissions before running functions
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            required_permissions = {
                "backup": ["backup", "restore", "full"],
                "check_recent_backups": ["backup", "restore", "full"],
                "list": ["backup", "restore", "full"],
                "ls": ["backup", "restore", "full"],
                "find": ["backup", "restore", "full"],
                "restore": ["restore", "full"],
                "check": ["restore", "full"],
                "repair": ["full"],
                "forget": ["full"],
                "prune": ["full"],
                "raw": ["full"],
            }
            try:
                operation = fn.__name__
                # TODO: enforce permissions
                self.write_logs(
                    f"Permissions required are {required_permissions[operation]}"
                )
            except (IndexError, KeyError):
                self.write_logs("You don't have sufficient permissions", level="error")
                return False
            return fn(self, *args, **kwargs)

        return wrapper
    
    def apply_config_to_restic_runner(fn: Callable):
        """
        Decorator to update backend before every run
        """
        
        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            if not self._apply_config_to_restic_runner():
                return False
            return fn(self, *args, **kwargs)
        return wrapper

    def create_restic_runner(self) -> None:
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
                            f"Password command failed to produce output:\n{output}", level="error"
                        )
                        can_run = False
                    elif "\n" in output.strip():
                        self.write_logs(
                            "Password command returned multiline content instead of a string", level="error"
                        )
                        can_run = False
                    else:
                        password = output
                else:
                    self.write_logs(
                        "No password nor password command given. Repo password cannot be empty", level="error"
                    )
                    can_run = False
            except KeyError:
                self.write_logs(
                    "No password nor password command given. Repo password cannot be empty", level="error"
                )
                can_run = False
        self._is_ready = can_run
        if not can_run:
            return None
        self.restic_runner = ResticRunner(
            repository=repository,
            password=password,
            binary_search_paths=[BASEDIR, CURRENT_DIR],
        )

        if self.restic_runner.binary is None:
            # Let's try to load our internal binary for dev purposes
            arch = os_arch()
            binary = get_restic_internal_binary(arch)
            if binary:
                if not self._using_dev_binary:
                    self._using_dev_binary = True
                    self.write_logs("Using dev binary !", level='warning')
                self.restic_runner.binary = binary

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
        self.restic_runner.stdout = self.stdout

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
                                f'Bogus environment variable "{env_variable}" defined in configuration.', level="error"
                            )
        except (KeyError, AttributeError, TypeError):
            self.write_logs("Bogus environment variables defined in configuration.", level="error")
            logger.error("Trace:", exc_info=True)

        try:
            self.restic_runner.environment_variables = expanded_env_vars
        except ValueError:
            self.write_logs("Cannot initialize additional environment variables", level="error")

        try:
            self.minimum_backup_age = int(
                self.repo_config.g("repo_opts.minimum_backup_age")
            )
        except (KeyError, ValueError, TypeError):
            self.minimum_backup_age = 1440

        self.restic_runner.verbose = self.verbose
        self.restic_runner.stdout = self.stdout
        self.restic_runner.stderr = self.stderr

        return True

    ###########################
    # ACTUAL RUNNER FUNCTIONS #
    ###########################

    @exec_timer
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    @close_queues
    def list(self) -> Optional[dict]:
        self.write_logs(f"Listing snapshots of repo {self.repo_config.g('name')}", level="error")
        snapshots = self.restic_runner.snapshots()
        return snapshots

    @exec_timer
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    @close_queues
    def find(self, path: str) -> bool:
        self.write_logs(f"Searching for path {path} in repo {self.repo_config.g('name')}", level="error")
        result = self.restic_runner.find(path=path)
        if result:
            self.write_logs("Found path in:\n")
            for line in result:
                self.write_logs(line)
            return True
        return False

    @exec_timer
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    @close_queues
    def ls(self, snapshot: str) -> Optional[dict]:
        self.write_logs(f"Showing content of snapshot {snapshot} in repo {self.repo_config.g('name')}")
        result = self.restic_runner.ls(snapshot)
        return result

    @exec_timer
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    @close_queues
    def check_recent_backups(self) -> bool:
        """
        Checks for backups in timespan
        Returns True or False if found or not
        Returns None if no information is available
        """
        if self.minimum_backup_age == 0:
            self.write_logs("No minimal backup age set. Set for backup")

        self.write_logs(
            f"Searching for a backup newer than {str(timedelta(minutes=self.minimum_backup_age))} ago"
        )
        self.restic_runner.verbose = False
        result, backup_tz = self.restic_runner.has_snapshot_timedelta(
            self.minimum_backup_age
        )
        self.restic_runner.verbose = self.verbose
        if result:
            self.write_logs(f"Most recent backup in repo {self.repo_config.g('name')} is from {backup_tz}")
        elif result is False and backup_tz == datetime(1, 1, 1, 0, 0):
            self.write_logs(f"No snapshots found in repo {self.repo_config.g('name')}.")
        elif result is False:
            self.write_logs(f"No recent backup found in repo {self.repo_config.g('name')}. Newest is from {backup_tz}")
        elif result is None:
            self.write_logs("Cannot connect to repository or repository empty.", level="error")
        return result, backup_tz

    @exec_timer
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    @close_queues
    def backup(self, force: bool = False) -> bool:
        """
        Run backup after checking if no recent backup exists, unless force == True
        """
        # Preflight checks
        paths = self.repo_config.g("backup_opts.paths")
        if not paths:
            self.write_logs(f"No paths to backup defined for repo {self.repo_config.g('name')}.", level="error")
            return False

        # Make sure we convert paths to list if only one path is give
        # Also make sure we remove trailing and ending spaces
        try:
            if not isinstance(paths, list):
                paths = [paths]
            paths = [path.strip() for path in paths]
            for path in paths:
                if path == self.repo_config.g("repo_uri"):
                    self.write_logs(
                        f"You cannot backup source into it's own path in repo {self.repo_config.g('name')}. No inception allowed !", level='critical'
                    )
                    return False
        except KeyError:
            self.write_logs(f"No backup source given for repo {self.repo_config.g('name')}.", level='error')
            return False

        exclude_patterns_source_type = self.repo_config.g(
            "backup_opts.exclude_patterns_source_type"
        )

        # MSWindows does not support one-file-system option
        exclude_patterns = self.repo_config.g("backup_opts.exclude_patterns")
        if not isinstance(exclude_patterns, list):
            exclude_patterns = [exclude_patterns]

        exclude_files = self.repo_config.g("backup_opts.exclude_files")
        if not isinstance(exclude_files, list):
            exclude_files = [exclude_files]

        exclude_patterns_case_ignore = self.repo_config.g(
            "backup_opts.exclude_patterns_case_ignore"
        )
        exclude_caches = self.repo_config.g("backup_opts.exclude_caches")
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

        # Check if backup is required
        self.restic_runner.verbose = False
        if not self.restic_runner.is_init:
            if not self.restic_runner.init():
                self.write_logs(f"Cannot continue, repo {self.repo_config.g('name')} is not defined.", level="critical")
                return False
        if self.check_recent_backups() and not force:
            self.write_logs("No backup necessary.")
            return True
        self.restic_runner.verbose = self.verbose

        # Run backup here
        if exclude_patterns_source_type not in ["folder_list", None]:
            self.write_logs(f"Running backup of files in {paths} list to repo {self.repo_config.g('name')}")
        else:
            self.write_logs(f"Running backup of {paths} to repo {self.repo_config.g('name')}")

        if pre_exec_commands:
            for pre_exec_command in pre_exec_commands:
                exit_code, output = command_runner(
                    pre_exec_command, shell=True, timeout=pre_exec_per_command_timeout
                )
                if exit_code != 0:
                    self.write_logs(
                        f"Pre-execution of command {pre_exec_command} failed with:\n{output}", level="error"
                    )
                    if pre_exec_failure_is_fatal:
                        return False
                else:
                    self.write_logs(
                        "Pre-execution of command {pre_exec_command} success with:\n{output}."
                    )

        self.restic_runner.dry_run = self.dry_run
        result, result_string = self.restic_runner.backup(
            paths=paths,
            exclude_patterns_source_type=exclude_patterns_source_type,
            exclude_patterns=exclude_patterns,
            exclude_files=exclude_files,
            exclude_patterns_case_ignore=exclude_patterns_case_ignore,
            exclude_caches=exclude_caches,
            one_file_system=one_file_system,
            use_fs_snapshot=use_fs_snapshot,
            tags=tags,
            additional_backup_only_parameters=additional_backup_only_parameters,
        )
        logger.debug(f"Restic output:\n{result_string}")
        metric_writer(
            self.repo_config, result, result_string, self.restic_runner.dry_run
        )

        if post_exec_commands:
            for post_exec_command in post_exec_commands:
                exit_code, output = command_runner(
                    post_exec_command, shell=True, timeout=post_exec_per_command_timeout
                )
                if exit_code != 0:
                    self.write_logs(
                        f"Post-execution of command {post_exec_command} failed with:\n{output}", level="error"
                    )
                    if post_exec_failure_is_fatal:
                        return False
                else:
                    self.write_logs(
                        "Post-execution of command {post_exec_command} success with:\n{output}.", level="error"
                    )
        return result

    @exec_timer
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    @close_queues
    def restore(self, snapshot: str, target: str, restore_includes: List[str]) -> bool:
        if not self.repo_config.g("permissions") in ["restore", "full"]:
            self.write_logs(f"You don't have permissions to restore repo {self.repo_config.g('name')}", level="error")
            return False
        self.write_logs(f"Launching restore to {target}")
        result = self.restic_runner.restore(
            snapshot=snapshot,
            target=target,
            includes=restore_includes,
        )
        return result

    @exec_timer
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    @close_queues
    def forget(self, snapshot: str) -> bool:
        self.write_logs(f"Forgetting snapshot {snapshot}")
        result = self.restic_runner.forget(snapshot)
        return result

    @exec_timer
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    @threaded
    @close_queues
    def check(self, read_data: bool = True) -> bool:
        if read_data:
            self.write_logs(f"Running full data check of repository {self.repo_config.g('name')}")
        else:
            self.write_logs(f"Running metadata consistency check of repository {self.repo_config.g('name')}")
        sleep(1)
        result = self.restic_runner.check(read_data)
        return result

    @exec_timer
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    @close_queues
    def prune(self) -> bool:
        self.write_logs(f"Pruning snapshots for repo {self.repo_config.g('name')}")
        result = self.restic_runner.prune()
        return result

    @exec_timer
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    @close_queues
    def repair(self, subject: str) -> bool:
        self.write_logs(f"Repairing {subject} in repo {self.repo_config.g('name')}")
        result = self.restic_runner.repair(subject)
        return result

    @exec_timer
    @has_permission
    @is_ready
    @apply_config_to_restic_runner
    @close_queues
    def raw(self, command: str) -> bool:
        self.write_logs(f"Running raw command: {command}")
        result = self.restic_runner.raw(command=command)
        return result

    @exec_timer
    def group_runner(self, repo_config_list: list, operation: str, **kwargs) -> bool:
        group_result = True

        # Make sure we don't close the stdout/stderr queues when running multiple operations
        # Also make sure we don't thread functions
        kwargs = {
            **kwargs,
            **{
                "close_queues": False,
                #"__no_threads": True,
                }
            }

        for repo_name, repo_config in repo_config_list:
            self.write_logs(f"Running {operation} for repo {repo_name}")
            self.repo_config = repo_config
            result = self.__getattribute__(operation)(**kwargs)
            if result:
                self.write_logs(f"Finished {operation} for repo {repo_name}")
            else:
                self.write_logs(
                    f"Operation {operation} failed for repo {repo_name}", level="error"
                )
                group_result = False
        self.write_logs("Finished execution group operations")
        # Manually close the queues at the end
        if self.stdout:
            self.stdout.put(None)
        if self.stderr:
            self.stderr.put(None)
        #sleep(1) # TODO this is arbitrary to allow queues to be read entirely
        return group_result
