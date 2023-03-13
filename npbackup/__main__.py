#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup"
__author__ = "Orsiris de Jong"
__site__ = "https://www.netperfect.fr/npbackup"
__description__ = "NetPerfect Backup Client"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023031301"
__version__ = "2.2.0-rc6"


import os
import sys
import atexit
from argparse import ArgumentParser
import dateutil.parser
from datetime import datetime
import tempfile
import pidfile
import ofunctions.logger_utils
from ofunctions.process import kill_childs
# This is needed so we get no GUI version messages
try:
    import PySimpleGUI as sg
    import _tkinter
    _NO_GUI = False
except ImportError:
    _NO_GUI = True

from npbackup.customization import (
    PYSIMPLEGUI_THEME,
    OEM_ICON,
    LICENSE_TEXT,
    LICENSE_FILE,
)
from npbackup import configuration
from npbackup.windows.task import create_scheduled_task
from npbackup.core.runner import NPBackupRunner
from npbackup.core.i18n_helper import _t
from npbackup.path_helper import CURRENT_DIR, CURRENT_EXECUTABLE
from npbackup.upgrade_client.upgrader import need_upgrade
from npbackup.core.upgrade_runner import run_upgrade
if not _NO_GUI:
    from npbackup.gui.config import config_gui
    from npbackup.gui.main import main_gui
    from npbackup.gui.minimize_window import minimize_current_window
    sg.theme(PYSIMPLEGUI_THEME)
    sg.SetOptions(icon=OEM_ICON)


del sys.path[0]

# Nuitka compat, see https://stackoverflow.com/a/74540217
try:
    # pylint: disable=W0611 (unused-import)
    from charset_normalizer import md__mypyc  # noqa
except ImportError:
    pass


_DEBUG = False
_VERBOSE = False
LOG_FILE = os.path.join(CURRENT_DIR, "{}.log".format(__intname__))
CONFIG_FILE = os.path.join(CURRENT_DIR, "{}.conf".format(__intname__))
PID_FILE = os.path.join(tempfile.gettempdir(), "{}.pid".format(__intname__))


logger = ofunctions.logger_utils.logger_get_logger(LOG_FILE)


def execution_logs(start_time: datetime) -> None:
    """
    Try to know if logger.warning or worse has been called
    logger._cache contains a dict of values like {10: boolean, 20: boolean, 30: boolean, 40: boolean, 50: boolean}
    where
    10 = debug, 20 = info, 30 = warning, 40 = error, 50 = critical
    so "if 30 in logger._cache" checks if warning has been triggered
    ATTENTION: logger._cache does only contain cache of current main, not modules, deprecated in favor of
    ofunctions.ContextFilterWorstLevel
    """
    end_time = datetime.utcnow()

    logger_worst_level = 0
    for flt in logger.filters:
        if isinstance(flt, ofunctions.logger_utils.ContextFilterWorstLevel):
            logger_worst_level = flt.worst_level

    log_level_reached = "success"
    try:
        if logger_worst_level >= 40:
            log_level_reached = "errors"
        elif logger_worst_level >= 30:
            log_level_reached = "warnings"
    except AttributeError as exc:
        logger.error("Cannot get worst log level reached: {}".format(exc))
    logger.info(
        "ExecTime = {}, finished, state is: {}.".format(
            end_time - start_time, log_level_reached
        )
    )
    # using sys.exit(code) in a atexit function will swallow the exitcode and render 0


