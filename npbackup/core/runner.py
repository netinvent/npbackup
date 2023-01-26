#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.core.runner"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023012101"


from typing import Optional, Callable, Union
import os
from logging import getLogger
import queue
from command_runner import command_runner
from ofunctions.platform import os_arch
from restic_metrics import restic_output_2_metrics, upload_metrics
from restic_wrapper import ResticRunner
import platform
from core.restic_source_binary import get_restic_internal_binary
from path_helper import CURRENT_DIR, BASEDIR
from version import NAME, BUILD, VERSION


logger = getLogger(__intname__)


def metric_writer(config: dict, restic_result: bool, result_string: str):
    try:
        if config["prometheus"]["metrics"]:
            # Evaluate variables
            if config["prometheus"]["instance"] == "${HOSTNAME}":
                instance = platform.node()
            else:
                instance = config["prometheus"]["instance"]
            if config["prometheus"]["backup_job"] == "${HOSTNAME}":
                backup_job = platform.node()
            else:
                backup_job = config["prometheus"]["backup_job"]
            try:
                prometheus_group = config["prometheus"]["group"]
            except (KeyError, AttributeError):
                prometheus_group = None
            try:
                prometheus_additional_labels = config["prometheus"]["additional_labels"]
            except (KeyError, AttributeError):
                prometheus_additional_labels = None

            destination = config["prometheus"]["destination"]
            destination = destination.replace("${BACKUP_JOB}", backup_job)

            # Configure lables
            labels = 'instance="{}",backup_job="{}"'.format(
                instance, backup_job
            )
            if prometheus_group:
                labels += ',group="{}"'.format(prometheus_group)

            try:
                # Make sure we convert prometheus_additional_labels to list if only one label is given
                if prometheus_additional_labels:
                    if not isinstance(prometheus_additional_labels, list):
                        prometheus_additional_labels = [prometheus_additional_labels]
                    for additional_label in prometheus_additional_labels:
                        label, value = additional_label.split("=")
                        labels += ',{}=\"{}\"'.format(label.strip(), value.strip())
            except (KeyError, AttributeError, TypeError, ValueError):
                logger.error("Bogus additional labels defined in configuration.")
                logger.debug("Trace:", exc_info=True)

            labels += ',npversion="{}{}"'.format(NAME, VERSION)


            errors, metrics = restic_output_2_metrics(
                restic_result=restic_result, output=result_string, labels=labels
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
                    authentication = (config["prometheus"]["http_username"], config["prometheus"]["http_password"])
                except KeyError:
                    logger.info("No metrics authentication present.")
                    authentication = None
                upload_metrics(destination, authentication, metrics)
    except KeyError as exc:
        logger.info("Metrics not configured: {}".format(exc))
    except OSError as exc:
        logger.error("Cannot write metric file: ".format(exc))


def runner(action: dict, config: dict, dry_run: bool = False, verbose: bool = False, stdout: Optional[Union[int, str, Callable, queue.Queue]] = None):
    try:
        repository = config["repo"]["repository"]
        password = config["repo"]["password"]
    except KeyError as exc:
        logger.error("Missing repo information: {}".format(exc))
        return None

    backup = ResticRunner(
        repository=repository, password=password, verbose=verbose, binary_search_paths=[BASEDIR, CURRENT_DIR]
    )


    if backup.binary is None:
        # Let's try to load our internal binary for dev purposes
        arch = os_arch()
        binary = get_restic_internal_binary(arch)
        if binary:
            backup.binary = binary
    
    if action['action'] == 'check-binary':
        if backup.binary:
            return True
        return False

    try:
        if config['repo']['upload_speed']:
            backup.limit_upload = config['repo']['upload_speed']
    except KeyError:
        pass
    except ValueError:
        logger.error("Bogus upload limit given.")
    try:
        if config['repo']['download_speed']:
            backup.limit_download = config['repo']['download_speed']
    except KeyError:
        pass
    except ValueError:
        logger.error("Bogus download limit given.")
    try:
        if config['repo']['backend_connections']:
            backup.backend_connections = config['repo']['backend_connections']
    except KeyError:
        pass
    except ValueError:
        logger.error("Bogus backend connections value given.")
    try:
        backup.additional_parameters = config['backup']['additional_parameters']
    except KeyError:
        pass
    try:
        if config['backup']['priority']:
            backup.priority = config['backup']['priority']
    except KeyError:
        pass
    except ValueError:
        logger.warning("Bogus backup priority in config file.")

    backup.stdout = stdout

    try:
        env_variables = config['env']['variables']
    except KeyError:
        env_variables = None

    expanded_env_vars = {}
    try:
        if env_variables:
            # Make sure we convert env_variables to list if only one label is given
            if not isinstance(env_variables, list):
                env_variables = [env_variables]
            for env_variable in env_variables:
                key, value = env_variable.split("=")
                expanded_env_vars[key.strip()] = value.strip()
    except (KeyError, AttributeError, TypeError, ValueError):
        logger.error("Bogus environment variables defined in configuration.")
        logger.debug("Trace:", exc_info=True)

    try:
        backup.environment_variables = expanded_env_vars
    except ValueError:
        logger.error("Cannot initialize additional environment variables")

    if action["action"] == "check":
        logger.info(
            "Searching for a backup newer than {} seconds ago.".format(
                config["repo"]["minimum_backup_age"]
            )
        )
        result = backup.has_snapshot_timedelta(config["repo"]["minimum_backup_age"])
        if result:
            logger.info("Most recent backup is from {}".format(result))
            return result
        elif result is False:
            logger.info("No recent backup found.")
        elif result is None:
            logger.error("Cannot connect to repository.")
        return False

    if action["action"] == "list":
        logger.info("Listing snapshots")
        snapshots = backup.snapshots()
        return snapshots

    if action["action"] == "ls":
        logger.info("Showing content of snapshot {}".format(action["snapshot"]))
        result = backup.ls(action["snapshot"])
        return result

    if action["action"] == "forget":
        logger.info("Deleting snapshot {}".format(action["snapshot"]))
        result = backup.forget(action["snapshot"])
        return result

    if action["action"] == "backup":
        logger.info("Running backup of {}".format(config["backup"]["paths"]))

        if not backup.is_init:
            backup.init()
        if (
            backup.has_snapshot_timedelta(config["repo"]["minimum_backup_age"])
            and not action["force"]
        ):
            logger.info("No backup necessary.")
            return True

        # Make sure we convert paths to list if only one path is given
        try:
            paths = config['backup']['paths']
            if not isinstance(paths, list):
                paths = [paths]
        except KeyError:
            logger.error("No backup source path given.")
            return False

        try:
            config["repo"]["minimum_backup_age"]
        except KeyError:
            config["repo"]["minimum_backup_age"] = 84600

        # MSWindows does not support one-file-system option
        try:
            exclude_patterns = config["backup"]["exclude_patterns"]
        except KeyError:
            exclude_patterns = []
        try:
            exclude_files = config["backup"]["exclude_files"]
        except KeyError:
            exclude_files = []
        try:
            exclude_case_ignore = config["backup"]["exclude_case_ignore"]
        except KeyError:
            exclude_case_ignore = False
        try:
            exclude_caches = config["backup"]["exclude_caches"]
        except KeyError:
            exclude_caches = False
        try:
            one_file_system = (
                config["backup"]["one_file_system"] if os.name != "nt" else False
            )
        except KeyError:
            one_file_system = False
        try:
            use_fs_snapshot = (
                config["backup"]["use_fs_snapshot"]
            )
        except KeyError:
            use_fs_snapshot = False
        try:
            pre_exec_command = config["backup"]['pre_exec_command']
        except KeyError:
            pre_exec_command = None

        try:
            pre_exec_timeout = config["backup"]['pre_exec_timeout']
        except KeyError:
            pre_exec_timeout = 0

        try:
            pre_exec_failure_is_fatal = config["backup"]['pre_exec_failure_is_fatal']
        except KeyError:
            pre_exec_failure_is_fatal = None


        try:
            post_exec_command = config["backup"]['post_exec_command']
        except KeyError:
            post_exec_command = None

        try:
            post_exec_timeout = config["backup"]['post_exec_timeout']
        except KeyError:
            post_exec_timeout = 0

        try:
            post_exec_failure_is_fatal = config["backup"]['post_exec_failure_is_fatal']
        except KeyError:
            post_exec_failure_is_fatal = None

        # Make sure we convert tag to list if only one tag is given
        try:
            tags = config['backup']['tags']
            if not isinstance(tags, list):
                tags = [tags]
        except KeyError:
            tags = None

        try:
            additional_parameters = config['backup']['additional_parameters']
        except KeyError:
            additional_parameters = None

        # Run backup here
        
        if pre_exec_command:
            exit_code, output = command_runner(pre_exec_command, shell=True, timeout=pre_exec_timeout)
            if exit_code != 0:
                logger.error("Pre-execution of command {} failed with:\n{}".format(pre_exec_command, output))
                if pre_exec_failure_is_fatal:
                    return False
            else:
                logger.debug("Pre-execution of command {} success with\n{}.".format(pre_exec_command, output))

        result, result_string = backup.backup(
            paths=paths,
            exclude_patterns=exclude_patterns,
            exclude_files=exclude_files,
            exclude_case_ignore=exclude_case_ignore,
            exclude_caches=exclude_caches,
            one_file_system=one_file_system,
            use_fs_snapshot=use_fs_snapshot,
            tags=tags,
            additional_parameters=additional_parameters,
            dry_run=dry_run,
        )
        logger.debug("Restic output:\n{}".format(result_string))
        metric_writer(config, result, result_string)
        
        if post_exec_command:
            exit_code, output = command_runner(post_exec_command, shell=True, timeout=post_exec_timeout)
            if exit_code != 0:
                logger.error("Post-execution of command {} failed with:\n{}".format(post_exec_command, output))
                if post_exec_failure_is_fatal:
                    return False
            else:
                logger.debug("Post-execution of command {} success with\n{}.".format(post_exec_command, output))
        return result

    if action["action"] == "find":
        logger.info("Searching for path {}".format(action["path"]))
        result = backup.find(path=action["path"])
        if result:
            logger.info("Found path in:\n")
            for line in result:
                logger.info(line)

    if action["action"] == "restore":
        logger.info("Launching restore to {}".format(action["target"]))
        result = backup.restore(
            snapshot=action["snapshot"],
            target=action["target"],
            includes=action["restore-include"],
        )
        return result

    if action["action"] == "has_recent_snapshots":
        logger.info("Checking for recent snapshots")
        result = backup.has_snapshot_timedelta(delta=config["repo"]["minimum_backup_age"])
        return result

    if action["action"] == "raw":
        logger.info("Running raw command: {}".format(action["command"]))
        result = backup.raw(command=action["command"])
        return result
