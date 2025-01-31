#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_client.upgrader"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2025012401"


import os
import sys
import shutil
from logging import getLogger
import hashlib
import tempfile
import atexit
from datetime import datetime
from packaging import version
from ofunctions.process import kill_childs
from ofunctions.requestor import Requestor
from ofunctions.random import random_string
from command_runner import deferred_command
from npbackup.path_helper import CURRENT_DIR, CURRENT_EXECUTABLE
from npbackup.__version__ import version_dict, IS_COMPILED
from npbackup.__debug__ import _NPBACKUP_ALLOW_AUTOUPGRADE_DEBUG
from npbackup.__env__ import UPGRADE_DEFER_TIME

logger = getLogger()


# RAW ofunctions.checksum import
def sha256sum_data(data):
    # type: (bytes) -> str
    """
    Returns sha256sum of some data
    """
    sha256 = hashlib.sha256()
    sha256.update(data)
    return sha256.hexdigest()


def _get_target_id(auto_upgrade_host_identity: str, group: str) -> str:
    """
    Get current target information string as

    {platform}/{arch}/{build_type}/{host_id}/{current_version}/{group}
    """
    target = "{}/{}/{}/{}".format(
        version_dict["os"],
        version_dict["arch"],
        version_dict["build_type"],
        version_dict["audience"],
    ).lower()
    try:
        host_id = "{}/{}/{}".format(
            auto_upgrade_host_identity, version_dict["version"], group
        )
        target = "{}/{}".format(target, host_id)
    except TypeError as exc:
        logger.debug(f"No other information to add to target: {exc}")
    return target


