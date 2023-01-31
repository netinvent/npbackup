#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_client.upgrader"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2021-2023 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2023012801"


import os
from logging import getLogger
import hashlib
import tempfile
from ofunctions.platform import get_os, os_arch
from command_runner import deferred_command
from npbackup.upgrade_client.requestor import Requestor
from npbackup.path_helper import CURRENT_DIR, CURRENT_EXECUTABLE

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


def auto_upgrade(upgrade_url: str, username: str, password: str):
    """
    Auto upgrade binary NPBackup distributions

    We must check that we run a compiled binary first
    We assume that we run a onefile nuitka binary
    """
    is_nuitka = "__compiled__" in globals()
    if not is_nuitka:
        logger.debug("No upgrade necessary")
        return True
    logger.info("Upgrade server is %s", upgrade_url)
    requestor = Requestor(upgrade_url, username, password)
    requestor.create_session(authenticated=True)
    server_ident = requestor.data_model()
    if server_ident is False:
        logger.error("Cannot reach upgrade server")
        return False
    try:
        if not server_ident['app'] == 'npbackup.upgrader':
            logger.error("Current server is not a recognized NPBackup update server")
            return False
    except (KeyError, TypeError):
        logger.error("Current server is not a NPBackup update server")
        return False

    platform_and_arch = '{}/{}'.format(get_os(), os_arch()).lower()

    file_info = requestor.data_model('upgrades', id_record=platform_and_arch)
    try:
        sha256sum = file_info['sha256sum']
    except (KeyError, TypeError):
        logger.error("Cannot get file description")
        return False
    
    file_data = requestor.requestor('upgrades/' + platform_and_arch + '/data', raw=True)
    if not file_data:

    #if not isinstance(file_data, bytes): # WIP
        logger.error("Cannot get update file")
        return False

    if sha256sum_data(file_data) != sha256sum:
        logger.error("Invalid checksum, won't upgrade")
        return False
    
    executable = os.path.join(tempfile.gettempdir(), file_info['filename'])
    with open(executable, 'wb') as fh:
        fh.write(file_data)
    logger.info("Upgrade file written to %s", executable)

    log_file = os.path.join(tempfile.gettempdir(), file_info['filename'] + '.log')

    # Actual upgrade process
    new_executable = os.path.join(CURRENT_DIR, os.path.basename(CURRENT_EXECUTABLE))
    cmd = "del \"{}\"; move \"{}\" \"{}\"; del \"{}\" > {}".format(CURRENT_EXECUTABLE, executable, new_executable, executable, log_file)
    logger.info("Launching upgrade. Current process will quit. Upgrade starts in %s seconds. Upgrade is done by OS logged in %s", UPGRADE_DEFER_TIME, log_file)
    logger.debug(cmd)
    deferred_command(cmd, defer_time=UPGRADE_DEFER_TIME)
    return True

