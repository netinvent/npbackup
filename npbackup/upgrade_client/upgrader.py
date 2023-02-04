#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_client.upgrader"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2023020201"


from typing import Optional
import os
from logging import getLogger
import hashlib
import tempfile
import atexit
from packaging import version
from ofunctions.platform import get_os, os_arch
from ofunctions.process import kill_childs
from command_runner import deferred_command
from npbackup.upgrade_client.requestor import Requestor
from npbackup.path_helper import CURRENT_DIR, CURRENT_EXECUTABLE
from npbackup.__main__ import __version__ as npbackup_version

logger = getLogger(__intname__)

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


def need_upgrade(upgrade_interval: int) -> bool:
    """
    Basic counter which allows an upgrade only every X times this is called so failed operations won't end in an endless upgrade loop

    We need to make to select a write counter file that is writable
    So we actually test a local file and a temp file (less secure for obvious reasons)
    We just have to make sure that once we can write to one file, we stick to it unless proven otherwise

    The for loop logic isn't straight simple, but allows file fallback
    """
    # file counter, local, home, or temp if not available
    counter_file = "npbackup.autoupgrade.log"

    def _write_count(file: str, count: int) -> bool:
        try:
            with open(file, "w") as fpw:
                fpw.write(str(count))
                return True
        except OSError:
            # We may not have write privileges, hence we need a backup plan
            return False

    def _get_count(file: str) -> Optional[int]:
        try:
            with open(file, "r") as fpr:
                count = int(fpr.read())
                return count
        except OSError:
            # We may not have read privileges
            None
        except ValueError:
            logger.error("Bogus upgrade counter in %s", file)
            return None

    try:
        upgrade_interval = int(upgrade_interval)
    except ValueError:
        logger.error("Bogus upgrade interval given. Will not upgrade")
        return False

    for file in [
        os.path.join(CURRENT_DIR, counter_file),
        os.path.join(tempfile.gettempdir(), counter_file),
    ]:
        if not os.path.isfile(file):
            if _write_count(file, 1):
                logger.debug("Initial upgrade counter written to %s", file)
            else:
                logger.debug("Cannot write to upgrade counter file %s", file)
                continue
        count = _get_count(file)
        # Make sure we can write to the file before we make any assumptions
        result = _write_count(file, count + 1)
        if result:
            if count >= upgrade_interval:
                # Reinitialize upgrade counter before we actually approve upgrades
                if _write_count(file, 1):
                    logger.info("Auto upgrade has decided upgrade check is required")
                    return True
            break
        else:
            logger.debug("Cannot write upgrade counter to %s", file)
            continue
    return False


