#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_client.upgrader"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2025011501"


import os
import sys
import shutil
from logging import getLogger
import hashlib
import tempfile
import atexit
from datetime import datetime
from packaging import version
from ofunctions.platform import get_os, python_arch
from ofunctions.process import kill_childs
from ofunctions.requestor import Requestor
from ofunctions.random import random_string
from command_runner import deferred_command
from npbackup.path_helper import CURRENT_DIR, CURRENT_EXECUTABLE
from npbackup.core.nuitka_helper import IS_COMPILED
from npbackup.__version__ import __version__ as npbackup_version, IS_LEGACY

logger = getLogger()

UPGRADE_DEFER_TIME = 60  # Wait x seconds before we actually do the upgrade so current program could quit before being erased


# RAW ofunctions.checksum import
def sha256sum_data(data):
    # type: (bytes) -> str
    """
    Returns sha256sum of some data
    """
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()


def _check_new_version(
    upgrade_url: str, username: str, password: str, ignore_errors: bool = False
) -> bool:
    """
    Check if we have a newer version of npbackup
    """
    if upgrade_url:
        logger.info("Upgrade server is %s", upgrade_url)
    else:
        logger.debug("Upgrade server not set")
        return None
    requestor = Requestor(upgrade_url, username, password)
    requestor.app_name = "npbackup" + npbackup_version
    requestor.user_agent = __intname__
    requestor.ignore_errors = ignore_errors
    requestor.create_session(authenticated=True)
    server_ident = requestor.data_model()
    if server_ident is False:
        if ignore_errors:
            logger.info("Cannt reach upgrade server")
        else:
            logger.error("Cannot reach upgrade server")
        return None
    try:
        if not server_ident["app"] == "npbackup.upgrader":
            msg = "Current server is not a recognized NPBackup update server"
            if ignore_errors:
                logger.info(msg)
            else:
                logger.error(msg)
            return None
    except (KeyError, TypeError):
        msg = "Current server is not a NPBackup update server"
        if ignore_errors:
            logger.info(msg)
        else:
            logger.error(msg)
        return None

    result = requestor.data_model("current_version")
    if result is False:
        msg = "Upgrade server didn't respond properly. Is it well configured ?"
        if ignore_errors:
            logger.info(msg)
        else:
            logger.error(msg)
        return None
    try:
        online_version = result["version"]
    except KeyError:
        msg = "Upgrade server failed to provide proper version info"
        if ignore_errors:
            logger.info(msg)
        else:
            logger.error(msg)
        return None
    else:
        if online_version:
            if version.parse(online_version) > version.parse(npbackup_version):
                logger.info(
                    "Current version %s is older than online version %s",
                    npbackup_version,
                    online_version,
                )
                return True
            else:
                logger.info(
                    "Current version %s is up-to-date (online version %s)",
                    npbackup_version,
                    online_version,
                )
                return False


