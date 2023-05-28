#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.runner"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023052801"


from typing import Optional, Callable, Union, List
import os
import logging
import queue
import datetime
from functools import wraps
from command_runner import command_runner
from ofunctions.platform import os_arch
from npbackup.restic_metrics import restic_output_2_metrics, upload_metrics
from npbackup.restic_wrapper import ResticRunner
from npbackup.core.restic_source_binary import get_restic_internal_binary
from npbackup.path_helper import CURRENT_DIR, BASEDIR
from npbackup.__main__ import __intname__ as NAME, __version__ as VERSION
from npbackup import configuration


logger = logging.getLogger(__intname__)


def metric_writer(config_dict: dict, restic_result: bool, result_string: str):
    try:
        labels = {}
        if config_dict["prometheus"]["metrics"]:
            try:
                labels["instance"] = configuration.evaluate_variables(
                    config_dict, config_dict["prometheus"]["instance"]
                )
            except (KeyError, AttributeError):
                labels["instance"] = None
            try:
                labels["backup_job"] = configuration.evaluate_variables(
                    config_dict, config_dict["prometheus"]["backup_job"]
                )
            except (KeyError, AttributeError):
                labels["backup_job"] = None
            try:
                labels["group"] = configuration.evaluate_variables(
                    config_dict, config_dict["prometheus"]["group"]
                )
            except (KeyError, AttributeError):
                labels["group"] = None
            try:
                destination = configuration.evaluate_variables(
                    config_dict, config_dict["prometheus"]["destination"]
                )
            except (KeyError, AttributeError):
                destination = None
            try:
                no_cert_verify = config_dict["prometheus"]["no_cert_verify"]
            except (KeyError, AttributeError):
                no_cert_verify = False
            try:
                prometheus_additional_labels = config_dict["prometheus"][
                    "additional_labels"
                ]
                if not isinstance(prometheus_additional_labels, list):
                    prometheus_additional_labels = [prometheus_additional_labels]
            except (KeyError, AttributeError):
                prometheus_additional_labels = None

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
            if destination.lower().startswith("file://"):
                destination = destination[len("file://") :]
                with open(destination, "w") as file_handle:
                    for metric in metrics:
                        file_handle.write(metric + "\n")
            if destination.lower().startswith("http"):
                try:
                    authentication = (
                        config_dict["prometheus"]["http_username"],
                        config_dict["prometheus"]["http_password"],
                    )
                except KeyError:
                    logger.info("No metrics authentication present.")
                    authentication = None
                upload_metrics(destination, authentication, no_cert_verify, metrics)
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

    def __init__(self, config_dict):
        self.config_dict = config_dict

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
            start_time = datetime.datetime.utcnow()
            # pylint: disable=E1102 (not-callable)
            result = fn(self, *args, **kwargs)
            self.exec_time = (datetime.datetime.utcnow() - start_time).total_seconds()
            logger.info("Runner took {} seconds".format(self.exec_time))
            return result

        return wrapper

    def create_restic_runner(self) -> None:
        can_run = True
        try:
            repository = self.config_dict["repo"]["repository"]
            if not repository:
                raise KeyError
        except (KeyError, AttributeError):
            logger.error("Repo cannot be empty")
            can_run = False
        try:
            password = self.config_dict["repo"]["password"]
        except (KeyError, AttributeError):
            logger.error("Repo password cannot be empty")
            can_run = False
        if not password or password == "":
            try:
                password_command = self.config_dict["repo"]["password_command"]
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
            if self.config_dict["repo"]["upload_speed"]:
                self.restic_runner.limit_upload = self.config_dict["repo"][
                    "upload_speed"
                ]
        except KeyError:
            pass
        except ValueError:
            logger.error("Bogus upload limit given.")
        try:
            if self.config_dict["repo"]["download_speed"]:
                self.restic_runner.limit_download = self.config_dict["repo"][
                    "download_speed"
                ]
        except KeyError:
            pass
        except ValueError:
            logger.error("Bogus download limit given.")
        try:
            if self.config_dict["repo"]["backend_connections"]:
                self.restic_runner.backend_connections = self.config_dict["repo"][
                    "backend_connections"
                ]
        except KeyError:
            pass
        except ValueError:
            logger.error("Bogus backend connections value given.")
        try:
            if self.config_dict["backup"]["priority"]:
                self.restic_runner.priority = self.config_dict["backup"]["priority"]
        except KeyError:
            pass
        except ValueError:
            logger.warning("Bogus backup priority in config file.")
        try:
            if self.config_dict["backup"]["ignore_cloud_files"]:
                self.restic_runner.ignore_cloud_files = self.config_dict["backup"][
                    "ignore_cloud_files"
                ]
        except KeyError:
            pass
        except ValueError:
            logger.warning("Bogus ignore_cloud_files value given")

        self.restic_runner.stdout = self.stdout

        try:
            env_variables = self.config_dict["env"]["variables"]
            if not isinstance(env_variables, list):
                env_variables = [env_variables]
        except KeyError:
            env_variables = []
        try:
            encrypted_env_variables = self.config_dict["env"]["encrypted_variables"]
            if not isinstance(encrypted_env_variables, list):
                encrypted_env_variables = [encrypted_env_variables]
        except KeyError:
            encrypted_env_variables = []

        expanded_env_vars = {}
        try:
            if env_variables:
                for env_variable in env_variables + encrypted_env_variables:
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
                self.config_dict["repo"]["minimum_backup_age"]
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
        logger.info(
            "Searching for a backup newer than {} ago.".format(
                str(datetime.timedelta(minutes=self.minimum_backup_age))
            )
        )
        self.restic_runner.verbose = False
        result = self.restic_runner.has_snapshot_timedelta(self.minimum_backup_age)
        self.restic_runner.verbose = self.verbose
        if result:
            logger.info("Most recent backup is from {}".format(result))
            return result
        elif result is False:
            logger.info("No recent backup found.")
        elif result is None:
            logger.error("Cannot connect to repository or repository empty.")
        return result

    @exec_timer
    def backup(self, force: bool = False) -> bool:
        """
        Run backup after checking if no recent backup exists, unless force == True
        """
        if not self.is_ready:
            return False
        # Preflight checks
        try:
            paths = self.config_dict["backup"]["paths"]
        except KeyError:
            logger.error("No backup paths defined.")
            return False

        # Make sure we convert paths to list if only one path is give
        # Also make sure we remove trailing and ending spaces
        try:
            if not isinstance(paths, list):
                paths = [paths]
            paths = [path.strip() for path in paths]
            for path in paths:
                if path == self.config_dict["repo"]["repository"]:
                    logger.critical(
                        "You cannot backup source into it's own path. No inception allowed !"
                    )
                    return False
        except KeyError:
            logger.error("No backup source given.")
            return False

        try:
            source_type = self.config_dict["backup"]["source_type"]
        except KeyError:
            source_type = None

        # MSWindows does not support one-file-system option
        try:
            exclude_patterns = self.config_dict["backup"]["exclude_patterns"]
            if not isinstance(exclude_patterns, list):
                exclude_patterns = [exclude_patterns]
        except KeyError:
            exclude_patterns = []
        try:
            exclude_files = self.config_dict["backup"]["exclude_files"]
            if not isinstance(exclude_files, list):
                exclude_files = [exclude_files]
        except KeyError:
            exclude_files = []
        try:
            exclude_case_ignore = self.config_dict["backup"]["exclude_case_ignore"]
        except KeyError:
            exclude_case_ignore = False
        try:
            exclude_caches = self.config_dict["backup"]["exclude_caches"]
        except KeyError:
            exclude_caches = False
        try:
            one_file_system = (
                self.config_dict["backup"]["one_file_system"]
                if os.name != "nt"
                else False
            )
        except KeyError:
            one_file_system = False
        try:
            use_fs_snapshot = self.config_dict["backup"]["use_fs_snapshot"]
        except KeyError:
            use_fs_snapshot = False
        try:
            pre_exec_command = self.config_dict["backup"]["pre_exec_command"]
        except KeyError:
            pre_exec_command = None

        try:
            pre_exec_timeout = self.config_dict["backup"]["pre_exec_timeout"]
        except KeyError:
            pre_exec_timeout = 0

        try:
            pre_exec_failure_is_fatal = self.config_dict["backup"][
                "pre_exec_failure_is_fatal"
            ]
        except KeyError:
            pre_exec_failure_is_fatal = None

        try:
            post_exec_command = self.config_dict["backup"]["post_exec_command"]
        except KeyError:
            post_exec_command = None

        try:
            post_exec_timeout = self.config_dict["backup"]["post_exec_timeout"]
        except KeyError:
            post_exec_timeout = 0

        try:
            post_exec_failure_is_fatal = self.config_dict["backup"][
                "post_exec_failure_is_fatal"
            ]
        except KeyError:
            post_exec_failure_is_fatal = None

        # Make sure we convert tag to list if only one tag is given
        try:
            tags = self.config_dict["backup"]["tags"]
            if not isinstance(tags, list):
                tags = [tags]
        except KeyError:
            tags = None

        try:
            additional_parameters = self.config_dict["backup"]["additional_parameters"]
        except KeyError:
            additional_parameters = None

        # Check if backup is required
        self.restic_runner.verbose = False
        if not self.restic_runner.is_init:
            self.restic_runner.init()
        if self.check_recent_backups() and not force:
            logger.info("No backup necessary.")
            return True
        self.restic_runner.verbose = self.verbose

        # Run backup here
        if source_type not in ["folder_list", None]:
            logger.info("Running backup of files in {} list".format(paths))
        else:
            logger.info("Running backup of {}".format(paths))

        if pre_exec_command:
            exit_code, output = command_runner(
                pre_exec_command, shell=True, timeout=pre_exec_timeout
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
                logger.debug(
                    "Pre-execution of command {} success with\n{}.".format(
                        pre_exec_command, output
                    )
                )

        self.restic_runner.dry_run = self.dry_run
        result, result_string = self.restic_runner.backup(
            paths=paths,
            source_type=source_type,
            exclude_patterns=exclude_patterns,
            exclude_files=exclude_files,
            exclude_case_ignore=exclude_case_ignore,
            exclude_caches=exclude_caches,
            one_file_system=one_file_system,
            use_fs_snapshot=use_fs_snapshot,
            tags=tags,
            additional_parameters=additional_parameters,
        )
        logger.debug("Restic output:\n{}".format(result_string))
        metric_writer(self.config_dict, result, result_string)

        if post_exec_command:
            exit_code, output = command_runner(
                post_exec_command, shell=True, timeout=post_exec_timeout
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
                logger.debug(
                    "Post-execution of command {} success with\n{}.".format(
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
    def raw(self, command: str) -> bool:
        logger.info("Running raw command: {}".format(command))
        result = self.restic_runner.raw(command=command)
        return result