def _check_new_version(upgrade_url: str, username: str, password: str) -> bool:
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
    requestor.create_session(authenticated=True)
    server_ident = requestor.data_model()
    if server_ident is False:
        logger.error("Cannot reach upgrade server")
        return None
    try:
        if not server_ident["app"] == "npbackup.upgrader":
            logger.error("Current server is not a recognized NPBackup update server")
            return None
    except (KeyError, TypeError):
        logger.error("Current server is not a NPBackup update server")
        return None

    result = requestor.data_model("current_version")
    try:
        online_version = result["version"]
    except KeyError:
        logger.error("Upgrade server failed to provide proper version info")
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
    installed_version: str = None,
    group: str = None,
) -> bool:
    """
    Auto upgrade binary NPBackup distributions

    We must check that we run a compiled binary first
    We assume that we run a onefile nuitka binary
    """
    is_nuitka = "__compiled__" in globals()
    if is_nuitka:
        logger.info(
            "Auto upgrade will only upgrade compiled verions. Please use 'pip install --upgrade npbackup' instead"
        )
        return False

    if not _check_new_version(upgrade_url, username, password):
        return False
    requestor = Requestor(upgrade_url, username, password)
    requestor.create_session(authenticated=True)
    platform_and_arch = "{}/{}".format(get_os(), os_arch()).lower()

    try:
        host_id = "{}/{}/{}".format(
            auto_upgrade_host_identity, installed_version, group
        )
        id_record = "{}/{}".format(platform_and_arch, host_id)
    except TypeError:
        id_record = platform_and_arch

    file_info = requestor.data_model("upgrades", id_record=id_record)
    try:
        sha256sum = file_info["sha256sum"]
    except (KeyError, TypeError):
        logger.error("Cannot get file description")
        return False

    file_data = requestor.requestor("download/" + id_record, raw=True)
    if not file_data:
        logger.error("Cannot get update file")
        return False

    if sha256sum_data(file_data) != sha256sum:
        logger.error("Invalid checksum, won't upgrade")
        return False

    downloaded_executable = os.path.join(tempfile.gettempdir(), file_info["filename"])
    with open(downloaded_executable, "wb") as fh:
        fh.write(file_data)
    logger.info("Upgrade file written to %s", downloaded_executable)

    log_file = os.path.join(tempfile.gettempdir(), file_info["filename"] + ".log")
    logger.info("Logging upgrade to %s", log_file)

    # Actual upgrade process
    backup_executable = CURRENT_EXECUTABLE + ".old"

    # Inplace upgrade script, gets executed after main program has exited
    if os.name == "nt":
        cmd = (
            f'echo "Launching upgrade" >> {log_file} 2>&1 && '
            f'del /F /Q "{backup_executable}" >> NUL 2>&1 && '
            f'echo "Renaming earlier executable from {CURRENT_EXECUTABLE} to {backup_executable}" >> {log_file} 2>&1 && '
            f'move /Y "{CURRENT_EXECUTABLE}" "{backup_executable}" >> {log_file} 2>&1 && '
            f'echo "Copying new executable from {downloaded_executable} to {CURRENT_EXECUTABLE}" >> {log_file} 2>&1 && '
            f'copy /Y "{downloaded_executable}" "{CURRENT_EXECUTABLE}" >> {log_file} 2>&1 && '
            f'del "{downloaded_executable}" >> {log_file} 2>&1 && '
            f'echo "Loading new executable" >> {log_file} 2>&1 && '
            f'"{CURRENT_EXECUTABLE}" --upgrade-conf >> {log_file} 2>&1 || '
            f'echo "New executable failed. Rolling back" >> {log_file} 2>&1 && '
            f'del /F /Q "{CURRENT_EXECUTABLE}" >> {log_file} 2>&1 && '
            f'move /Y "{backup_executable}" "{CURRENT_EXECUTABLE}" >> {log_file} 2>&1'
        )
    else:
        cmd = (
            f'echo "Launching upgrade" >> {log_file} 2>&1 && '
            f'rm -f "{backup_executable}" >> /dev/null 2>&1 && '
            f'echo "Renaming earlier executable from {CURRENT_EXECUTABLE} to {backup_executable}" >> {log_file} 2>&1 && '
            f'mv -f "{CURRENT_EXECUTABLE}" "{backup_executable}" >> {log_file} 2>&1 && '
            f'echo "Copying new executable from {downloaded_executable} to {CURRENT_EXECUTABLE}" >> {log_file} 2>&1 && '
            f'alias cp=cp && cp -f "{downloaded_executable}" "{CURRENT_EXECUTABLE}" >> {log_file} 2>&1 && '
            f'rm -f "{downloaded_executable}" >> {log_file} 2>&1 && '
            f'echo "Loading new executable" >> {log_file} 2>&1 && '
            f'"{CURRENT_EXECUTABLE}" --upgrade-conf >> {log_file} 2>&1 || '
            f'echo "New executable failed. Rolling back" >> {log_file} 2>&1 && '
            f'rm -f "{CURRENT_EXECUTABLE}" >> {log_file} 2>&1 && '
            f'mv -f "{backup_executable}" "{CURRENT_EXECUTABLE}" >> {log_file} 2>&1'
        )

    # We still need to unregister previous kill_childs function se we can actually make the upgrade happen
    atexit.unregister(kill_childs)

    logger.info(
        "Launching upgrade. Current process will quit. Upgrade starts in %s seconds. Upgrade is done by OS logged in %s",
        UPGRADE_DEFER_TIME,
        log_file,
    )
    logger.debug(cmd)
    deferred_command(cmd, defer_time=UPGRADE_DEFER_TIME)
    return True
