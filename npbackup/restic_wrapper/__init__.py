#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.restic_wrapper"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024110301"
__version__ = "2.3.3"


from typing import Tuple, List, Optional, Callable, Union
import os
import sys
from logging import getLogger
import re
from datetime import datetime, timezone
import dateutil.parser
import queue
from functools import wraps
from command_runner import command_runner
from ofunctions.misc import BytesConverter, fn_name
from npbackup.__debug__ import _DEBUG
from npbackup.__env__ import FAST_COMMANDS_TIMEOUT, CHECK_INTERVAL, HEARTBEAT_INTERVAL
from npbackup.path_helper import CURRENT_DIR
from npbackup.restic_wrapper import schema

try:
    import msgspec

    HAVE_MSGSPEC = True
except ImportError:
    # We may not have msgspec on Python 3.7
    import json

    HAVE_MSGSPEC = False

logger = getLogger()


class ResticRunner:
    def __init__(
        self,
        repository: str,
        password: str,
        binary_search_paths: List[str] = None,
    ) -> None:
        self._stdout = None
        self._stderr = None

        self.repository = str(repository).strip()
        self.password = str(password).strip()
        self._verbose = False
        self._live_output = False
        self._dry_run = False
        self._no_cache = False
        self._json_output = False
        self._struct_output = False

        self.backup_result_content = None

        self._binary = None
        self.binary_search_paths = binary_search_paths

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
        self._additional_parameters = None
        self._environment_variables = {}

        # Function which will make executor abort if result is True
        self._stop_on = None

        # Internal value to check whether executor is running, accessed via self.executor_running property
        self._executor_running = False

        # Error /warning messages to add for json output
        self.errors_for_json = []
        self.warnings_for_json = []

    def on_exit(self) -> bool:
        self._executor_running = False
        return self._executor_running

    def _make_env(self) -> None:
        """
        Configures environment for repository & password
        """
        if self.password:
            try:
                os.environ["RESTIC_PASSWORD"] = str(self.password)
            except TypeError:
                self.write_logs("Bogus restic password", level="critical")
                self.password = None
        if self.repository:
            try:
                if self._backend_type == "local":
                    self.repository = os.path.expanduser(self.repository)
                    self.repository = os.path.expandvars(self.repository)
                os.environ["RESTIC_REPOSITORY"] = str(self.repository)
            except TypeError:
                self.write_logs("Bogus restic repository", level="critical")
                self.repository = None

        for env_variable, value in self.environment_variables.items():
            self.write_logs(
                f'Setting envrionment variable "{env_variable}"', level="debug"
            )
            os.environ[env_variable] = value

        # Configure default cpu usage when not specifically set
        if not "GOMAXPROCS" in self.environment_variables:
            nb_cores = os.cpu_count()
            if nb_cores < 2:
                gomaxprocs = nb_cores
            elif 2 <= nb_cores <= 4:
                gomaxprocs = nb_cores - 1
            else:
                gomaxprocs = nb_cores - 2
            # No need to use write_logs here
            logger.debug("Setting GOMAXPROCS to {}".format(gomaxprocs))
            os.environ["GOMAXPROCS"] = str(gomaxprocs)

    def _remove_env(self) -> None:
        """
        Unsets repository & password environment, we don't need to keep that data when not requested
        """
        os.environ["RESTIC_PASSWORD"] = "o_O"
        os.environ["RESTIC_REPOSITORY"] = self.repository_anonymous

        for env_variable in self.environment_variables.keys():
            os.environ[env_variable] = "__ooOO(° °)OOoo__"

    @property
    def stdout(self) -> Optional[Union[int, str, Callable, queue.Queue]]:
        return self._stdout

    @stdout.setter
    def stdout(self, value: Optional[Union[int, str, Callable, queue.Queue]]):
        self._stdout = value

    @property
    def stderr(self) -> Optional[Union[int, str, Callable, queue.Queue]]:
        return self._stderr

    @stderr.setter
    def stderr(self, value: Optional[Union[int, str, Callable, queue.Queue]]):
        self._stderr = value

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
    def live_output(self) -> bool:
        return self._live_output

    @live_output.setter
    def live_output(self, value):
        if isinstance(value, bool):
            self._live_output = value
        else:
            raise ValueError("Bogus live_output value given")

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    @dry_run.setter
    def dry_run(self, value: bool):
        if isinstance(value, bool):
            self._dry_run = value
        else:
            raise ValueError("Bogus dry_run value given")

    @property
    def no_cache(self) -> bool:
        return self._no_cache

    @no_cache.setter
    def no_cache(self, value: bool):
        if isinstance(value, bool):
            self._no_cache = value
        else:
            raise ValueError("Bogus no_cache value given")

    @property
    def json_output(self) -> bool:
        return self._json_output

    @json_output.setter
    def json_output(self, value: bool):
        if isinstance(value, bool):
            self._json_output = value
        else:
            raise ValueError("Bogus json_output value given")

    @property
    def struct_output(self) -> bool:
        return self._struct_output

    @struct_output.setter
    def struct_output(self, value: bool):
        if isinstance(value, bool):
            self._struct_output = value
        else:
            raise ValueError("Bogus struct_output value given")

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

    @property
    def executor_running(self) -> bool:
        return self._executor_running

    @property
    def repository_anonymous(self):
        if self.repository:
            return self.repository.split(":")[0] + ":_(o_O)_hidden_by_npbackup"
        return None

    def write_logs(
        self,
        msg: str,
        level: str,
        raise_error: str = None,
        ignore_additional_json: bool = False,
    ):
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
            # pylint: disable=E1101 (no-member)
            self.stdout.put(msg)
        if self.stderr and level in ("critical", "error", "warning"):
            # pylint: disable=E1101 (no-member)
            self.stderr.put(msg)

        if not ignore_additional_json:
            if level in ("critical", "error"):
                self.errors_for_json.append(msg)
            if level == "warning":
                self.warnings_for_json.append(msg)

        if raise_error == "ValueError":
            raise ValueError(msg)
        if raise_error:
            raise Exception(msg)

    def executor(
        self,
        cmd: str,
        errors_allowed: bool = False,
        no_output_queues: bool = False,
        method: str = "poller",
        timeout: int = None,
        stdin=None,
    ) -> Tuple[bool, str]:
        """
        Executes restic with given command
        errors_allowed is needed since we're testing if repo is already initialized
        no_output_queues is needed since we don't want is_init output to be logged
        """
        start_time = datetime.now(timezone.utc)
        # pylint: disable=E1101 (no-member)
        additional_parameters = (
            f" {self.additional_parameters.strip()} "
            if self.additional_parameters
            else ""
        )
        _cmd = f'"{self._binary}"{additional_parameters}{self.generic_arguments} {cmd}'

        if self.dry_run:
            # Only some restic commands support --dry-run, and it must be added after the main command
            # eg restic --dry-run backup / doesn't work
            # but restic backup / --dry-run does
            operation = fn_name(1)
            if operation in ["backup", "forget", "prune", "restore", "rewrite"]:
                _cmd += " --dry-run"

        self._executor_running = True
        self.write_logs(f"Running command: [{_cmd}]", level="debug")
        self._make_env()

        exit_code, output = command_runner(
            _cmd,
            timeout=timeout,
            split_streams=False,
            encoding="utf-8",
            stdin=stdin,
            stdout=self.stdout if not no_output_queues and method == "poller" else None,
            stderr=self.stderr if not no_output_queues and method == "poller" else None,
            no_close_queues=True,
            valid_exit_codes=errors_allowed,
            stop_on=self.is_cancelled,
            on_exit=self.on_exit,
            method=method,
            # Live output is only useful in CLI non json mode
            # But must not be used with ls since restic may produce too much output
            live_output=self._live_output if method != "monitor" else False,
            check_interval=CHECK_INTERVAL,
            priority=self._priority,
            io_priority=self._priority,
            windows_no_window=True,
            heartbeat=HEARTBEAT_INTERVAL,
        )
        # Don't keep protected environment variables in memory when not necessary
        self._remove_env()

        # _executor_running = False is also set via on_exit function call
        self._executor_running = False
        self.exec_time = (datetime.now(timezone.utc) - start_time).total_seconds

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
                self.last_command_status = True
                return True, output
            else:
                self.write_logs("Some files could not be backed up", level="error")
            # TEMP-FIX-4155-END
        self.last_command_status = False

        # From here, we assume that we have errors
        # We'll log them unless we tried to know if the repo is initialized
        if not errors_allowed and output:
            # We won't write to stdout/stderr queues since command_runner already did that for us
            logger.error(output)
        return False, output

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
        self.write_logs(
            "No backup engine binary found. Please install latest binary from restic.net",
            level="error",
        )

    @property
    def limit_upload(self):
        return self._limit_upload

    @limit_upload.setter
    def limit_upload(self, value: str):
        try:
            # restic uses kbytes as upload speed unit
            value = int(BytesConverter(value).kbytes)
            if value > 0:
                self._limit_upload = value
        except TypeError:
            raise ValueError("Cannot set upload limit")

    @property
    def limit_download(self):
        return self._limit_download

    @limit_download.setter
    def limit_download(self, value: str):
        try:
            # restic uses kbytes as download speed unit
            value = int(BytesConverter(value).kbytes)
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
            self.write_logs("Bogus backend_connections value given.", level="warning")

    @property
    def additional_parameters(self):
        return self._additional_parameters

    @additional_parameters.setter
    def additional_parameters(self, value: str):
        self._additional_parameters = value

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
        version = self.binary_version
        self.write_logs(f"Using binary {version}", level="info")

    @property
    def binary_version(self) -> Optional[str]:
        if self._binary:
            _cmd = "{} version".format(self._binary)
            exit_code, output = command_runner(
                _cmd,
                timeout=FAST_COMMANDS_TIMEOUT,
                split_streams=False,
                encoding="utf-8",
                priority=self._priority,
                io_priority=self._priority,
            )
            if exit_code == 0:
                return output.strip()
            self.write_logs("Cannot get backend version: {output}", level="warning")
        else:
            self.write_logs(
                "Cannot get backend version: No binary defined.", level="error"
            )
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
        if self.json_output:
            args += " --json"
        if self.no_cache:
            args += " --no-cache"
        return args

    def init(
        self,
        repository_version: int = 2,
        compression: str = "auto",
    ) -> bool:
        """
        Init repository. Let's make sure we always run in JSON mode so we don't need
        horrendous regexes to find whether initialized

        --json output when inializing:
          {"message_type":"initialized","id":"8daef59e2ac4c86535ae3f7414fcac6534f270077176af3ebddd34c364cac3c2","repository":"c:\\testy"}
        --json output when already initialized (is not json !!!)
        """
        cmd = "init --repository-version {} --compression {}".format(
            repository_version, compression
        )
        result, output = self.executor(
            cmd,
            timeout=FAST_COMMANDS_TIMEOUT,
        )
        if result:
            if re.search(
                r"created restic repository ([a-z0-9]+) at .+|{\"message_type\":\"initialized\"",
                output,
                re.IGNORECASE,
            ):
                self.write_logs("Repo initialized successfully", level="info")
                self.is_init = True
                return True
        else:
            if re.search(
                ".*already exists|.*already initialized", output, re.IGNORECASE
            ):
                self.write_logs("Repo is already initialized.", level="info")
                self.is_init = True
                return True
            self.write_logs(f"Cannot contact repo: {output}", level="error")
            self.is_init = False
            return False
        self.is_init = False
        return False

    @property
    def is_init(self):
        """
        We'll just check if snapshots can be read
        """
        cmd = "snapshots"

        # Disable live output for this check
        live_output = self.live_output
        self.live_output = False
        self._is_init, output = self.executor(
            cmd,
            timeout=FAST_COMMANDS_TIMEOUT,
            errors_allowed=True,
            no_output_queues=True,
        )
        self.live_output = live_output
        if not self._is_init:
            self.write_logs("Repository is not initialized or accessible", level="info")
            output = output.replace(
                self.repository,
                self.repository_anonymous,
            )
        return self._is_init, output

    @is_init.setter
    def is_init(self, value: bool):
        self._is_init = value

    @property
    def last_command_status(self):
        return self._last_command_status

    @last_command_status.setter
    def last_command_status(self, value: bool):
        self._last_command_status = value

    # pylint: disable=E0213 (no-self-argument)
    def check_if_init(fn: Callable):
        """
        Decorator to check that we don't do anything unless repo is initialized
        Also auto init repo when backing up
        """

        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            is_init, output = self.is_init
            if not is_init:
                # pylint: disable=E1101 (no-member)
                if fn.__name__ == "backup":
                    init = self.init()
                    if not init:
                        msg = f"Could not initialize repo for backup operation"
                        self.write_logs(
                            msg,
                            level="critical",
                        )
                        return self.convert_to_json_output(False, output=msg)
                else:
                    # pylint: disable=E1101 (no-member)
                    output = output.replace(
                        self.repository,
                        self.repository_anonymous,
                    )
                    if (
                        "repository is already locked" in output
                        and fn.__name__ == "unlock"
                    ):
                        # our is ready check should not fail if repo is locked
                        pass
                    else:
                        msg = f"Backend is not ready to perform operation {fn.__name__}. Repo maybe inaccessible or not initialized. You can try to run a backup to initialize the repository:\n{output}."  # pylint: disable=E1101 (no-member)
                        return self.convert_to_json_output(False, msg=msg)
            # pylint: disable=E1102 (not-callable)
            return fn(self, *args, **kwargs)

        return wrapper

    def convert_to_json_output(self, result, output=None, msg=None, **kwargs):
        """
        result, output = command_runner results
        msg will be logged and used as reason on failure


        Converts restic --json output to parseable json

        as of restic 0.16.2:
        restic --list snapshots|index... --json returns brute strings, one per line !
        """
        if self.json_output:
            operation = fn_name(1)
            js = {
                "result": result,
                "operation": operation,
                "args": kwargs,
                "output": [],
                "additional_error_info": [],
                "additional_warning_info": [],
            }
            if result:
                if output:
                    if HAVE_MSGSPEC:
                        decoder = msgspec.json.Decoder()
                        ls_decoder = msgspec.json.Decoder(schema.LsNode)
                    is_first_line = True

                    for line in output.split("\n"):
                        if not line:
                            continue
                        if HAVE_MSGSPEC:
                            try:
                                if (
                                    not is_first_line
                                    and operation == "ls"
                                    and self.struct_output
                                ):
                                    js["output"].append(ls_decoder.decode(line))
                                else:
                                    js["output"].append(decoder.decode(line))
                                    is_first_line = False
                            except msgspec.DecodeError as exc:
                                # We may have a json decode error, but actually, we just want to get the output
                                # in any case, since restic might output non json data, but we need to
                                # convert it to json

                                # msg = f"JSON decode error: {exc} on content '{line}'"
                                # self.write_logs(msg, level="error")
                                # js["extended_info"] = msg
                                js["output"].append({"data": line})
                                # Don't alter result since restic might give non json result
                                # js["result"] = False
                        else:
                            try:
                                # pylint: disable=E0601 (used-before-assignment)
                                js["output"].append(json.loads(line))
                            except json.JSONDecodeError as exc:
                                # Same as above

                                # msg = f"JSON decode error: {exc} on content '{line}'"
                                # self.write_logs(msg, level="error")
                                # js["extended_info"] = msg
                                js["output"].append({"data": line})
                                # js["result"] = False
                    # If we only have one output, we don't need a list
                    if len(js["output"]) == 1:
                        js["output"] = js["output"][0]

                if msg:
                    self.write_logs(msg, level="info")
            else:
                if msg:
                    js["reason"] = msg
                    self.write_logs(msg, level="error")
                if output:
                    if HAVE_MSGSPEC:
                        try:
                            js["output"] = msgspec.json.decode(output)
                        except msgspec.DecodeError as exc:
                            # Save as above

                            # msg = f"JSON decode error: {exc} on output '{output}'"
                            # self.write_logs(msg, level="error")
                            # js["extended_info"] = msg
                            js["output"] = {"data": output}
                    else:
                        try:
                            # pylint: disable=E0601 (used-before-assignment)
                            js["output"] = json.loads(output)
                        except json.JSONDecodeError as exc:
                            # same as above
                            # msg = f"JSON decode error: {exc} on output '{output}'"
                            # self.write_logs(msg, level="error")
                            # js["extended_info"] = msg
                            js["output"] = {"data": output}
            if self.errors_for_json:
                js["additional_error_info"] += self.errors_for_json
            if self.warnings_for_json:
                js["additional_warning_info"] += self.warnings_for_json
            return js

        if result:
            if msg:
                self.write_logs(msg, level="info")
            # Don't return output as result, only bool result
            # if output:
            #    self.write_logs(output, level="info")
            return result
        if msg:
            self.write_logs(msg, level="error")
        return False

    @check_if_init
    def list(self, subject: str) -> Union[bool, str, dict]:
        """
        Returns list of snapshots

        restic won't really return json content, but rather lines of object without any formatting
        """
        kwargs = locals()
        kwargs.pop("self")

        if not subject:
            return self.convert_to_json_output(
                False, None, msg="list expects an object type given by --list", **kwargs
            )

        cmd = "list {}".format(subject)
        result, output = self.executor(cmd)
        if result:
            msg = f"Successfully listed {subject} objects"
        else:
            msg = f"Failed to list {subject} objects:\n{output}"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def ls(self, snapshot: str) -> Union[bool, str, dict]:
        """
        Returns list of objects in a snapshot

        # When not using --json, we must remove first line since it will contain a heading string like:
        # snapshot db125b40 of [C:\\GIT\\npbackup] filtered by [] at 2023-01-03 09:41:30.9104257 +0100 CET):
        return output.split("\n", 2)[2]

        Using --json here does not return actual json content, but lines with each file being a json...

        Also, restic may return millions of lines, which command_runner will be slow to read in poller mode
        so we need to setup monitor mode in this one
        """
        kwargs = locals()
        kwargs.pop("self")

        if not snapshot:
            return self.convert_to_json_output(
                False, None, msg="ls expects a snapshot id given by --ls", **kwargs
            )

        cmd = "ls {}".format(snapshot)
        result, output = self.executor(cmd, method="monitor")
        if result:
            msg = f"Successfuly listed snapshot {snapshot} content"
        else:
            msg = f"Could not list snapshot {snapshot} content:\n{output}"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def snapshots(self) -> Union[bool, str, dict]:
        """
        Returns a list of snapshots
        --json is directly parseable
        """
        kwargs = locals()
        kwargs.pop("self")

        cmd = "snapshots"
        result, output = self.executor(cmd, timeout=FAST_COMMANDS_TIMEOUT)
        if result:
            msg = "Snapshots listed successfully"
        else:
            msg = f"Could not list snapshots:\n{output}"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def backup(
        self,
        paths: List[str] = None,
        source_type: str = None,
        exclude_patterns: List[str] = [],
        exclude_files: List[str] = [],
        excludes_case_ignore: bool = False,
        exclude_caches: bool = False,
        exclude_files_larger_than: str = None,
        use_fs_snapshot: bool = False,
        tags: List[str] = [],
        one_file_system: bool = False,
        read_from_stdin: bool = False,
        stdin_from_command: str = None,
        stdin_filename: str = "stdin.data",
        additional_backup_only_parameters: str = None,
    ) -> Union[bool, str, dict]:
        """
        Executes restic backup after interpreting all arguments
        """
        kwargs = locals()
        kwargs.pop("self")

        cmd = "backup"

        if not read_from_stdin and not stdin_from_command:
            # Handle various source types
            if source_type in [
                "files_from",
                "files_from_verbatim",
                "files_from_raw",
            ]:
                cmd = "backup"
                if source_type == "files_from":
                    source_parameter = "--files-from"
                elif source_type == "files_from_verbatim":
                    source_parameter = "--files-from-verbatim"
                elif source_type == "files_from_raw":
                    source_parameter = "--files-from-raw"
                else:
                    self.write_logs("Bogus source type given", level="error")
                    return False, ""

                for path in paths:
                    cmd += ' {} "{}"'.format(source_parameter, path)
            else:
                # make sure path is a list and does not have trailing slashes, unless we're backing up root
                # We don't need to scan files for ETA, so let's add --no-scan
                cmd = "backup --no-scan {}".format(
                    " ".join(
                        [
                            '"{}"'.format(path.rstrip("/\\")) if path != "/" else path
                            for path in paths
                        ]
                    )
                )

            case_ignore_param = ""
            # Always use case ignore excludes under windows
            if os.name == "nt" or excludes_case_ignore:
                case_ignore_param = "i"

            for exclude_pattern in exclude_patterns:
                if exclude_pattern:
                    cmd += f' --{case_ignore_param}exclude "{exclude_pattern}"'
            for exclude_file in exclude_files:
                if exclude_file:
                    if os.path.isfile(exclude_file):
                        cmd += f' --{case_ignore_param}exclude-file "{exclude_file}"'
                    else:
                        expansion_path = os.path.join(
                            CURRENT_DIR, "excludes", os.path.basename(exclude_file)
                        )
                        self.write_logs(
                            f"Trying to expanding exclude file path to {expansion_path}",
                            level="info",
                        )
                        if os.path.isfile(expansion_path):
                            cmd += (
                                f' --{case_ignore_param}exclude-file "{expansion_path}"'
                            )
                        else:
                            self.write_logs(
                                f"Exclude file '{exclude_file}' not found",
                                level="error",
                            )

            if exclude_caches:
                cmd += " --exclude-caches"
            if exclude_files_larger_than:
                exclude_files_larger_than = int(
                    BytesConverter(exclude_files_larger_than).bytes
                )

            if exclude_files_larger_than:
                try:
                    # Default --exclude_larger_than unit is bytes
                    exclude_files_larger_than = int(
                        BytesConverter(exclude_files_larger_than)
                    )
                except ValueError:
                    warning = f"Bogus unit for exclude_files_larger_than value given: {exclude_files_larger_than}"
                    self.write_logs(warning, level="warning")
                    exclude_files_larger_than = None
                # In case of conversion to 0, avoid setting this value
                if exclude_files_larger_than == 0:
                    exclude_files_larger_than = None

                cmd += f" --exclude-larger-than {exclude_files_larger_than}"
            if one_file_system:
                cmd += " --one-file-system"
            if use_fs_snapshot:
                if os.name == "nt":
                    cmd += " --use-fs-snapshot"
                    self.write_logs("Using VSS snapshot to backup", level="info")
                else:
                    self.write_logs(
                        "Parameter --use-fs-snapshot was given, which is only compatible with Windows",
                        level="warning",
                    )

        for tag in tags:
            if tag:
                tag = tag.strip()
                cmd += " --tag {}".format(tag)
        if additional_backup_only_parameters:
            cmd += " {}".format(additional_backup_only_parameters)

        if read_from_stdin:
            cmd += " --stdin"
            if stdin_filename:
                cmd += f' --stdin-filename "{stdin_filename}"'
        if stdin_from_command:
            if stdin_filename:
                cmd += f' --stdin-filename "{stdin_filename}"'
            cmd += f" --stdin-from-command -- {stdin_from_command}"

        # Run backup without json output, as we could not compute the cloud errors in json output via regexes
        json_output = self.json_output
        self.json_output = False
        if read_from_stdin:
            result, output = self.executor(cmd, stdin=sys.stdin.buffer)
        else:
            result, output = self.executor(cmd)

        if (
            not read_from_stdin
            and use_fs_snapshot
            and not result
            and re.search("VSS Error", output, re.IGNORECASE)
        ):
            self.write_logs(
                "VSS cannot be used. Backup will be done without VSS.", level="error"
            )
            result, output = self.executor(cmd.replace(" --use-fs-snapshot", ""))
        self.json_output = json_output
        if result:
            msg = "Backend finished with success"
        else:
            msg = f"Backend failed operation:\n{output}"

        self.backup_result_content = output
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def find(self, path: str) -> Union[bool, str, dict]:
        """
        Returns find command
        --json produces a directly parseable format
        """
        kwargs = locals()
        kwargs.pop("self")

        if not path:
            return self.convert_to_json_output(
                False, None, msg="find expects aa path given by --find", **kwargs
            )

        cmd = f'find "{path}"'
        result, output = self.executor(cmd)
        if result:
            msg = "Find command succeed"
        else:
            msg = f"Could not find path {path}:\n{output}"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def restore(
        self, snapshot: str, target: str, includes: List[str] = None
    ) -> Union[bool, str, dict]:
        """
        Restore given snapshot to directory
        """
        kwargs = locals()
        kwargs.pop("self")

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
            msg = "Successfully restored data"
        else:
            msg = f"Data not restored:\n{output}"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def forget(
        self,
        snapshots: Optional[Union[List[str], Optional[str]]] = None,
        policy: Optional[dict] = None,
        group_by: Optional[List[str]] = None,
    ) -> Union[bool, str, dict]:
        """
        Execute forget command for given snapshot
        """
        kwargs = locals()
        kwargs.pop("self")

        if not snapshots and not policy:
            self.write_logs(
                "No valid snapshot or policy defined for pruning", level="error"
            )
            return False

        if snapshots:
            if isinstance(snapshots, list):
                cmds = []
                for snapshot in snapshots:
                    cmds.append(f"forget {snapshot}")
            else:
                cmds = [f"forget {snapshots}"]
        if policy:
            cmd = "forget"
            for key, value in policy.items():
                if key == "keep-tags":
                    if isinstance(value, list):
                        for tag in value:
                            if tag:
                                cmd += f" --keep-tag {tag}"
                else:
                    cmd += f" --{key.replace('_', '-')} {value}"
            if group_by:
                cmd += f' --group-by {",".join(group_by)}'
            cmds = [cmd]

        # We need to be verbose here since server errors will not stop client from deletion attempts
        verbose = self.verbose
        self.verbose = True
        batch_result = True
        batch_output = ""
        if cmds:
            for cmd in cmds:
                result, output = self.executor(cmd)
                # NPF-RESTIC-00001
                # restic output inconsistency: non existing snapshot IDs still produce exit code 0
                if result and not "no matching ID found for prefix" in output:
                    msg = f"Successfully {'applied retention policy' if policy else 'forgot snapshot'}"
                    self.write_logs(
                        msg,
                        level="info",
                    )
                    batch_output += f"\n{msg}"
                else:
                    self.write_logs(f"Forget failed\n{output}", level="error")
                    batch_result = False
                    batch_output += f"\n{output}"
        self.verbose = verbose
        return self.convert_to_json_output(batch_result, batch_output, **kwargs)

    @check_if_init
    def prune(
        self, max_unused: Optional[str] = None, max_repack_size: Optional[int] = None
    ) -> Union[bool, str, dict]:
        """
        Prune forgotten snapshots
        """
        kwargs = locals()
        kwargs.pop("self")

        cmd = "prune"
        if max_unused:
            cmd += f"--max-unused {max_unused}"
        if max_repack_size:
            cmd += f"--max-repack-size {max_repack_size}"
        verbose = self.verbose
        self.verbose = True
        result, output = self.executor(cmd)
        self.verbose = verbose
        if result:
            msg = "Successfully pruned repository"
        else:
            msg = "Could not prune repository"
        return self.convert_to_json_output(result, output=output, msg=msg, **kwargs)

    @check_if_init
    def check(self, read_data: bool = True) -> Union[bool, str, dict]:
        """
        Check current repo status
        """
        kwargs = locals()
        kwargs.pop("self")

        cmd = "check{}".format(" --read-data" if read_data else "")
        result, output = self.executor(cmd)
        if result:
            msg = "Repo checked successfully."
        else:
            msg = "Repo check failed"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def repair(self, subject: str, pack_ids) -> Union[bool, str, dict]:
        """
        Check current repo status
        """
        kwargs = locals()
        kwargs.pop("self")

        if subject not in ["index", "packs", "snapshots"]:
            self.write_logs(f"Bogus repair order given: {subject}", level="error")
            return False
        cmd = f"repair {subject}"
        if pack_ids:
            cmd += f" {pack_ids}"
        result, output = self.executor(cmd)
        if result:
            msg = f"Repo successfully repaired:\n{output}"
        else:
            msg = f"Repo repair failed:\n{output}"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def recover(self) -> Union[bool, str, dict]:
        """
        Try to recover lost snapshots
        """
        kwargs = locals()
        kwargs.pop("self")

        cmd = f"recover"
        result, output = self.executor(cmd)
        if result:
            msg = f"Recovery succees"
        else:
            msg = f"Recovery failed:\n{output}"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def unlock(self) -> Union[bool, str, dict]:
        """
        Remove stale locks from repos
        """
        kwargs = locals()
        kwargs.pop("self")

        cmd = f"unlock"
        result, output = self.executor(cmd)
        if result:
            msg = f"Repo successfully unlocked"
        else:
            msg = f"Repo unlock failed:\n{output}"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def dump(self, path: str) -> Union[bool, str, dict]:
        """
        Dump given file directly to stdout
        """
        kwargs = locals()
        kwargs.pop("self")

        cmd = f'dump "{path}"'
        result, output = self.executor(cmd)
        if result:
            msg = f"File {path} successfully dumped"
        else:
            msg = f"Cannot dump file {path}:\n {output}"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def stats(self, subject: str = None) -> Union[bool, str, dict]:
        """
        Gives various repository statistics
        """
        kwargs = locals()
        kwargs.pop("self")

        cmd = f"stats"
        if subject:
            cmd += f" {subject}"
        result, output = self.executor(cmd)
        if result:
            msg = f"Repo statistics command success"
        else:
            msg = f"Cannot get repo statistics:\n {output}"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @check_if_init
    def raw(self, command: str) -> Union[bool, str, dict]:
        """
        Execute plain restic command without any interpretation"
        """
        kwargs = locals()
        kwargs.pop("self")

        result, output = self.executor(command)
        if result:
            msg = f"successfully run raw command:\n{output}"
        else:
            msg = "Raw command failed:\n{output}"
        return self.convert_to_json_output(result, output, msg=msg, **kwargs)

    @staticmethod
    def _has_recent_snapshot(
        snapshot_list: List, delta: int = None
    ) -> Tuple[bool, Optional[datetime]]:
        """
        Making the actual comparaison a static method so we can call it from GUI too

        Expects a restic snasphot_list (which is most recent at the end ordered)
        Returns bool if delta (in minutes) is not reached since last successful backup, and returns the last backup timestamp
        """
        backup_ts = datetime(1, 1, 1, 0, 0)
        # Don't bother to deal with mising delta or snapshot list
        if not snapshot_list or not delta:
            return False, backup_ts
        tz_aware_timestamp = datetime.now(timezone.utc).astimezone()

        # Now just take the last snapshot in list (being the more recent), and check whether it's too old
        last_snapshot = snapshot_list[-1]
        if re.match(
            r"[0-9]{4}-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9](\.\d*)?(\+[0-2][0-9]:[0-9]{2})?",
            last_snapshot["time"],
        ):
            backup_ts = dateutil.parser.parse(last_snapshot["time"])
            snapshot_age_minutes = (tz_aware_timestamp - backup_ts).total_seconds() / 60
            if delta - snapshot_age_minutes > 0:
                logger.info(
                    f"Recent snapshot {last_snapshot['short_id']} of {last_snapshot['time']} exists !"
                )
                return True, backup_ts
            return False, backup_ts

    #  @check_if_init  # We don't need to run if init before checking snapshots since if init searches for snapshots
    def has_recent_snapshot(self, delta: int = None) -> Tuple[bool, Optional[datetime]]:
        """
        Checks if a snapshot exists that is newer that delta minutes
        Eg: if delta = -60 we expect a snapshot newer than an hour ago, and return True if exists
            if delta = +60 we expect a snpashot newer than one hour in future (!)

            returns True, datetime if exists
            returns False, datetime if exists but too old
            returns False, datetime = 0001-01-01T00:00:00 if no snapshots found
            Returns None, None on error
        """
        kwargs = locals()
        kwargs.pop("self")

        # Don't bother to deal with mising delta
        if not delta:
            if self.json_output:
                msg = "No delta given"
                self.convert_to_json_output(False, None, msg=msg, **kwargs)
            return False, None
        try:
            # Make sure we run with json support for this one
            json_output = self.json_output
            self.json_output = True
            result = self.snapshots()
            self.json_output = json_output
            if self.last_command_status is False:
                if self.json_output:
                    msg = "Could not check for snapshots"
                    return self.convert_to_json_output(False, None, msg=msg, **kwargs)
                return False, None
            snapshots = result["output"]
            result, timestamp = self._has_recent_snapshot(snapshots, delta)
            if self.json_output:
                return self.convert_to_json_output(result, timestamp, **kwargs)
            return result, timestamp
        except IndexError as exc:
            self.write_logs(f"snapshot information missing: {exc}", level="error")
            logger.debug("Trace", exc_info=True)
            # No 'time' attribute in snapshot ?
            if self.json_output:
                return self.convert_to_json_output(None, None, **kwargs)
            return None, None

    def cancel(self):
        """
        Makes executor stop on next tick
        """
        self._stop_on = True

    def is_cancelled(self):
        return self._stop_on