def _check_new_version(
    upgrade_url: str,
    username: str,
    password: str,
    ignore_errors: bool = False,
    auto_upgrade_host_identity: str = None,
    group: str = None,
) -> bool:
    """
    Check if we have a newer version of npbackup

    Returns True if upgrade is needed, False if no upgrade is needed
    Returns None if we cannot determine if an upgrade is needed
    """
    if upgrade_url:
        logger.info("Upgrade server is %s", upgrade_url)
    else:
        logger.debug("Upgrade server not set")
        return None
    try:
        requestor = Requestor(upgrade_url, username, password)
        requestor.app_name = "npbackup" + version_dict["version"]
        requestor.user_agent = __intname__
        requestor.ignore_errors = ignore_errors
        requestor.create_session(authenticated=True)
        server_ident = requestor.data_model()
        if server_ident is False:
            if ignore_errors:
                logger.info("Cannot reach upgrade server")
            else:
                logger.error("Cannot reach upgrade server")
            return None
    except Exception as exc:
        logger.error(f"Upgrade server response '{server_ident}' is bogus: {exc}")
        logger.debug("Trace", exc_info=True)
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

    target_id = _get_target_id(
        auto_upgrade_host_identity=auto_upgrade_host_identity, group=group
    )
    result = requestor.data_model("current_version", id_record=target_id)
    logger.info(f"Upgrade server response to current version: {result}")
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

    try:
        if online_version:
            if version.parse(online_version) > version.parse(version_dict["version"]):
                logger.info(
                    "Current version %s is older than online version %s",
                    version_dict["version"],
                    online_version,
                )
                return True
            logger.info(
                "Current version %s is up-to-date (online version %s)",
                version_dict["version"],
                online_version,
            )
            return False
        logger.error("Cannot determine online version")
        return None
    except Exception as exc:
        logger.error(
            f"Cannot determine if online version '{online_version}' is newer than current version {version_dict['verison']}: {exc}"
        )
        return None


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
        if _NPBACKUP_ALLOW_AUTOUPGRADE_DEBUG is not True:
            return False
        logger.info(
            "Debug mode allows auto upgrade on non-compiled versions. Be aware that this will probably mess up your installation"
        )

    res = _check_new_version(
        upgrade_url,
        username,
        password,
        ignore_errors=ignore_errors,
        auto_upgrade_host_identity=auto_upgrade_host_identity,
        group=group,
    )
    # Let's set a global environment variable which we can check later in metrics
    os.environ["NPBACKUP_UPGRADE_STATE"] = "0"
    if not res:
        if res is None:
            os.environ["NPBACKUP_UPGRADE_STATE"] = "1"
        return False
    requestor = Requestor(upgrade_url, username, password)
    requestor.app_name = "npbackup" + version_dict["version"]
    requestor.user_agent = __intname__
    requestor.create_session(authenticated=True)

    # This allows to get the current running target identification for upgrade server to return the right file
    target_id = _get_target_id(
        auto_upgrade_host_identity=auto_upgrade_host_identity, group=group
    )

    file_info = {}
    file_data = {}
    for file_type in ("script", "archive"):
        logger.info(f"Searching for {file_type} description for target {target_id}")
        file_info[file_type] = requestor.data_model(
            "info", id_record=f"{file_type}/{target_id}"
        )
        if not file_info[file_type]:
            if file_type == "script":
                logger.error(
                    "No upgrade script found. We'll try to use the inline script"
                )
            else:
                logger.error(f"Cannot get file description for {file_type}")
                return False
        try:
            logger.info(
                f"Found file description for {file_type} with hash {file_info[file_type]['sha256sum']}"
            )
        except (KeyError, TypeError):
            logger.debug("Trace", exc_info=True)
            if file_type == "script":
                logger.info(
                    "Could not check for upgrade script. We'll try to use the inline script"
                )
            else:
                logger.error(f"Cannot get file description for {file_type}")
                return False
        if file_info[file_type] and file_info[file_type]["sha256sum"] is None:
            logger.info(f"No {file_type} file found has been found for me :/")
            if file_type != "script":
                return True

    for file_type in ("script", "archive"):
        logger.info(f"Downloading {file_type} file for target {target_id}")
        file_info[file_type]["local_fs_path"] = None
        file_data[file_type] = requestor.requestor(
            f"download/{file_type}/{target_id}", raw=True
        )
        if not file_data[file_type]:
            if file_type != "script":
                logger.error("Cannot get update file")
                return False
        else:
            current_file_cksum = sha256sum_data(file_data[file_type])
            if current_file_cksum != file_info[file_type]["sha256sum"]:
                logger.error(
                    f"Expected checksum {file_info[file_type]['sha256sum']} does not match downloaded file checksum {current_file_cksum}. Won't run this"
                )
                return False

            local_fs_path = os.path.join(
                tempfile.gettempdir(), file_info[file_type]["filename"]
            )
            with open(local_fs_path, "wb") as fh:
                fh.write(file_data[file_type])
            logger.info(f"{file_type} file written to {local_fs_path}")
            file_info[file_type]["local_fs_path"] = local_fs_path

    upgrade_date = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_file = os.path.join(
        tempfile.gettempdir(), f"npbackup_upgrader.{upgrade_date}.log"
    )

    # We'll extract the downloaded archive to a temporary directory which should contain the base directory
    # eg /tmp/npbackup_upgrade_dist/npbackup-cli
    upgrade_dist = os.path.join(
        tempfile.gettempdir(), "npbackup_upgrade_dist" + random_string(6)
    )
    try:
        # File is a zip or tar.gz and should contain a single directory 'npbackup-cli' or 'npbackup-gui' with all files in it
        downloaded_archive = file_info["archive"]["local_fs_path"]
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

    logger.info(f"Logging upgrade to {log_file}")

    """
    Inplace upgrade script, gets executed after main program has exited if no upgrade script is provided

    So in this script we basically need to:
    - Move current dist to backup directory
    - Move downloaded dist to current directory
    - Copy any configuration files from backup to current
    
    If the above statement fails (current dist dir is locked by a process), we'll copy it and then overwrite it

    Check if new executable can load current config file
    Rollback if above statement fails
    """

    # Original arguments which were passed to this executable / script
    # Except --auto-upgrade of course
    filtered_args = []
    for arg in sys.argv[1:]:
        if arg != "--auto-upgrade":
            filtered_args.append(arg)
    original_args = " ".join(filtered_args)

    if file_info["script"]["local_fs_path"]:
        logger.info(
            f"Using remote upgrade script in {file_info['script']['local_fs_path']}"
        )
        try:
            # We must replace the script variables with actual values
            with open(file_info["script"]["local_fs_path"], "r") as fh:
                script_content = (
                    fh.read()
                    .replace("{CURRENT_DIR}", CURRENT_DIR)
                    .replace("{CURRENT_EXECUTABLE}", CURRENT_EXECUTABLE)
                    .replace("{upgrade_dist}", upgrade_dist)
                    .replace("{downloaded_archive}", downloaded_archive)
                    .replace("{backup_dist}", backup_dist)
                    .replace("{log_file}", log_file)
                    .replace("{original_args}", original_args)
                )
            with open(file_info["script"]["local_fs_path"], "w") as fh:
                fh.write(script_content)
        except OSError as exc:
            logger.error(f"Failed to replace variables in upgrade script: {exc}")
            return False

        if os.name == "nt":
            cmd = f'cmd /c "{file_info["script"]["local_fs_path"]}"'
        else:
            cmd = f'bash "{file_info["script"]["local_fs_path"]}"'
    else:
        logger.info("Using inline upgrade script")

        # By the way, why do we have an inline script ?
        # it's harder to maintain, and isn't as flexible as a remote script
        # but, some AV engines hate remote scripts, so we have to provide an inline script
        # or we'll get flagged as malware
        if os.name == "nt":
            cmd = (
                f'echo "Launching upgrade" >> "{log_file}" 2>&1 & '
                f'echo "Moving current dist from {CURRENT_DIR} to {backup_dist}" >> "{log_file}" 2>&1 & '
                f'move /Y "{CURRENT_DIR}" "{backup_dist}" >> "{log_file}" 2>&1 && ( '
                f'echo "Moving upgraded dist from {upgrade_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1 & '
                f'move /Y "{upgrade_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1 & '
                f'echo "Copying optional configuration files from {backup_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1 & '
                rf'xcopy /S /Y /I "{backup_dist}\*conf" {CURRENT_DIR} > NUL 2>&1 '
                f") || ( "
                f'echo "Moving current dist failed. Trying to copy it." >> "{log_file}" 2>&1 & '
                rf'xcopy /S /Y /I "{CURRENT_DIR}\*" "{backup_dist}\" >> "{log_file}" 2>&1 & '
                f'echo "Now trying to overwrite current dist with upgrade dist" >> "{log_file}" 2>&1 & '
                rf'xcopy /S /Y /I "{upgrade_dist}\*" "{CURRENT_DIR}" >> "{log_file}" 2>&1 '
                f") & "
                f'echo "Loading new executable {CURRENT_EXECUTABLE} --check-config {original_args}" >> "{log_file}" 2>&1 & '
                f'"{CURRENT_EXECUTABLE}" --check-config {original_args} >> "{log_file}" 2>&1 && ( '
                f'echo "Upgrade successful" >> "{log_file}" 2>&1 & '
                f'rd /S /Q "{backup_dist}" >> "{log_file}" 2>&1 & '
                f'del /F /S /Q "{downloaded_archive}" >> "{log_file}" 2>&1 '
                f") || ( "
                f'echo "New executable failed. Rolling back" >> "{log_file}" 2>&1 & '
                f'echo "Deleting current dist {CURRENT_DIR}" >> "{log_file}" 2>&1 & '
                f'rd /S /Q "{CURRENT_DIR}" >> "{log_file}" 2>&1 & '
                f'echo "Moving back files from {backup_dist} to original place in {CURRENT_DIR}" >> "{log_file}" 2>&1 & '
                f'move /Y "{backup_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1 || ( '
                f'echo "Moving back method failed. Overwriting back" >> "{log_file}" 2>&1 & '
                rf'copy /S /Y /I "{backup_dist}\*" "{CURRENT_DIR}" >> "{log_file}" 2>&1 '
                f") "
                f") & "
                f'echo "Running as initially planned:" >> "{log_file}" 2>&1 & '
                f'echo "{CURRENT_EXECUTABLE} {original_args}" >> "{log_file}" 2>&1 & '
                f'"{CURRENT_EXECUTABLE}" {original_args} & '
                f'echo "Upgrade script run finished" >> "{log_file}" 2>&1 '
            )
        else:
            cmd = (
                f'echo "Launching upgrade" >> "{log_file}" 2>&1 ;'
                f'echo "Moving current dist from {CURRENT_DIR} to {backup_dist}" >> "{log_file}" 2>&1 ;'
                f'mv -f "{CURRENT_DIR}" "{backup_dist}" >> "{log_file}" 2>&1 ;'
                f'echo "Moving upgraded dist from {upgrade_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1 ;'
                f'mv -f "{upgrade_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1 ;'
                f'echo "Copying optional configuration files from {backup_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1 ;'
                # In order to get find to give relative paths to cp, we need to cd into
                f'pushd "{backup_dist}" >> "{log_file}" 2>&1 && '
                rf'find ./ -name "*.conf" -exec cp --parents "{{}}" "{CURRENT_DIR}" \; && '
                f'popd >> "{log_file}" 2>&1 ;'
                f'echo "Adding executable bit to new executable" >> "{log_file}" 2>&1 ;'
                f'pushd "{backup_dist}" >> "{log_file}" 2>&1 && popd >> "{log_file}" 2>&1 ;'
                f'chmod +x "{CURRENT_EXECUTABLE}" >> "{log_file}" 2>&1 ;'
                f'echo "Loading new executable {CURRENT_EXECUTABLE} --run-as-cli --check-config {original_args}" >> "{log_file}" 2>&1 ;'
                f'"{CURRENT_EXECUTABLE}" --run-as-cli --check-config {original_args} >> "{log_file}" 2>&1 ;'
                f"if [ $? -ne 0 ]; then "
                f'    echo "New executable failed. Rolling back" >> "{log_file}" 2>&1 ;'
                f'    mv -f "{CURRENT_DIR}" "{backup_dist}.failed_upgrade">> "{log_file}" 2>&1 ;'
                f'    mv -f "{backup_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1 ;'
                f"else "
                f'    echo "Upgrade successful" >> "{log_file}" 2>&1 ;'
                f'    rm -rf "{backup_dist}" >> "{log_file}" 2>&1 ;'
                f'    rm -rf "{upgrade_dist}" >> "{log_file}" 2>&1 ;'
                f'    rm -rf "{downloaded_archive}" >> "{log_file}" 2>&1 ;'
                f"fi ;"
                # Since directory has changed, we need to chdir so current dir is updated in case it's CURRENT_DIR
                f'pushd /tmp >> "{log_file}" 2>&1 && popd >> "{log_file}" 2>&1 ;'
                f'echo "Running as initially planned:" >> "{log_file}" 2>&1 ;'
                f'echo "{CURRENT_EXECUTABLE} {original_args}" >> "{log_file}" 2>&1 ;'
                f'"{CURRENT_EXECUTABLE}" {original_args} ;'
                f'echo "Upgrade script run finished" >> "{log_file}" 2>&1 '
            )

    # We still need to unregister previous kill_childs function se we can actually make the upgrade happen
    atexit.unregister(kill_childs)

    logger.info(
        "Launching upgrade. Current process will quit. Upgrade starts in %s seconds. Upgrade is done by OS and logged in %s",
        UPGRADE_DEFER_TIME,
        log_file,
    )
    if _NPBACKUP_ALLOW_AUTOUPGRADE_DEBUG:
        logger.info("So we only show the command, but we won't actually run it in debug mode. Please run it manually")
        logger.info(cmd)
    else:
        logger.debug(cmd)
        deferred_command(cmd, defer_time=UPGRADE_DEFER_TIME)
    sys.exit(0)
