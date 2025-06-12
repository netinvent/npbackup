import atexit
import os
from typing import Any

import psutil


class AlreadyRunningError(Exception):
    pass


class PIDFile(object):
    """
    Checks if a program with the same executable name already runs
    Can accept some form of concurrency by specifying check_full_commandline which would check the whole commandline instead of the executable
    Can also accept concurrency by specifying an arbitrary identifier
    """

    def __init__(
        self,
        filename: Any = "pidfile",
        check_full_commandline: bool = False,
        identifier: Any = None,
    ):
        self._process_name = psutil.Process(os.getpid()).cmdline()
        self._check_full_commandline = check_full_commandline
        self._file = str(filename)
        if not self._check_full_commandline:
            self._process_name = self.sanitize(self._process_name[0])
        else:
            self._process_name = "-".join(self._process_name)

        self._file = "{}-{}".format(self._file, self.sanitize(self._process_name))
        if identifier:
            self._file = "{}-{}".format(self._file, self.sanitize(identifier))

    @staticmethod
    def sanitize(filename: str) -> str:
        """
        Sanitizes the filename by replacing slashes and backslashes with dots.
        This is useful to ensure that the filename is valid across different filesystems.
        """
        return "".join(x for x in filename if x.isalnum())

    @property
    def is_running(self) -> bool:
        if not os.path.exists(self._file):
            return False

        with open(self._file, "r") as f:
            try:
                pid = int(f.read())
            except (OSError, ValueError):
                return False

        if not psutil.pid_exists(pid):
            return False

        try:
            cmd1 = psutil.Process(pid).cmdline()
            if not self._check_full_commandline:
                cmd1 = self.sanitize(cmd1[0])
            return cmd1 == self.sanitize("-".join(self._process_name))
        except psutil.AccessDenied:
            return False

    def close(self) -> None:
        if os.path.exists(self._file):
            try:
                os.unlink(self._file)
            except OSError:
                pass

    def __enter__(self) -> "PIDFile":
        if self.is_running:
            raise AlreadyRunningError

        with open(self._file, "w") as f:
            f.write(str(os.getpid()))

        atexit.register(self.close)

        return self

    def __exit__(self, *_) -> None:
        self.close()
        atexit.unregister(self.close)
