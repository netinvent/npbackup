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
from command_runner import command_runner
from ofunctions.platform import os_arch
from npbackup.restic_metrics import restic_output_2_metrics, upload_metrics
from npbackup.restic_wrapper import ResticRunner
from npbackup.core.restic_source_binary import get_restic_internal_binary
from npbackup.path_helper import CURRENT_DIR, BASEDIR
from npbackup.__version__ import __intname__ as NAME, __version__ as VERSION
from npbackup import configuration


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

    def __init__(self, repo_config: Optional[dict] = None):
        if repo_config:
            self.repo_config = repo_config

            self._dry_run = False
            self._verbose = False
            self._stdout = None
            self.restic_runner = None
            self.minimum_backup_age = None
            self._exec_time = None

            self.is_ready = False
            # Create an instance of restic wrapper
            self.create_restic_runner()
            # Configure that instance
            self.apply_config_to_restic_runner()
        else:
            self.is_ready = False

    @property
    def backend_version(self) -> bool:
        if self.is_ready:
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
        self.apply_config_to_restic_runner()

    @property
    def verbose(self):
        return self._verbose

    @verbose.setter
    def verbose(self, value):
        if not isinstance(value, bool):
            raise ValueError("Bogus verbose parameter given: {}".format(value))
        self._verbose = value
        self.apply_config_to_restic_runner()

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
        self.apply_config_to_restic_runner()

    @property
    def has_binary(self) -> bool:
        if self.is_ready:
            return True if self.restic_runner.binary else False
        return False

    @property
    def exec_time(self):
        return self._exec_time

    @exec_time.setter
    def exec_time(self, value: int):
        self._exec_time = value

    # pylint does not understand why this function does not take a self parameter
    # It's a decorator, and the inner function will have the self argument instead
    # pylint: disable=no-self-argument
    def exec_timer(fn: Callable):
        """
        Decorator that calculates time of a function execution
        """

        def wrapper(self, *args, **kwargs):
            start_time = datetime.utcnow()
            # pylint: disable=E1102 (not-callable)
            result = fn(self, *args, **kwargs)
            self.exec_time = (datetime.utcnow() - start_time).total_seconds()
            logger.info("Runner took {} seconds".format(self.exec_time))
            return result

        return wrapper

    def create_restic_runner(self) -> None:
        can_run = True
        try:
            repository = self.repo_config.g("repo_uri")
            if not repository:
                raise KeyError
        except (KeyError, AttributeError):
            logger.error("Repo cannot be empty")
            can_run = False
        try:
            password = self.repo_config.g("repo_opts.repo_password")
        except (KeyError, AttributeError):
            logger.error("Repo password cannot be empty")
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
                        logger.error(
                            "Password command failed to produce output:\n{}".format(
                                output
                            )
                        )
                        can_run = False
                    elif "\n" in output.strip():
                        logger.error(
                            "Password command returned multiline content instead of a string"
                        )
                        can_run = False
                    else:
                        password = output
                else:
                    logger.error(
                        "No password nor password command given. Repo password cannot be empty"
                    )
                    can_run = False
            except KeyError:
                logger.error(
                    "No password nor password command given. Repo password cannot be empty"
                )
                can_run = False
        self.is_ready = can_run
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
                logger.info("Using dev binary !")
                self.restic_runner.binary = binary

    def apply_config_to_restic_runner(self) -> None:
        if not self.is_ready:
            return None
        try:
            if self.repo_config.g("repo_opts.upload_speed"):
                self.restic_runner.limit_upload = self.repo_config.g("repo_opts.upload_speed")
        except KeyError:
            pass
        except ValueError:
            logger.error("Bogus upload limit given.")
        try:
            if self.repo_config.g("repo_opts.download_speed"):
                self.restic_runner.limit_download = self.repo_config.g("repo_opts.download_speed")
        except KeyError:
            pass
        except ValueError:
            logger.error("Bogus download limit given.")
        try:
            if self.repo_config.g("repo_opts.backend_connections"):
                self.restic_runner.backend_connections = self.repo_config.g("repo_opts.backend_connections")
        except KeyError:
            pass
        except ValueError:
            logger.error("Bogus backend connections value given.")
        try:
            if self.repo_config.g("backup_opts.priority"):
                self.restic_runner.priority = self.repo_config.g("backup_opts.priority")
        except KeyError:
            pass
        except ValueError:
            logger.warning("Bogus backup priority in config file.")
        try:
            if self.repo_config.g("backup_opts.ignore_cloud_files"):
                self.restic_runner.ignore_cloud_files = self.repo_config.g("backup_opts.ignore_cloud_files")
        except KeyError:
            pass
        except ValueError:
            logger.warning("Bogus ignore_cloud_files value given")

        try:
            if self.repo_config.g("backup_opts.additional_parameters"):
                self.restic_runner.additional_parameters = self.repo_config.g("backup_opts.additional_parameters")
        except KeyError:
            pass
        except ValueError:
            logger.warning("Bogus additional parameters given")
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
                            logger.error(
                                'Bogus environment variable "{}" defined in configuration.'.format(
                                    env_variable
                                )
                            )
        except (KeyError, AttributeError, TypeError):
            logger.error("Bogus environment variables defined in configuration.")
            logger.debug("Trace:", exc_info=True)

        try:
            self.restic_runner.environment_variables = expanded_env_vars
        except ValueError:
            logger.error("Cannot initialize additional environment variables")

        try:
            self.minimum_backup_age = int(
                self.repo_config.g("repo_opts.minimum_backup_age")
            )
        except (KeyError, ValueError, TypeError):
            self.minimum_backup_age = 1440

        self.restic_runner.verbose = self.verbose
        self.restic_runner.stdout = self.stdout

    @exec_timer
    def list(self) -> Optional[dict]:
        if not self.is_ready:
            return False
        logger.info("Listing snapshots")
        snapshots = self.restic_runner.snapshots()
        return snapshots

    @exec_timer
    def find(self, path: str) -> bool:
        if not self.is_ready:
            return False
        logger.info("Searching for path {}".format(path))
        result = self.restic_runner.find(path=path)
        if result:
            logger.info("Found path in:\n")
            for line in result:
                logger.info(line)
            return True
        return False

    @exec_timer
    def ls(self, snapshot: str) -> Optional[dict]:
        if not self.is_ready:
            return False
        logger.info("Showing content of snapshot {}".format(snapshot))
        result = self.restic_runner.ls(snapshot)
        return result

    @exec_timer
    def check_recent_backups(self) -> bool:
        """
        Checks for backups in timespan
        Returns True or False if found or not
        Returns None if no information is available
        """
        if not self.is_ready:
            return None
        if self.minimum_backup_age == 0:
            logger.info("No minimal backup age set. Set for backup")

        logger.info(
            "Searching for a backup newer than {} ago".format(
                str(timedelta(minutes=self.minimum_backup_age))
            )
        )
        self.restic_runner.verbose = False
        result, backup_tz = self.restic_runner.has_snapshot_timedelta(
            self.minimum_backup_age
        )
        self.restic_runner.verbose = self.verbose
        if result:
            logger.info("Most recent backup is from {}".format(backup_tz))
        elif result is False and backup_tz == datetime(1, 1, 1, 0, 0):
            logger.info("No snapshots found in repo.")
        elif result is False:
            logger.info("No recent backup found. Newest is from {}".format(backup_tz))
        elif result is None:
            logger.error("Cannot connect to repository or repository empty.")
        return result, backup_tz

    @exec_timer
    def backup(self, force: bool = False) -> bool:
        """
        Run backup after checking if no recent backup exists, unless force == True
        """
        if not self.is_ready:
            return False
        # Preflight checks
        paths = self.repo_config.g("backup_opts.paths")
        if not paths:
            logger.error("No backup paths defined.")
            return False

        # Make sure we convert paths to list if only one path is give
        # Also make sure we remove trailing and ending spaces
        try:
            if not isinstance(paths, list):
                paths = [paths]
            paths = [path.strip() for path in paths]
            for path in paths:
                if path == self.repo_config.g("repo_uri"):
                    logger.critical(
                        "You cannot backup source into it's own path. No inception allowed !"
                    )
                    return False
        except KeyError:
            logger.error("No backup source given.")
            return False

        exclude_patterns_source_type = self.repo_config.g("backup_opts.exclude_patterns_source_type")

        # MSWindows does not support one-file-system option
        exclude_patterns = self.repo_config.g("backup_opts.exclude_patterns")
        if not isinstance(exclude_patterns, list):
            exclude_patterns = [exclude_patterns]

        exclude_files = self.repo_config.g("backup_opts.exclude_files")
        if not isinstance(exclude_files, list):
            exclude_files = [exclude_files]

        exclude_patterns_case_ignore = self.repo_config.g("backup_opts.exclude_patterns_case_ignore")
        exclude_caches = self.repo_config.g("backup_opts.exclude_caches")
        one_file_system = self.config.g("backup_opts.one_file_system") if os.name != 'nt' else False
        use_fs_snapshot = self.config.g("backup_opts.use_fs_snapshot")

        pre_exec_commands = self.config.g("backup_opts.pre_exec_commands")
        pre_exec_per_command_timeout = self.config.g("backup_opts.pre_exec_per_command_timeout")
        pre_exec_failure_is_fatal = self.config.g("backup_opts.pre_exec_failure_is_fatal")

        post_exec_commands = self.config.g("backup_opts.post_exec_commands")
        post_exec_per_command_timeout = self.config.g("backup_opts.post_exec_per_command_timeout")
        post_exec_failure_is_fatal = self.config.g("backup_opts.post_exec_failure_is_fatal")

        # Make sure we convert tag to list if only one tag is given
        try:
            tags = self.repo_config.g("backup_opts.tags")
            if not isinstance(tags, list):
                tags = [tags]
        except KeyError:
            tags = None

        additional_backup_only_parameters = self.repo_config.g("backup_opts.additional_backup_only_parameters")


        # Check if backup is required
        self.restic_runner.verbose = False
        if not self.restic_runner.is_init:
            if not self.restic_runner.init():
                logger.error("Cannot continue.")
                return False
        if self.check_recent_backups() and not force:
            logger.info("No backup necessary.")
            return True
        self.restic_runner.verbose = self.verbose

        # Run backup here
        if exclude_patterns_source_type not in ["folder_list", None]:
            logger.info("Running backup of files in {} list".format(paths))
        else:
            logger.info("Running backup of {}".format(paths))

        if pre_exec_commands:
            for pre_exec_command in pre_exec_commands:
                exit_code, output = command_runner(
                    pre_exec_command, shell=True, timeout=pre_exec_per_command_timeout
                )
                if exit_code != 0:
                    logger.error(
                        "Pre-execution of command {} failed with:\n{}".format(
                            pre_exec_command, output
                        )
                    )
                    if pre_exec_failure_is_fatal:
                        return False
                else:
                    logger.info(
                        "Pre-execution of command {} success with:\n{}.".format(
                            pre_exec_command, output
                        )
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
        logger.debug("Restic output:\n{}".format(result_string))
        metric_writer(
            self.repo_config, result, result_string, self.restic_runner.dry_run
        )

        if post_exec_commands:
            for post_exec_command in post_exec_commands:
                exit_code, output = command_runner(
                    post_exec_command, shell=True, timeout=post_exec_per_command_timeout
                )
                if exit_code != 0:
                    logger.error(
                        "Post-execution of command {} failed with:\n{}".format(
                            post_exec_command, output
                        )
                    )
                    if post_exec_failure_is_fatal:
                        return False
                else:
                    logger.info(
                        "Post-execution of command {} success with:\n{}.".format(
                            post_exec_command, output
                        )
                    )
        return result

    @exec_timer
    def restore(self, snapshot: str, target: str, restore_includes: List[str]) -> bool:
        if not self.is_ready:
            return False
        logger.info("Launching restore to {}".format(target))
        result = self.restic_runner.restore(
            snapshot=snapshot,
            target=target,
            includes=restore_includes,
        )
        return result

    @exec_timer
    def forget(self, snapshot: str) -> bool:
        if not self.is_ready:
            return False
        logger.info("Forgetting snapshot {}".format(snapshot))
        result = self.restic_runner.forget(snapshot)
        return result

    @exec_timer
    def check(self, read_data: bool = True) -> bool:
        if not self.is_ready:
            return False
        logger.info("Checking repository")
        result = self.restic_runner.check(read_data)
        return result

    @exec_timer
    def prune(self) -> bool:
        if not self.is_ready:
            return False
        logger.info("Pruning snapshots")
        result = self.restic_runner.prune()
        return result

    @exec_timer
    def repair(self, order: str) -> bool:
        if not self.is_ready:
            return False
        logger.info("Repairing {} in repo".format(order))
        result = self.restic_runner.repair(order)
        return result

    @exec_timer
    def raw(self, command: str) -> bool:
        logger.info("Running raw command: {}".format(command))
        result = self.restic_runner.raw(command=command)
        return result

    def group_runner(
        self, operations_config: dict, result_queue: Optional[queue.Queue]
    ) -> bool:
        print(operations_config)
        print("run to the hills")