def interface():
    global _DEBUG
    global _VERBOSE
    global CONFIG_FILE

    parser = ArgumentParser(
        prog="{} {} - {}".format(__description__, __copyright__, __site__),
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
        "--config-gui",
        action="store_true",
        default=False,
        help="Show configuration GUI",
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
        help="Create task that runs every n minutes",
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
    if args.version:
        print("{} v{} {}".format(__intname__, __version__, __build__))
        sys.exit(0)

    if args.license:
        try:
            with open(LICENSE_FILE, "r", "utf-8") as file_handle:
                print(file_handle.read())
        except OSError:
            print(LICENSE_TEXT)
        sys.exit(0)

    if args.debug or os.environ.get("_DEBUG", "False").capitalize() == "True":
        _DEBUG = True
        logger.setLevel(ofunctions.logger_utils.logging.DEBUG)

    if args.verbose:
        _VERBOSE = True

    # Make sure we log execution time and error state at the end of the program
    if args.backup or args.restore or args.find or args.list or args.check:
        atexit.register(
            execution_logs,
            datetime.utcnow(),
        )

    if args.config_file:
        if not os.path.isfile(args.config_file):
            logger.critical("Given file {} cannot be read.".format(args.config_file))
        CONFIG_FILE = args.config_file

    # Program entry
    if args.config_gui:
        try:
            config_dict = configuration.load_config(CONFIG_FILE)
            if not config_dict:
                logger.error("Cannot load config file")
                sys.exit(24)
        except FileNotFoundError:
            logger.warning(
                'No configuration file found. Please use --config-file "path" to specify one or put a config file into current directory. Will create fresh config file in current directory.'
            )
            config_dict = configuration.empty_config_dict

        config_dict = config_gui(config_dict, CONFIG_FILE)
        sys.exit(0)

    logger.info("{} v{}".format(__intname__, __version__))
    if args.create_scheduled_task:
        try:
            result = create_scheduled_task(
                executable_path=CURRENT_EXECUTABLE,
                interval_minutes=int(args.create_scheduled_task),
            )
            if result:
                sys.exit(0)
            else:
                sys.exit(22)
        except ValueError:
            sys.exit(23)

    try:
        config_dict = configuration.load_config(CONFIG_FILE)
    except FileNotFoundError:
        config_dict = None

    if not config_dict:
        message = _t("config_gui.no_config_available")
        logger.error(message)

        if config_dict is None and not _NO_GUI:
            config_dict = configuration.empty_config_dict
            # If no arguments are passed, assume we are launching the GUI
            if len(sys.argv) == 1:
                minimize_current_window()
                try:
                    result = sg.Popup(
                        "{}\n\n{}".format(message, _t("config_gui.create_new_config")),
                        custom_text=(_t("generic._yes"), _t("generic._no")),
                        keep_on_top=True,
                    )
                    if result == _t("generic._yes"):
                        config_dict = config_gui(config_dict, CONFIG_FILE)
                        sg.Popup(_t("config_gui.saved_initial_config"))
                    else:
                        logger.error("No configuration created via GUI")
                        sys.exit(7)
                except _tkinter.TclError:
                    logger.info("Seems to be a headless server.")
                    parser.print_help(sys.stderr)
                    sys.exit(1)
        elif config_dict is False:
            logger.info("Bogus config file %s", CONFIG_FILE)
            if len(sys.argv) == 1:
                sg.Popup(_t("config_gui.bogus_config_file", config_file=CONFIG_FILE))
            sys.exit(7)

    if args.upgrade_conf:
        # Whatever we need to add here for future releases
        # Eg:

        logger.info("Upgrading configuration file to version %s", __version__)
        try:
            config_dict["identity"]
        except KeyError:
            # Create new section identity, as per upgrade 2.2.0rc2
            config_dict["identity"] = {"machine_id": "${HOSTNAME}"}
        configuration.save_config(CONFIG_FILE, config_dict)
        sys.exit(0)

    # Try to perform an auto upgrade if needed
    try:
        auto_upgrade = config_dict["options"]["auto_upgrade"]
    except KeyError:
        auto_upgrade = True
    try:
        auto_upgrade_interval = config_dict["options"]["interval"]
    except KeyError:
        auto_upgrade_interval = 10

    if (auto_upgrade and need_upgrade(auto_upgrade_interval)) or args.auto_upgrade:
        if args.auto_upgrade:
            logger.info("Running user initiated auto upgrade")
        else:
            logger.info("Running program initiated auto upgrade")
        result = run_upgrade(config_dict)
        if result:
            sys.exit(0)
        elif args.auto_upgrade:
            sys.exit(23)

    dry_run = False
    if args.dry_run:
        dry_run = True

    npbackup_runner = NPBackupRunner(config_dict=config_dict)
    npbackup_runner.dry_run = dry_run
    npbackup_runner.verbose = _VERBOSE

    if args.check:
        if npbackup_runner.check_recent_backups():
            sys.exit(0)
        else:
            sys.exit(2)

    if args.list:
        result = npbackup_runner.list()
        if result:
            for snapshot in result:
                try:
                    tags = snapshot["tags"]
                except KeyError:
                    tags = None
                logger.info(
                    "ID: {} Hostname: {}, Username: {}, Tags: {}, source: {}, time: {}".format(
                        snapshot["short_id"],
                        snapshot["hostname"],
                        snapshot["username"],
                        tags,
                        snapshot["paths"],
                        dateutil.parser.parse(snapshot["time"]),
                    )
                )
            sys.exit(0)
        else:
            sys.exit(2)

    if args.ls:
        result = npbackup_runner.ls(snapshot=args.ls)
        if result:
            logger.info("Snapshot content:")
            for entry in result:
                logger.info(entry)
            sys.exit(0)
        else:
            logger.error("Snapshot could not be listed.")
            sys.exit(2)

    if args.find:
        result = npbackup_runner.find(path=args.find)
        if result:
            sys.exit(0)
        else:
            sys.exit(2)
    try:
        with pidfile.PIDFile(PID_FILE):
            if args.backup:
                result = npbackup_runner.backup(force=args.force)
                if result:
                    logger.info("Backup finished.")
                    sys.exit(0)
                else:
                    logger.error("Backup operation failed.")
                    sys.exit(2)
            if args.restore:
                result = npbackup_runner.restore(
                    snapshot=args.restore_from_snapshot,
                    target=args.restore,
                    restore_includes=args.restore_include,
                )
                if result:
                    sys.exit(0)
                else:
                    sys.exit(2)

            if args.forget:
                result = npbackup_runner.forget(snapshot=args.forget)
                if result:
                    sys.exit(0)
                else:
                    sys.exit(2)

            if args.raw:
                result = npbackup_runner.raw(command=args.raw)
                if result:
                    sys.exit(0)
                else:
                    sys.exit(2)

    except pidfile.AlreadyRunningError:
        logger.warning("Backup process already running. Will not continue.")
        # EXIT_CODE 21 = current backup process already running
        sys.exit(21)

    if not _NO_GUI:
        # When no argument is given, let's run the GUI
        # Also, let's minimize the commandline window so the GUI user isn't distracted
        minimize_current_window()
        logger.info("Running GUI")
        try:
            version_string = "{} v{} {}\n{}".format(
                __intname__, __version__, __build__, __copyright__
            )
            with pidfile.PIDFile(PID_FILE):
                try:
                    main_gui(config_dict, CONFIG_FILE, version_string)
                except _tkinter.TclError:
                    logger.info("Seems to be a headless server.")
                    parser.print_help(sys.stderr)
                    sys.exit(1)
        except pidfile.AlreadyRunningError:
            logger.warning("Backup GUI already running. Will not continue")
            # EXIT_CODE 21 = current backup process already running
            sys.exit(21)
    else:
        parser.print_help(sys.stderr)


def main():
    try:
        # kill_childs normally would not be necessary, but let's just be foolproof here (kills restic subprocess in all cases)
        atexit.register(
            kill_childs,
            os.getpid(),
        )
        interface()
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
