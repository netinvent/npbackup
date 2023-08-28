#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.restic_wrapper"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023082801"
__version__ = "1.7.2"


from typing import Tuple, List, Optional, Callable, Union
import os
from logging import getLogger
import re
import json
from datetime import datetime, timezone
import dateutil.parser
import queue
from command_runner import command_runner


logger = getLogger(__intname__)

# Arbitrary timeout for init / init checks.
# If init takes more than a minute, we really have a problem
INIT_TIMEOUT = 60


class ResticRunner:
    def __init__(
        self,
        repository: str,
        password: str,
        binary_search_paths: List[str] = None,
    ) -> None:
        self.repository = str(repository).strip()
        self.password = str(password).strip()
        self._verbose = False
        self._dry_run = False
        self._stdout = None
        self._binary = None
        self.binary_search_paths = binary_search_paths
        self._get_binary()

        self._is_init = None
        self._exec_time = None
        self._last_command_status = False
        self._limit_upload = None
        self._limit_download = None
        self._backend_connections = None
        self._priority = None
        try:
            backend = self.repository.split(":")[0].upper()
            if backend in [
                "REST",
                "S3",
                "B2",
                "SFTP",
                "SWIFT",
                "AZURE",
                "GZ",
                "RCLONE",
            ]:
                self._backend_type = backend.lower()
            else:
                self._backend_type = "local"
        except AttributeError:
            self._backend_type = None
        self._ignore_cloud_files = True
        self._addition_parameters = None
        self._environment_variables = {}

        self._stop_on = (
            None  # Function which will make executor abort if result is True
        )
        self._executor_finished = False  # Internal value to check whether executor is done, accessed via self.executor_finished property
        self._stdout = None  # Optional outputs when command is run as thread

    def on_exit(self) -> bool:
        self._executor_finished = True
        return self._executor_finished

    def _make_env(self) -> None:
        """
        Configures environment for repository & password
        """
        if self.password:
            try:
                os.environ["RESTIC_PASSWORD"] = str(self.password)
            except TypeError:
                logger.error("Bogus restic password")
                self.password = None
        if self.repository:
            try:
                if self._backend_type == "local":
                    self.repository = os.path.expanduser(self.repository)
                    self.repository = os.path.expandvars(self.repository)
                os.environ["RESTIC_REPOSITORY"] = str(self.repository)
            except TypeError:
                logger.error("Bogus restic repository")
                self.repository = None

        for env_variable, value in self.environment_variables.items():
            logger.debug('Setting envrionment variable "{}"'.format(env_variable))
            os.environ[env_variable] = value

        # Configure default cpu usage when not specifically set
        if not "GOMAXPROCS" in self.environment_variables:
            nb_cores = os.cpu_count()
            if nb_cores < 2:
                gomaxprocs = nb_cores
            elif 2 <= nb_cores <= 4:
                gomaxprocs = nb_cores - 1
            elif nb_cores > 4:
                gomaxprocs = nb_cores - 2
            logger.debug("Setting GOMAXPROCS to {}".format(gomaxprocs))
            os.environ["GOMAXPROCS"] = str(gomaxprocs)

    def _remove_env(self) -> None:
        """
        Unsets repository & password environment, we don't need to keep that data when not requested
        """
        os.environ["RESTIC_PASSWORD"] = "o_O"
        os.environ["RESTIC_REPOSITORY"] = self.repository.split(":")[0] + ":o_O"

        for env_variable in self.environment_variables.keys():
            os.environ[env_variable] = "__ooOO(° °)OOoo__"

    @property
    def stop_on(self) -> Callable:
        return self._stop_on

    @stop_on.setter
    def stop_on(self, fn: Callable) -> None:
        self._stop_on = fn

    @property
    def stdout(self) -> Optional[Union[int, str, Callable, queue.Queue]]:
        return self._stdout

    @stdout.setter
    def stdout(self, value: Optional[Union[int, str, Callable, queue.Queue]]):
        self._stdout = value

    @property
    def verbose(self) -> bool:
        return self._verbose

    @verbose.setter
    def verbose(self, value):
        if isinstance(value, bool):
            self._verbose = value
        else:
            raise ValueError("Bogus verbose value given")

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    @dry_run.setter
    def dry_run(self, value: bool):
        if isinstance(value, bool):
            self._dry_run = value
        else:
            raise ValueError("Bogus dry run value givne")

    @property
    def ignore_cloud_files(self) -> bool:
        return self._ignore_cloud_files

    @ignore_cloud_files.setter
    def ignore_cloud_files(self, value):
        if isinstance(value, bool):
            self._ignore_cloud_files = value
        else:
            raise ValueError("Bogus ignore_cloud_files value given")

    @property
    def exec_time(self) -> Optional[int]:
        return self._exec_time

    @exec_time.setter
    def exec_time(self, value: int):
        self._exec_time = value

    def executor(
        self,
        cmd: str,
        errors_allowed: bool = False,
        timeout: int = None,
        live_stream=False,
    ) -> Tuple[bool, str]:
        """
        Executes restic with given command

        When using live_stream, we'll have command_runner fill stdout queue, which is useful for interactive GUI programs, but slower, especially for ls operation

        """
        start_time = datetime.utcnow()
        self._executor_finished = False
        _cmd = '"{}" {}{}'.format(self._binary, cmd, self.generic_arguments)
        if self.dry_run:
            _cmd += " --dry-run"
        logger.debug("Running command: [{}]".format(_cmd))
        self._make_env()
        if live_stream:
            exit_code, output = command_runner(
                _cmd,
                timeout=timeout,
                split_streams=False,
                encoding="utf-8",
                live_output=self.verbose,
                valid_exit_codes=errors_allowed,
                stdout=self._stdout,
                stop_on=self.stop_on,
                on_exit=self.on_exit,
                method="poller",
                priority=self.priority,
                io_priority=self.priority,
            )
        else:
            exit_code, output = command_runner(
                _cmd,
                timeout=timeout,
                split_streams=False,
                encoding="utf-8",
                live_output=self.verbose,
                valid_exit_codes=errors_allowed,
                stop_on=self.stop_on,
                on_exit=self.on_exit,
                method="monitor",
                priority=self._priority,
                io_priority=self._priority,
            )
        # Don't keep protected environment variables in memory when not necessary
        self._remove_env()

        self._executor_finished = True
        self.exec_time = (datetime.utcnow() - start_time).total_seconds

        if exit_code == 0:
            self.last_command_status = True
            return True, output
        if exit_code == 3 and os.name == "nt" and self.ignore_cloud_files:
            # TEMP-FIX-4155, since we don't have reparse point support for Windows, see https://github.com/restic/restic/issues/4155, we have to filter manually for cloud errors which should not affect backup result
            # exit_code = 3 when errors are present but snapshot could be created
            # Since errors are always shown, we don't need restic --verbose option explicitly

            # We enhanced the error detection with :.*cloud.* since Windows can't have ':' in filename, it should be safe to use
            is_cloud_error = True
            for line in output.split("\n"):
                if re.match("error", line, re.IGNORECASE):
                    if not re.match(
                        r"error: read .*: The cloud operation is not supported on a read-only volume\.|error: read .*: The media is write protected\.|error: read .*:.*cloud.*",
                        line,
                        re.IGNORECASE,
                    ):
                        is_cloud_error = False
            if is_cloud_error is True:
                return True, output
            # TEMP-FIX-4155-END
        self.last_command_status = False

        # From here, we assume that we have errors
        # We'll log them unless we tried to know if the repo is initialized
        if not errors_allowed and output:
            logger.error(output)
        return False, output

    @property
    def executor_finished(self) -> bool:
        return self._executor_finished

    def _get_binary(self) -> None:
        """
        Make sure we find restic binary depending on platform
        """
        # This is the path to a onefile executable binary
        # When run with nuitka onefile, this will be the temp directory
        if not self.binary_search_paths:
            self.binary_search_paths = []

        if os.name == "nt":
            binary = "restic.exe"
            probe_paths = self.binary_search_paths + [
                "",
                os.path.join(os.environ.get("windir", ""), "SYSTEM32"),
                os.environ.get("windir", ""),
                os.path.join(os.environ.get("ProgramFiles", ""), "restic"),
            ]
        else:
            binary = "restic"
            probe_paths = self.binary_search_paths + ["", "/usr/bin", "/usr/local/bin"]

        for path in probe_paths:
            probed_path = os.path.join(path, binary)
            logger.debug('Probing for binary in "{}"'.format(probed_path))
            if os.path.isfile(probed_path):
                self._binary = probed_path
                return
        logger.error(
            "No backup engine binary found. Please install latest binary from restic.net"
        )

    @property
    def limit_upload(self):
        return self._limit_upload

    @limit_upload.setter
    def limit_upload(self, value: int):
        try:
            value = int(value)
            if value > 0:
                self._limit_upload = value
        except TypeError:
            raise ValueError("Cannot set upload limit")

    @property
    def limit_download(self):
        return self._limit_download

    @limit_download.setter
    def limit_download(self, value: int):
        try:
            value = int(value)
            if value > 0:
                self._limit_download = value
        except TypeError:
            raise ValueError("Cannot set download limit")

    @property
    def backend_connections(self):
        return self._backend_connections

    @backend_connections.setter
    def backend_connections(self, value: int):
        try:
            value = int(value)
            if value > 0:
                self._backend_connections = value
            elif value == 0:
                if self._backend_type == "local":
                    self._backend_connections = 2
                else:
                    self._backend_connections = 8

        except TypeError:
            logger.warning("Bogus backend_connections value given.")

    @property
    def additional_parameters(self):
        return self._addition_parameters

    @additional_parameters.setter
    def additional_parameters(self, value: str):
        self._addition_parameters = value

    @property
    def priority(self):
        return self._priority

    @priority.setter
    def priority(self, value: str):
        if value not in ["low", "normal", "high"]:
            raise ValueError("Bogus priority given.")
        self._priority = value

    @property
    def environment_variables(self):
        return self._environment_variables

    @environment_variables.setter
    def environment_variables(self, value):
        if not isinstance(value, dict):
            raise ValueError("Bogus environment variables set")
        self._environment_variables = value

    @property
    def binary(self):
        return self._binary

    @binary.setter
    def binary(self, value):
        if not os.path.isfile(value):
            raise ValueError("Non existent binary given: {}".format(value))
        self._binary = value

    @property
    def binary_version(self) -> Optional[str]:
        if self._binary:
            _cmd = "{} version".format(self._binary)
            exit_code, output = command_runner(
                _cmd,
                timeout=60,
                split_streams=False,
                encoding="utf-8",
                priority=self._priority,
                io_priority=self._priority,
            )
            if exit_code == 0:
                return output.strip()
            else:
                logger.error("Cannot get backend version: {}".format(output))
        else:
            logger.error("Cannot get backend version: No binary defined.")
        return None

    @property
    def generic_arguments(self):
        """
        Adds potential global arguments
        """
        args = ""
        if self.limit_upload:
            args += " --limit-upload {}".format(self.limit_upload)
        if self.limit_download:
            args += " --limit-download {}".format(self.limit_download)
        if self.backend_connections and self._backend_type != "local":
            args += " -o {}.connections={}".format(
                self._backend_type, self.backend_connections
            )
        if self.verbose:
            args += " -vv"
        return args

    def init(
        self,
        repository_version: int = 2,
        compression: str = "auto",
        errors_allowed: bool = False,
    ) -> bool:
        cmd = "init --repository-version {} --compression {}".format(
            repository_version, compression
        )
        result, output = self.executor(
            cmd, errors_allowed=errors_allowed, timeout=INIT_TIMEOUT
        )
        if result:
            if re.search(
                r"created restic repository ([a-z0-9]+) at .+", output, re.IGNORECASE
            ):
                return True
        else:
            if re.search(".*already exists", output, re.IGNORECASE):
                logger.info("Repo already initialized.")
                self.is_init = True
        return False

    @property
    def is_init(self):
        if self._is_init is None:
            self.init(errors_allowed=True)
        return self._is_init

    @is_init.setter
    def is_init(self, value: bool):
        self._is_init = value

    @property
    def last_command_status(self):
        return self._last_command_status

    @last_command_status.setter
    def last_command_status(self, value: bool):
        self._last_command_status = value

    def list(self, obj: str = "snapshots") -> Optional[list]:
        """
        Returns json list of snapshots
        """
        if not self.is_init:
            return None
        cmd = "list {} --json".format(obj)
        result, output = self.executor(cmd)
        if result:
            try:
                return json.loads(output)
            except json.decoder.JSONDecodeError:
                logger.error("Returned data is not JSON:\n{}".format(output))
                logger.debug("Trace:", exc_info=True)
        return None

    def ls(self, snapshot: str) -> Optional[list]:
        """
        Returns json list of objects
        """
        if not self.is_init:
            return None
        cmd = "ls {} --json".format(snapshot)
        result, output = self.executor(cmd)
        if result and output:
            """
            # When not using --json, we must remove first line since it will contain a heading string like:
            # snapshot db125b40 of [C:\\GIT\\npbackup] filtered by [] at 2023-01-03 09:41:30.9104257 +0100 CET):
            return output.split("\n", 2)[2]

            Using --json here does not return actual json content, but lines with each file being a json... !
            """
            try:
                for line in output.split("\n"):
                    if line:
                        yield json.loads(line)
            except json.decoder.JSONDecodeError:
                logger.error("Returned data is not JSON:\n{}".format(output))
                logger.debug("Trace:", exc_info=True)
        return result

    def snapshots(self) -> Optional[list]:
        """
        Returns json list of snapshots
        """
        if not self.is_init:
            return None
        cmd = "snapshots --json"
        result, output = self.executor(cmd)
        if result:
            try:
                return json.loads(output)
            except json.decoder.JSONDecodeError:
                logger.error("Returned data is not JSON:\n{}".format(output))
                logger.debug("Trace:", exc_info=True)
                return False
        return None

    def backup(
        self,
        paths: List[str],
        source_type: str,
        exclude_patterns: List[str] = [],
        exclude_files: List[str] = [],
        exclude_case_ignore: bool = False,
        exclude_caches: bool = False,
        use_fs_snapshot: bool = False,
        tags: List[str] = [],
        one_file_system: bool = False,
        additional_parameters: str = None,
    ) -> Tuple[bool, str]:
        """
        Executes restic backup after interpreting all arguments
        """
        if not self.is_init:
            return None, None

        # Handle various source types
        if source_type in ["files_from", "files_from_verbatim", "files_from_raw"]:
            cmd = "backup"
            if source_type == "files_from":
                source_parameter = "--files-from"
            elif source_type == "files_from_verbatim":
                source_parameter = "--files-from-verbatim"
            elif source_type == "files_from_raw":
                source_parameter = "--files-from-raw"
            else:
                logger.error("Bogus source type given")
                return False, ""

            for path in paths:
                cmd += ' {} "{}"'.format(source_parameter, path)
        else:
            # make sure path is a list and does not have trailing slashes
            cmd = "backup {}".format(
                " ".join(['"{}"'.format(path.rstrip("/\\")) for path in paths])
            )

        case_ignore_param = ""
        # Always use case ignore excludes under windows
        if os.name == "nt" or exclude_case_ignore:
            case_ignore_param = "i"

        for exclude_pattern in exclude_patterns:
            if exclude_pattern:
                cmd += ' --{}exclude "{}"'.format(case_ignore_param, exclude_pattern)
        for exclude_file in exclude_files:
            if exclude_file:
                cmd += ' --{}exclude-file "{}"'.format(case_ignore_param, exclude_file)
        if exclude_caches:
            cmd += " --exclude-caches"
        if one_file_system:
            cmd += " --one-file-system"
        if use_fs_snapshot:
            if os.name == "nt":
                cmd += " --use-fs-snapshot"
                logger.info("Using VSS snapshot to backup")
            else:
                logger.warning(
                    "Parameter --use-fs-snapshot was given, which is only compatible with Windows"
                )
        for tag in tags:
            if tag:
                tag = tag.strip()
                cmd += " --tag {}".format(tag)
        if additional_parameters:
            cmd += " {}".format(additional_parameters)
        result, output = self.executor(cmd, live_stream=True)

        if (
            use_fs_snapshot
            and not result
            and re.search("VSS Error", output, re.IGNORECASE)
        ):
            logger.warning("VSS cannot be used. Backup will be done without VSS.")
            result, output = self.executor(
                cmd.replace(" --use-fs-snapshot", ""), live_stream=True
            )
        if result:
            return True, output
        return False, output

    def find(self, path: str) -> Optional[list]:
        """
        Returns find command
        """
        if not self.is_init:
            return None
        cmd = 'find "{}" --json'.format(path)
        result, output = self.executor(cmd)
        if result:
            logger.info("Successfuly found {}".format(path))
            try:
                return json.loads(output)
            except json.decoder.JSONDecodeError:
                logger.error("Returned data is not JSON:\n{}".format(output))
                logger.debug("Trace:", exc_info=True)
        logger.warning("Could not find path: {}".format(path))
        return None

    def restore(self, snapshot: str, target: str, includes: List[str] = None):
        """
        Restore given snapshot to directory
        """
        if not self.is_init:
            return None
        case_ignore_param = ""
        # Always use case ignore excludes under windows
        if os.name == "nt":
            case_ignore_param = "i"
        cmd = 'restore "{}" --target "{}"'.format(snapshot, target)
        if includes:
            for include in includes:
                if include:
                    cmd += ' --{}include "{}"'.format(case_ignore_param, include)
        result, output = self.executor(cmd)
        if result:
            logger.info("successfully restored data.")
            return True
        logger.critical("Data not restored: {}".format(output))
        return False

    def forget(self, snapshot: str) -> bool:
        """
        Execute forget command for given snapshot
        """
        if not self.is_init:
            return None
        cmd = "forget {}".format(snapshot)
        # We need to be verbose here since server errors will not stop client from deletion attempts
        verbose = self.verbose
        self.verbose = True
        result, output = self.executor(cmd)
        self.verbose = verbose
        if result:
            logger.info("successfully forgot snapshot.")
            return True
        logger.critical("Could not forge snapshot: {}".format(output))
        return False

    def raw(self, command: str) -> Tuple[bool, str]:
        """
        Execute plain restic command without any interpretation"
        """
        if not self.is_init:
            return None
        result, output = self.executor(command)
        if result:
            logger.info("successfully run raw command:\n{}".format(output))
            return True, output
        logger.critical("Raw command failed.")
        return False, output

    def has_snapshot_timedelta(self, delta: int = 1441) -> Optional[datetime]:
        """
        Checks if a snapshot exists that is newer that delta minutes
        Eg: if delta = -60 we expect a snapshot newer than an hour ago, and return True if exists
            if delta = +60 we expect a snpashot newer than one hour in future (!), and return True if exists
            returns False is too old snapshots exit
            returns None if no info available
        """
        if not self.is_init:
            return None
        try:
            snapshots = self.snapshots()
            if self.last_command_status is False:
                return None
            if not snapshots:
                return False

            tz_aware_timestamp = datetime.now(timezone.utc).astimezone()
            has_recent_snapshot = False
            for snapshot in snapshots:
                if re.match(
                    r"[0-9]{4}-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]\..*\+[0-2][0-9]:[0-9]{2}",
                    snapshot["time"],
                ):
                    backup_ts = dateutil.parser.parse(snapshot["time"])
                    snapshot_age_minutes = (
                        tz_aware_timestamp - backup_ts
                    ).total_seconds() / 60
                    if delta - snapshot_age_minutes > 0:
                        logger.debug(
                            "Recent snapshot {} of {} exists !".format(
                                snapshot["short_id"], snapshot["time"]
                            )
                        )
                        has_recent_snapshot = True
            if has_recent_snapshot:
                return backup_ts
            return False
        except IndexError as exc:
            logger.debug("snapshot information missing: {}".format(exc))
            logger.debug("Trace", exc_info=True)
            # No 'time' attribute in snapshot ?
            return None
