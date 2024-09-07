#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup-cli"


import os
import sys
from pathlib import Path
import atexit
from time import sleep
from argparse import ArgumentParser
from datetime import datetime, timezone
from tempfile import gettempdir
import logging
import json
import ofunctions.logger_utils
from ofunctions.process import kill_childs
from npbackup.path_helper import CURRENT_DIR
from resources.customization import LICENSE_TEXT
import npbackup.configuration
from npbackup.runner_interface import entrypoint
from npbackup.__version__ import version_string, version_dict
from npbackup.__debug__ import _DEBUG
from npbackup.common import execution_logs
from npbackup.core import upgrade_runner
from npbackup.core.i18n_helper import _t
from npbackup import key_management
from npbackup.task import create_scheduled_task

# Nuitka compat, see https://stackoverflow.com/a/74540217
try:
    # pylint: disable=W0611 (unused-import)
    from charset_normalizer import md__mypyc  # noqa
except ImportError:
    pass


_JSON = False
logger = logging.getLogger()


def json_error_logging(result: bool, msg: str, level: str):
    if _JSON:
        js = {"result": result, "reason": msg}
        print(json.dumps(js))
    logger.__getattribute__(level)(msg)


def cli_interface():
    global _JSON
    global logger

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
        default=None,
        required=False,
        help="Name of the repository to work with. Defaults to 'default'. In group operation mode, this can be a comma separated list of repo names. Can accept special name '__all__' to work with all repositories.",
    )
    parser.add_argument(
        "--repo-group",
        type=str,
        default=None,
        required=False,
        help="Comme separated list of groups to work with. Can accept special name '__all__' to work with all repositories.",
    )
    parser.add_argument("-b", "--backup", action="store_true", help="Run a backup")
    parser.add_argument(
        "-f",
        "--force",
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
    parser.add_argument(
        "-s",
        "--snapshots",
        action="store_true",
        default=False,
        help="Show current snapshots",
    )
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
        help="Forget given snapshot",
    )
    parser.add_argument(
        "--policy",
        action="store_true",
        default=False,
        help="Apply retention policy to snapshots (forget snapshots)",
    )
    parser.add_argument(
        "--housekeeping",
        action="store_true",
        default=False,
        help="Run --check, --policy and --prune in one go",
    )
    parser.add_argument(
        "--quick-check", action="store_true", help="Quick check repository"
    )
    parser.add_argument(
        "--full-check",
        action="store_true",
        help="Full check repository (read all data)",
    )
    parser.add_argument("--prune", action="store_true", help="Prune data in repository")
    parser.add_argument(
        "--prune-max",
        action="store_true",
        help="Prune data in repository reclaiming maximum space",
    )
    parser.add_argument("--unlock", action="store_true", help="Unlock repository")
    parser.add_argument("--repair-index", action="store_true", help="Repair repo index")
    parser.add_argument(
        "--repair-packs",
        default=None,
        required=False,
        help="Repair repo packs ids given by --repair-packs",
    )
    parser.add_argument(
        "--repair-snapshots", action="store_true", help="Repair repo snapshots"
    )
    parser.add_argument(
        "--recover", action="store_true", help="Recover lost repo snapshots"
    )
    parser.add_argument(
        "--list",
        type=str,
        default=None,
        required=False,
        help="Show [blobs|packs|index|snapshots|keys|locks] objects",
    )
    parser.add_argument(
        "--dump",
        type=str,
        default=None,
        required=False,
        help="Dump a specific file to stdout",
    )
    parser.add_argument(
        "--stats",
        type=str,
        default=None,
        required=False,
        help="Get repository statistics. If snapshot id is given, only snapshots statistics will be shown.",
    )
    parser.add_argument(
        "--raw",
        type=str,
        default=None,
        required=False,
        help="Run raw command against backend.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Manually initialize a repo (is done automatically on first backup)",
    )
    parser.add_argument(
        "--has-recent-snapshot",
        action="store_true",
        help="Check if a recent snapshot exists",
    )
    parser.add_argument(
        "--restore-includes",
        type=str,
        default=None,
        required=False,
        help="Restore only paths within include path, comma separated list accepted",
    )
    parser.add_argument(
        "--snapshot-id",
        type=str,
        default="latest",
        required=False,
        help="Choose which snapshot to use. Defaults to latest",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Run in JSON API mode. Nothing else than JSON will be printed to stdout",
    )
    parser.add_argument(
        "--stdin", action="store_true", help="Backup using data from stdin input"
    )
    parser.add_argument(
        "--stdin-filename",
        type=str,
        default=None,
        help="Alternate filename for stdin, defaults to 'stdin.data'",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show verbose output"
    )
    parser.add_argument(
        "-V", "--version", action="store_true", help="Show program version"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run operations in test mode, no actual modifications",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Run operations without cache",
    )
    parser.add_argument("--license", action="store_true", help="Show license")
    parser.add_argument(
        "--auto-upgrade", action="store_true", help="Auto upgrade NPBackup"
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        required=False,
        help="Optional path for logfile",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        required=False,
        help="Show full inherited configuration for current repo",
    )
    parser.add_argument(
        "--external-backend-binary",
        type=str,
        default=None,
        required=False,
        help="Full path to alternative external backend binary",
    )
    parser.add_argument(
        "--group-operation",
        type=str,
        default=None,
        required=False,
        help="Launch an operation on a group of repositories given by --repo-group or --repo-name. Valid group operations are [backup|restore|snapshots|list|ls|find|policy|quick_check|full_check|prune|prune_max|unlock|repair_index|repair_packs|repair_snapshots|recover|dump|stats|raw|has_recent_snapshot]",
    )
    parser.add_argument(
        "--create-key",
        type=str,
        default=False,
        required=False,
        help="Create a new encryption key, requires a file path",
    )
    parser.add_argument(
        "--create-backup-scheduled-task",
        type=str,
        default=None,
        required=False,
        help="Create a scheduled backup task, specify an argument interval via interval=minutes, or hour=hour,minute=minute for a daily task",
    )
    parser.add_argument(
        "--create-housekeeping-scheduled-task",
        type=str,
        default=None,
        required=False,
        help="Create a scheduled housekeeping task, specify hour=hour,minute=minute for a daily task",
    )
    args = parser.parse_args()

    if args.log_file:
        log_file = args.log_file
    else:
        if os.name == "nt":
            log_file = os.path.join(CURRENT_DIR, "{}.log".format(__intname__))
        else:
            log_file = "/var/log/{}.log".format(__intname__)

    if args.json:
        _JSON = True
        logger = ofunctions.logger_utils.logger_get_logger(
            log_file, console=False, debug=_DEBUG
        )
    else:
        logger = ofunctions.logger_utils.logger_get_logger(log_file, debug=_DEBUG)

    if args.version:
        if _JSON:
            print(json.dumps({"result": True, "version": version_dict}))
        else:
            print(version_string)
        sys.exit(0)

    logger.info(version_string)
    if args.license:
        if _JSON:
            print(json.dumps({"result": True, "output": LICENSE_TEXT}))
        else:
            print(LICENSE_TEXT)
        sys.exit(0)

    if args.create_key:
        result = key_management.create_key_file(args.create_key)
        if result:
            sys.exit(0)
        else:
            sys.exit(1)

    if args.verbose:
        _VERBOSE = True

    if args.config_file:
        if not os.path.isfile(args.config_file):
            msg = f"Config file {args.config_file} cannot be read."
            json_error_logging(False, msg, "critical")
            sys.exit(70)
        config_file = Path(args.config_file)
    else:
        config_file = Path(f"{CURRENT_DIR}/npbackup.conf")
        if config_file.exists():
            logger.info(f"Loading default configuration file {config_file}")
        else:
            msg = "Cannot run without configuration file."
            json_error_logging(False, msg, "critical")
            sys.exit(70)

    try:
        full_config = npbackup.configuration.load_config(config_file)
    except EnvironmentError as exc:
        json_error_logging(False, exc, "critical")
        sys.exit(12)
    if not full_config:
        msg = "Cannot obtain repo config"
        json_error_logging(False, msg, "critical")
        sys.exit(71)

    if args.create_backup_scheduled_task or args.create_housekeeping_scheduled_task:
        try:
            if "interval" in args.create_scheduled_task:
                interval = args.create_scheduled_task.split("=")[1].strip()
                result = create_scheduled_task(
                    config_file, type="backup", interval_minutes=int(interval)
                )
            elif (
                "hour" in args.create_scheduled_task
                and "minute" in args.create_scheduled_task
            ):
                if args.create_backup_scheduled_task:
                    type = "backup"
                if args.create_housekeeping_scheduled_task:
                    type = "housekeeping"
                hours, minutes = args.create_scheduled_task.split(",")
                hour = hours.split("=")[1].strip()
                minute = minutes.split("=")[1].strip()
                result = create_scheduled_task(
                    config_file, type=type, hour=int(hour), minute=int(minute)
                )
                if not result:
                    msg = "Scheduled task creation failed"
                    json_error_logging(False, msg, "critical")
                    sys.exit(72)
                else:
                    msg = "Scheduled task created successfully"
                    json_error_logging(True, msg, "info")
                    sys.exit(0)
            else:
                msg = "Invalid interval or hour and minute given for scheduled task"
                json_error_logging(False, msg, "critical")
        except (TypeError, ValueError, IndexError) as exc:
            logger.debug("Trace:", exc_info=True)
            msg = f"Bogus data given for scheduled task: {exc}"
            json_error_logging(False, msg, "critical")
        sys.exit(72)

    if not args.group_operation:
        repo_name = None
        if not args.repo_name:
            repo_name = "default"
        repo_config, _ = npbackup.configuration.get_repo_config(full_config, repo_name)
        if not repo_config:
            msg = "Cannot find repo config"
            json_error_logging(False, msg, "critical")
            sys.exit(72)
    else:
        repo_config = None

    backend_binary = None
    if args.external_backend_binary:
        backend_binary = args.external_backend_binary
        if not os.path.isfile(backend_binary):
            msg = f"External backend binary {backend_binary} cannot be found."
            json_error_logging(False, msg, "critical")
            sys.exit(73)

    if args.show_config:
        # NPF-SEC-00009
        # Load an anonymous version of the repo config
        show_encrypted = False
        session_manager_password = os.environ.get("NPBACKUP_MANAGER_PASSWORD", None)
        if session_manager_password:
            manager_password = repo_config.g("manager_password")
            if manager_password:
                if manager_password == session_manager_password:
                    show_encrypted = True
                else:
                    # NPF-SEC
                    sleep(2)  # Sleep to avoid brute force attacks
                    logger.error("Wrong manager password")
                    sys.exit(74)
        repo_config = npbackup.configuration.get_anonymous_repo_config(
            repo_config, show_encrypted=show_encrypted
        )
        print(json.dumps(repo_config, indent=4))
        sys.exit(0)

    # Try to perform an auto upgrade if needed
    try:
        auto_upgrade = full_config["global_options"]["auto_upgrade"]
    except KeyError:
        auto_upgrade = True
    try:
        auto_upgrade_interval = full_config["global_options"]["auto_upgrade_interval"]
    except KeyError:
        auto_upgrade_interval = 10

    if (
        auto_upgrade and upgrade_runner.need_upgrade(auto_upgrade_interval)
    ) or args.auto_upgrade:
        if args.auto_upgrade:
            logger.info("Running user initiated auto upgrade")
        else:
            logger.info("Running program initiated auto upgrade")
        # Don't log upgrade check errors if we're in auto upgrade mode
        # since it will change the whole exit code of the program
        result = upgrade_runner.run_upgrade(full_config, ignore_errors=False if args.auto_upgrade else True)
        if result:
            sys.exit(0)
        elif args.auto_upgrade:
            logger.error("Auto upgrade failed")
            sys.exit(23)
        else:
            # Don't actually log errors for upgrades, since they could fail for various reasons
            # but change the exit code of the program
            # Prefer using supervision for upgrades
            logger.info("Interval initiated auto upgrade failed")

    # Prepare program run
    cli_args = {
        "repo_config": repo_config,
        "verbose": args.verbose,
        "dry_run": args.dry_run,
        "json_output": args.json,
        "backend_binary": backend_binary,
        "no_cache": args.no_cache,
        "operation": None,
        "op_args": {},
    }

    # On group operations, we also need to set op_args

    if args.stdin:
        cli_args["operation"] = "backup"
        cli_args["op_args"] = {
            "force": True,
            "read_from_stdin": True,
            "stdin_filename": args.stdin_filename if args.stdin_filename else None,
        }
    elif args.backup or args.group_operation == "backup":
        cli_args["operation"] = "backup"
        cli_args["op_args"] = {"force": args.force}
    elif args.restore or args.group_operation == "restore":
        if args.restore_includes:
            restore_includes = [
                include.strip() for include in args.restore_includes.split(",")
            ]
        else:
            restore_includes = None
        cli_args["operation"] = "restore"
        cli_args["op_args"] = {
            "snapshot": args.snapshot_id,
            "target": args.restore,
            "restore_includes": restore_includes,
        }
    elif args.snapshots or args.group_operation == "snapshots":
        cli_args["operation"] = "snapshots"
    elif args.list or args.group_operation == "list":
        cli_args["operation"] = "list"
        cli_args["op_args"] = {"subject": args.list}
    elif args.ls or args.group_operation == "ls":
        cli_args["operation"] = "ls"
        cli_args["op_args"] = {"snapshot": args.ls}
    elif args.find or args.group_operation == "find":
        cli_args["operation"] = "find"
        cli_args["op_args"] = {"path": args.find}
    elif args.forget:
        cli_args["operation"] = "forget"
        cli_args["op_args"] = {"snapshots": args.forget}
    elif args.policy or args.group_operation == "policy":
        cli_args["operation"] = "forget"
        cli_args["op_args"] = {"use_policy": True}
    elif args.housekeeping or args.group_operation == "housekeeping":
        cli_args["operation"] = "housekeeping"
        cli_args["op_args"] = {}
    elif args.quick_check or args.group_operation == "quick_check":
        cli_args["operation"] = "check"
        cli_args["op_args"] = {"read_data": False}
    elif args.full_check or args.group_operation == "full_check":
        cli_args["operation"] = "check"
        cli_args["op_args"] = {"read_data": True}
    elif args.prune or args.group_operation == "prune":
        cli_args["operation"] = "prune"
    elif args.prune_max or args.group_operation == "prune_max":
        cli_args["operation"] = "prune"
        cli_args["op_args"] = {"max": True}
    elif args.unlock or args.group_operation == "unlock":
        cli_args["operation"] = "unlock"
    elif args.repair_index or args.group_operation == "repair_index":
        cli_args["operation"] = "repair"
        cli_args["op_args"] = {"subject": "index"}
    elif args.repair_packs or args.group_operation == "repair_packs":
        cli_args["operation"] = "repair"
        cli_args["op_args"] = {
            "subject": "packs",
            "pack_ids": args.repair_packs,
        }
    elif args.repair_snapshots or args.group_operation == "repair_snapshots":
        cli_args["operation"] = "repair"
        cli_args["op_args"] = {"subject": "snapshots"}
    elif args.recover or args.group_operation == "recover":
        cli_args["operation"] = "recover"
    elif args.dump or args.group_operation == "dump":
        cli_args["operation"] = "dump"
        cli_args["op_args"] = {"path": args.dump}
    elif args.stats or args.group_operation == "stats":
        cli_args["operation"] = "stats"
        cli_args["op_args"] = {"subject": args.stats}
    elif args.raw or args.group_operation == "raw":
        cli_args["operation"] = "raw"
        cli_args["op_args"] = {"command": args.raw}
    elif args.has_recent_snapshot or args.group_operation == "has_recent_snapshot":
        cli_args["operation"] = "has_recent_snapshot"
    elif args.init:
        cli_args["operation"] = "init"

    # Group operation mode
    if args.group_operation and args.group_operation not in (
        "backup",
        "restore",
        "snapshots",
        "list",
        "ls",
        "find",
        "policy",
        "housekeeping",
        "quick_check",
        "full_check",
        "prune",
        "prune_max",
        "unlock",
        "repair_index",
        "repair_packs",
        "repair_snapshots",
        "recover",
        "dump",
        "stats",
        "raw",
        "has_recent_snapshot",
    ):
        logger.critical(
            f"Invalid group operation {args.group_operation}. Valid operations are [backup|restore|snapshots|list|ls|find|policy|housekeeping|quick_check|full_check|prune|prune_max|unlock|repair_index|repair_packs|repair_snapshots|recover|dump|stats|raw|has_recent_snapshot]"
        )
        sys.exit(74)
    repo_config_list = []
    repos = []
    if args.group_operation:
        if args.repo_group:
            groups = [group.strip() for group in args.repo_group.split(",")]
            for group in groups:
                repos = npbackup.configuration.get_repos_by_group(full_config, group)
                if repos is None or repos == []:
                    json_error_logging(
                        False, "No corresponding repo found", level="error"
                    )
                    sys.exit(74)
        elif args.repo_name:
            if args.repo_name == "__all__":
                repos = npbackup.configuration.get_repo_list(full_config)
            else:
                repos = [repo.strip() for repo in args.repo_name.split(",")]
        else:
            json_error_logging(
                False,
                "No repository names or groups have been provided for group operation. Please use --repo-group or --repo-name",
                level="critical",
            )
            sys.exit(74)

        for repo in repos:
            repo_config, _ = npbackup.configuration.get_repo_config(full_config, repo)
            if repo_config is None:
                json_error_logging(
                    False,
                    f"Repo {repo} does not exist in this configuration",
                    level="error",
                )
                repos.remove(repo)
            else:
                repo_config_list.append(repo_config)

        if repos is None or repos == []:
            json_error_logging(False, "No valid repos selected", level="error")
            sys.exit(74)
        logger.info(f"Running group operations for repos: {', '.join(repos)}")

        op = cli_args["operation"]
        cli_args["operation"] = "group_runner"
        cli_args["op_args"] = {
            "repo_config_list": repo_config_list,
            "operation": op,
            **cli_args["op_args"],
        }

    if cli_args["operation"]:
        entrypoint(**cli_args)
    else:
        json_error_logging(False, "No operation has been requested", level="warning")


def main():
    # Make sure we log execution time and error state at the end of the program
    atexit.register(
        execution_logs,
        datetime.now(timezone.utc),
    )
    # kill_childs normally would not be necessary, but let's just be foolproof here (kills restic subprocess in all cases)
    atexit.register(kill_childs, os.getpid(), grace_period=30)
    try:
        cli_interface()
        worst_error = logger.get_worst_logger_level()
        if worst_error >= logging.WARNING:
            sys.exit(worst_error)
        sys.exit()
    except KeyboardInterrupt as exc:
        json_error_logging(
            False, f"Program interrupted by keyboard: {exc}", level="error"
        )
        logger.info("Trace:", exc_info=True)
        # EXIT_CODE 200 = keyboard interrupt
        sys.exit(200)
    except Exception as exc:
        json_error_logging(False, f"Program interrupted by error: {exc}", level="error")
        logger.info("Trace:", exc_info=True)
        # EXIT_CODE 201 = Non handled exception
        sys.exit(201)


if __name__ == "__main__":
    main()
