#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.cli_interface"


import os
import sys
from pathlib import Path
import atexit
from argparse import ArgumentParser
from datetime import datetime
import tempfile
import pidfile
import ofunctions.logger_utils
from ofunctions.process import kill_childs
from npbackup.path_helper import CURRENT_DIR
from npbackup.customization import (
    LICENSE_TEXT,
    LICENSE_FILE,
)
import npbackup.configuration
from npbackup.runner_interface import entrypoint
from npbackup.__version__ import version_string
from npbackup.__debug__ import _DEBUG
from npbackup.common import execution_logs
from npbackup.core.i18n_helper import _t
if os.name == "nt":
    from npbackup.windows.task import create_scheduled_task

# Nuitka compat, see https://stackoverflow.com/a/74540217
try:
    # pylint: disable=W0611 (unused-import)
    from charset_normalizer import md__mypyc  # noqa
except ImportError:
    pass


LOG_FILE = os.path.join(CURRENT_DIR, "{}.log".format(__intname__))
PID_FILE = os.path.join(tempfile.gettempdir(), "{}.pid".format(__intname__))


logger = ofunctions.logger_utils.logger_get_logger(LOG_FILE, debug=_DEBUG)


def cli_interface():
    parser = ArgumentParser(
        prog=f"{__intname__}",
        description="""Portable Network Backup Client\n
This program is distributed under the GNU General Public License and comes with ABSOLUTELY NO WARRANTY.\n
This is free software, and you are welcome to redistribute it under certain conditions; Please type --license for more info.""",
    )

    parser.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        type=str,
        default=None,
        required=False,
        help="Path to alternative configuration file (defaults to current dir/npbackup.conf)",
    )
    parser.add_argument(
        "--repo-name",
        dest="repo_name",
        type=str,
        default="default",
        required=False,
        help="Name of the repository to work with. Defaults to 'default'",
    )
    parser.add_argument("-b", "--backup", action="store_true", help="Run a backup")
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        default=False,
        help="Force running a backup regardless of existing backups age",
    )
    parser.add_argument(
        "-r",
        "--restore",
        type=str,
        default=None,
        required=False,
        help="Restore to path given by --restore",
    )
    parser.add_argument("-l", "--list", action="store_true", help="Show current snapshots")
    parser.add_argument(
        "--ls",
        type=str,
        default=None,
        required=False,
        help='Show content given snapshot. Use "latest" for most recent snapshot.',
    )
    parser.add_argument(
        "--find",
        type=str,
        default=None,
        required=False,
        help="Find full path of given file / directory",
    )
    parser.add_argument(
        "--forget",
        type=str,
        default=None,
        required=False,
        help='Forget given snapshot, or specify \"policy\" to apply retention policy',
    )
    parser.add_argument(
        "--quick-check",
        action="store_true",
        help="Quick check repository"
    )
    parser.add_argument(
        "--full-check",
        action="store_true",
        help="Full check repository"
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Prune data in repository"
    )
    parser.add_argument(
        "--prune-max",
        action="store_true",
        help="Prune data in repository reclaiming maximum space"
    )
    parser.add_argument(
        "--unlock",
        action="store_true",
        help="Unlock repository"
    )
    parser.add_argument(
        "--repair-index",
        action="store_true",
        help="Repair repo index"
    )
    parser.add_argument(
        "--repair-snapshots",
        action="store_true",
        help="Repair repo snapshots"
    )
    parser.add_argument(
        "--raw",
        type=str,
        default=None,
        required=False,
        help='Run raw command against backend.',
    )


    parser.add_argument(
        "--has-recent-snapshot", action="store_true", help="Check if a recent snapshot exists"
    )
    parser.add_argument(
        "--restore-include",
        type=str,
        default=None,
        required=False,
        help="Restore only paths within include path",
    )
    parser.add_argument(
        "--snapshot",
        type=str,
        default="latest",
        required=False,
        help="Choose which snapshot to use. Defaults to latest",
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
    args = parser.parse_args()

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

    if args.debug or _DEBUG:
        logger.setLevel(ofunctions.logger_utils.logging.DEBUG)

    if args.verbose:
        _VERBOSE = True

    if args.config_file:
        if not os.path.isfile(args.config_file):
            logger.critical(f"Config file {args.config_file} cannot be read.")
            sys.exit(70)
        CONFIG_FILE = args.config_file
    else:
        config_file = Path(f"{CURRENT_DIR}/npbackup.conf")
        if config_file.exists:
            CONFIG_FILE = config_file
        else:
            logger.critical("Cannot run without configuration file.")
            sys.exit(70)

    full_config = npbackup.configuration.load_config(CONFIG_FILE)
    if full_config:
        repo_config, _ = npbackup.configuration.get_repo_config(full_config, args.repo_name)
    else:
        logger.critical("Cannot obtain repo config")
        sys.exit(71)

    if not repo_config:
        message = _t("config_gui.no_config_available")
        logger.critical(message)
        sys.exit(72)

    # Prepare program run
    cli_args = {
        "repo_config": repo_config,
        "verbose": args.verbose,
        "dry_run": args.dry_run,
        "debug": args.debug,
        "operation": None,
        "op_args": {}
    }

    if args.backup:
        cli_args["operation"] = "backup"
        cli_args["op_args"] = {
            "force": args.force
        }
    elif args.restore:
        cli_args["operation"] = "restore"
        cli_args["op_args"] = {
            "snapshot": args.snapshot,
            "target": args.restore,
            "restore_include": args.restore_include
            }   
    elif args.list:
        cli_args["operation"] = "list"
    elif args.ls:
        cli_args["operation"] = "ls"
        cli_args["op_args"] = {
            "snapshot": args.snapshot
        }
    elif args.find:
        cli_args["operation"] = "find"
        cli_args["op_args"] = {
            "snapshot": args.snapshot,
            "path": args.find
        }
    elif args.forget:
        cli_args["operation"] = "forget"
        if args.forget == "policy":
            cli_args["op_args"] = {
                "use_policy": True
            }
        else:
            cli_args["op_args"] = {
                "snapshots": args.forget
            }
    elif args.quick_check:
        cli_args["operation"] = "check"
    elif args.full_check:
        cli_args["operation"] = "check"
        cli_args["op_args"] = {
            "read_data": True
        }
    elif args.prune:
        cli_args["operation"] = "prune"
    elif args.prune_max:
        cli_args["operation"] = "prune"
        cli_args["op_args"] = {
            "max": True
        }
    elif args.unlock:
        cli_args["operation"] = "unlock"
    elif args.repair_index:
        cli_args["operation"] = "repair"
        cli_args["op_args"] = {
            "subject": "index"
        }
    elif args.repair_snapshots:
        cli_args["operation"] = "repair"
        cli_args["op_args"] = {
            "subject": "snapshots"
        }
    elif args.raw:
        cli_args["operation"] = "raw"
        cli_args["op_args"] = {
            "command": args.raw
        }
    elif args.has_recent_snapshot:
        cli_args["operation"] = "has_recent_snapshot"
    
    if cli_args["operation"]:
        locking_operations = ["backup", "repair", "forget", "prune", "raw", "unlock"]
        # Program entry
        if cli_args["operation"] in locking_operations:
            try:
                with pidfile.PIDFile(PID_FILE):
                    entrypoint(**cli_args)
            except pidfile.AlreadyRunningError:
                logger.critical("Backup process already running. Will not continue.")
                # EXIT_CODE 21 = current backup process already running
                sys.exit(21)
        else:
            entrypoint(**cli_args)
    else:
        logger.warning("No operation has been requested")
        


def main():
    # Make sure we log execution time and error state at the end of the program
    atexit.register(
        execution_logs,
        datetime.utcnow(),
    )
    # kill_childs normally would not be necessary, but let's just be foolproof here (kills restic subprocess in all cases)
    atexit.register(
        kill_childs,
        os.getpid(),
    )
    try:
        cli_interface()
        sys.exit(logger.get_worst_logger_level())
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