def auto_upgrader(
    upgrade_url: str,
    username: str,
    password: str,
    auto_upgrade_host_identity: str = None,
    group: str = None,
    ignore_errors: bool = False,
) -> bool:
    """
    Auto upgrade binary NPBackup distributions

    We must check that we run a compiled binary first
    We assume that we run a onefile nuitka binary
    """
    if not IS_COMPILED:
        logger.info(
            "Auto upgrade will only upgrade compiled verions. Please use 'pip install --upgrade npbackup' instead"
        )
        return False

    res = _check_new_version(
        upgrade_url, username, password, ignore_errors=ignore_errors
    )
    # Let's set a global environment variable which we can check later in metrics
    os.environ["NPBACKUP_UPGRADE_STATE"] = "0"
    if not res:
        if res is None:
            os.environ["NPBACKUP_UPGRADE_STATE"] = "1"
        return False
    requestor = Requestor(upgrade_url, username, password)
    requestor.app_name = "npbackup" + npbackup_version
    requestor.user_agent = __intname__
    requestor.create_session(authenticated=True)

    # We'll check python_arch instead of os_arch since we build 32 bit python executables for compat reasons
    arch = python_arch() if not IS_LEGACY else f"{python_arch()}-legacy"
    build_type = os.environ.get("NPBACKUP_BUILD_TYPE", None)
    if not build_type:
        logger.critical("Cannot determine build type for upgrade processs")
        return False
    target = "{}/{}/{}".format(get_os(), arch, build_type).lower()
    try:
        host_id = "{}/{}/{}".format(auto_upgrade_host_identity, npbackup_version, group)
        id_record = "{}/{}".format(target, host_id)
    except TypeError:
        id_record = target

    file_info = requestor.data_model("upgrades", id_record=id_record)
    if not file_info:
        logger.error("Server didn't provide a file description")
        return False
    try:
        sha256sum = file_info["sha256sum"]
    except (KeyError, TypeError):
        logger.error("Cannot get file description")
        logger.debug("Trace", exc_info=True)
        return False
    if sha256sum is None:
        logger.info("No upgrade file found has been found for me :/")
        return True

    file_data = requestor.requestor("download/" + id_record, raw=True)
    if not file_data:
        logger.error("Cannot get update file")
        return False

    if sha256sum_data(file_data) != sha256sum:
        logger.error("Invalid checksum, won't upgrade")
        return False

    downloaded_archive = os.path.join(tempfile.gettempdir(), file_info["filename"])
    with open(downloaded_archive, "wb") as fh:
        fh.write(file_data)
    logger.info("Upgrade file written to %s", downloaded_archive)

    upgrade_date = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_file = os.path.join(
        tempfile.gettempdir(), f"npbackup_upgrader.{upgrade_date}.log"
    )
    logger.info("Logging upgrade to %s", log_file)

    # We'll extract the downloaded archive to a temporary directory which should contain the base directory
    # eg /tmp/npbackup_upgrade_dist/npbackup-cli
    upgrade_dist = os.path.join(tempfile.gettempdir(), "npbackup_upgrade_dist")
    try:
        # File is a zip or tar.gz and should contain a single directory 'npbackup-cli' or 'npbackup-gui' with all files in it
        shutil.unpack_archive(downloaded_archive, upgrade_dist)
    except Exception as exc:
        logger.critical(f"Upgrade failed. Cannot uncompress downloaded dist: {exc}")
        return False
    try:
        first_directory = os.listdir(upgrade_dist)[0]
        upgrade_dist = os.path.join(
            tempfile.gettempdir(), "npbackup_upgrade_dist", first_directory
        )
        logger.debug(f"Upgrade dist dir: {upgrade_dist}")
    except Exception as exc:
        logger.critical(
            f"Upgrade failed. Upgrade directory does not contain a subdir: {exc}"
        )
        return False

    backup_dist = os.path.join(
        tempfile.gettempdir(), "npbackup_backup_dist_" + random_string(6)
    )

    # Inplace upgrade script, gets executed after main program has exited
    if os.name == "nt":
        cmd = (
            f"setlocal EnableDelayedExpansion & "
            f'echo "Launching upgrade" >> "{log_file}" 2>&1 && '
            f'echo "Moving earlier dist from {CURRENT_DIR} to {backup_dist}" >> "{log_file}" 2>&1 && '
            f'move /Y "{CURRENT_DIR}" "{backup_dist}" >> "{log_file}" 2>&1 && '
            f'echo "Moving upgraded dist from {upgrade_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1 && '
            f'move /Y "{upgrade_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1 && '
            f'echo "Copying optional configuration files from {backup_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1 && '
            # Just copy any possible *.conf file from any subdirectory
            rf'xcopy /S /Y "{backup_dist}\*conf" {CURRENT_DIR} > NUL 2>&1 & '
            f'echo "Loading new executable {CURRENT_EXECUTABLE} --version" >> "{log_file}" 2>&1 && '
            f'"{CURRENT_EXECUTABLE}" --version >> "{log_file}" 2>&1 & '
            f"IF !ERRORLEVEL! NEQ 0 ( "
            f'echo "New executable failed. Rolling back" >> "{log_file}" 2>&1 && '
            f'rd /S /Q "{CURRENT_DIR}" >> "{log_file}" 2>&1 && '
            f'move /Y "{backup_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1 '
            f") ELSE ( "
            f'echo "Upgrade successful" >> "{log_file}" 2>&1 && '
            f'rd /S /Q "{backup_dist}" >> "{log_file}" 2>&1 & '
            # f'rd /S /Q "{upgrade_dist}" >> "{log_file}" 2>&1 & ' Since we move this, we don't need to delete it
            f'del /F /S /Q "{downloaded_archive}" >> "{log_file}" 2>&1 & '
            f'echo "Running new version as planned:" >> "{log_file}" 2>&1 && '
            f'echo "{CURRENT_EXECUTABLE} {" ".join(sys.argv[1:])}" >> "{log_file}" 2>&1 && '
            f'"{CURRENT_EXECUTABLE}" {" ".join(sys.argv[1:])}'
            f")"
        )
    else:
        cmd = (
            f'echo "Launching upgrade" >> "{log_file}" 2>&1 && '
            f'echo "Moving earlier dist from {CURRENT_DIR} to {backup_dist}" >> "{log_file}" 2>&1 && '
            f'mv -f "{CURRENT_DIR}" "{backup_dist}" >> "{log_file}" 2>&1 && '
            f'echo "Moving upgraded dist from {upgrade_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1 && '
            f'mv -f "{upgrade_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1 && '
            f'echo "Copying optional configuration files from {backup_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1 && '
            f'find "{backup_dist}" -name "*.conf" -exec cp --parents {{}} "{CURRENT_DIR}" \; '
            f'echo "Adding executable bit to new executable" >> "{log_file}" 2>&1 && '
            f'chmod +x "{CURRENT_EXECUTABLE}" >> "{log_file}" 2>&1 && '
            f'echo "Loading new executable {CURRENT_EXECUTABLE} --version" >> "{log_file}" 2>&1 && '
            f'"{CURRENT_EXECUTABLE}" --version >> "{log_file}" 2>&1; '
            f"if [ $? -ne 0 ]; then "
            f'echo "New executable failed. Rolling back" >> "{log_file}" 2>&1 && '
            f'rm -f "{CURRENT_DIR}" >> "{log_file}" 2>&1 && '
            f'mv -f "{backup_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1; '
            f" else "
            f'echo "Upgrade successful" >> "{log_file}" 2>&1 && '
            f'rm -rf "{backup_dist}" >> "{log_file}" 2>&1 ; '
            f'rm -rf "{upgrade_dist}" >> "{log_file}" 2>&1 ; '
            f'rm -rf "{downloaded_archive}" >> "{log_file}" 2>&1 ; '
            f'echo "Running new version as planned:" >> "{log_file}" 2>&1 && '
            f'echo "{CURRENT_EXECUTABLE} {" ".join(sys.argv[1:])}" >> "{log_file}" 2>&1 && '
            f'"{CURRENT_EXECUTABLE}" {" ".join(sys.argv[1:])}; '
            f"fi"
        )

    # We still need to unregister previous kill_childs function se we can actually make the upgrade happen
    atexit.unregister(kill_childs)

    logger.info(
        "Launching upgrade. Current process will quit. Upgrade starts in %s seconds. Upgrade is done by OS and logged in %s",
        UPGRADE_DEFER_TIME,
        log_file,
    )
    logger.debug(cmd)
    deferred_command(cmd, defer_time=UPGRADE_DEFER_TIME)
    sys.exit(0)
