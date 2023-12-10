#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.cli_interface"


import os
import sys
from argparse import ArgumentParser
import ofunctions.logger_utils
from ofunctions.platform import python_arch
from npbackup.path_helper import CURRENT_DIR
from npbackup.configuration import IS_PRIV_BUILD
from npbackup.customization import (
    LICENSE_TEXT,
    LICENSE_FILE,
)
from npbackup.interface_entrypoint import entrypoint
from npbackup.__version__ import __intname__ as intname, __version__, __build__, __copyright__, __description__


_DEBUG = False
_VERBOSE = False
LOG_FILE = os.path.join(CURRENT_DIR, "{}.log".format(__intname__))


logger = ofunctions.logger_utils.logger_get_logger(LOG_FILE)

def cli_interface():
    global _DEBUG
    global _VERBOSE
    global CONFIG_FILE

    parser = ArgumentParser(
        prog=f"{__description__}",
        description="""Portable Network Backup Client\n
This program is distributed under the GNU General Public License and comes with ABSOLUTELY NO WARRANTY.\n
This is free software, and you are welcome to redistribute it under certain conditions; Please type --license for more info.""",
    )

    parser.add_argument(
        "--check", action="store_true", help="Check if a recent backup exists"
    )

    parser.add_argument("-b", "--backup", action="store_true", help="Run a backup")

    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force running a backup regardless of existing backups",
    )

    parser.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        type=str,
        default=None,
        required=False,
        help="Path to alternative configuration file",
    )

    parser.add_argument(
        "--repo-name",
        dest="repo_name",
        type=str,
        default="default",
        required=False,
        help="Name of the repository to work with. Defaults to 'default'"
    )

    parser.add_argument(
        "-l", "--list", action="store_true", help="Show current snapshots"
    )

    parser.add_argument(
        "--ls",
        type=str,
        default=None,
        required=False,
        help='Show content given snapshot. Use "latest" for most recent snapshot.',
    )

    parser.add_argument(
        "-f",
        "--find",
        type=str,
        default=None,
        required=False,
        help="Find full path of given file / directory",
    )

    parser.add_argument(
        "-r",
        "--restore",
        type=str,
        default=None,
        required=False,
        help="Restore to path given by --restore",
    )

    parser.add_argument(
        "--restore-include",
        type=str,
        default=None,
        required=False,
        help="Restore only paths within include path",
    )

    parser.add_argument(
        "--restore-from-snapshot",
        type=str,
        default="latest",
        required=False,
        help="Choose which snapshot to restore from. Defaults to latest",
    )

    parser.add_argument(
        "--forget", type=str, default=None, required=False, help="Forget snapshot"
    )
    parser.add_argument(
        "--raw", type=str, default=None, required=False, help="Raw commands"
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show verbose output"
    )
    parser.add_argument("-d", "--debug", action="store_true", help="Run with debugging")
    parser.add_argument(
        "-V", "--version", action="store_true", help="Show program version"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run operations in test mode (no actual modifications",
    )

    parser.add_argument(
        "--create-scheduled-task",
        type=str,
        default=None,
        required=False,
        help="Create task that runs every n minutes on Windows",
    )

    parser.add_argument("--license", action="store_true", help="Show license")
    parser.add_argument(
        "--auto-upgrade", action="store_true", help="Auto upgrade NPBackup"
    )
    parser.add_argument(
        "--upgrade-conf",
        action="store_true",
        help="Add new configuration elements after upgrade",
    )

    args = parser.parse_args()
    version_string = "{} v{}{}{}-{} {} - {}".format(
        intname,
        __version__,
        "-PRIV" if IS_PRIV_BUILD else "",
        "-P{}".format(sys.version_info[1]),
        python_arch(),
        __build__,
        __copyright__,
    )
    if args.version:
        print(version_string)
        sys.exit(0)

    logger.info(version_string)
    if args.license:
        try:
            with open(LICENSE_FILE, "r", encoding="utf-8") as file_handle:
                print(file_handle.read())
        except OSError:
            print(LICENSE_TEXT)
        sys.exit(0)

    if args.debug or os.environ.get("_DEBUG", "False").capitalize() == "True":
        _DEBUG = True
        logger.setLevel(ofunctions.logger_utils.logging.DEBUG)

    if args.verbose:
        _VERBOSE = True

    if args.config_file:
        if not os.path.isfile(args.config_file):
            logger.critical("Given file {} cannot be read.".format(args.config_file))
        CONFIG_FILE = args.config_file

    # Program entry
    entrypoint()

def main():
    try:
        cli_interface()
    except KeyboardInterrupt as exc:
        logger.error("Program interrupted by keyboard. {}".format(exc))
        logger.info("Trace:", exc_info=True)
        # EXIT_CODE 200 = keyboard interrupt
        sys.exit(200)
    except Exception as exc:
        logger.error("Program interrupted by error. {}".format(exc))
        logger.info("Trace:", exc_info=True)
        # EXIT_CODE 201 = Non handled exception
        sys.exit(201)


if __name__ == "__main__":
    main()
