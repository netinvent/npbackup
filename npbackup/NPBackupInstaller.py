#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.installer"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023011101"
__version__ = "1.1.6"


import sys
import os
import shutil
from distutils.dir_util import copy_tree
from command_runner import command_runner
import ofunctions.logger_utils
from npbackup.customization import PROGRAM_NAME, PROGRAM_DIRECTORY
from npbackup.path_helper import BASEDIR, CURRENT_DIR


_DEBUG = os.environ.get("_DEBUG", False)
LOG_FILE = os.path.join(CURRENT_DIR, __intname__ + ".log")


INSTALL_TO = "{}{}{}".format(
    os.environ.get("PROGRAMFILES", None), os.sep, PROGRAM_DIRECTORY
)
NPBACKUP_EXECUTABLE = "npbackup.exe" if os.name == "nt" else "npbackup"
NPBACKUP_INSTALLED_EXECUTABLE = os.path.join(INSTALL_TO, NPBACKUP_EXECUTABLE)
FILES_TO_COPY = [NPBACKUP_EXECUTABLE]
DIRS_TO_COPY = ["excludes"]
CONF_FILE = "npbackup.conf.dist"

logger = ofunctions.logger_utils.logger_get_logger(LOG_FILE, debug=_DEBUG)


def install(config_file=None):
    logger.info("Running {} {}".format(__intname__, __version__))
    # We need to stop / disable current npbackup tasks so we don't get race conditions
    exit_code, output = command_runner(
        'schtasks /END /TN "{}"'.format(PROGRAM_NAME),
        valid_exit_codes=[0, 1],
        windows_no_window=True,
        encoding="cp437",
    )
    if exit_code != 0:
        logger.error(
            "Could not terminate currant scheduled task {}:\{}".format(
                PROGRAM_NAME, output
            )
        )
    # Create destination directory
    if not os.path.isdir(INSTALL_TO):
        try:
            os.makedirs(INSTALL_TO)
        except OSError as exc:
            logger.error("Could not create directory {}: {}".format(INSTALL_TO, exc))
            return False

    # Copy files
    for file in FILES_TO_COPY:
        source = os.path.join(BASEDIR, file)
        destination = os.path.join(INSTALL_TO, file)
        try:
            logger.info("Copying {} to {}".format(source, destination))
            shutil.copy2(source, destination)
        except OSError as exc:
            logger.error(
                "Could not copy file {} to {}: {}".format(source, destination, exc)
            )
            return False

    # Copy dirs
    for dir in DIRS_TO_COPY:
        source = os.path.join(BASEDIR, dir)
        destination = os.path.join(INSTALL_TO, dir)
        try:
            logger.info("Copying {} to {}".format(source, destination))
            copy_tree(source, destination)
        except OSError as exc:
            logger.error(
                "Could not copy directory {} to {}: {}".format(source, destination, exc)
            )
            return False

    # Copy distribution config file if none given, never overwrite existing conf file
    if not config_file:
        # Execute config file modification if needed
        source = os.path.join(BASEDIR, CONF_FILE)
        destination = os.path.join(INSTALL_TO, CONF_FILE.rstrip(".dist"))
        config_file = destination
        if os.path.isfile(destination):
            logger.info("Keeping in place configuration file.")
            destination = os.path.join(INSTALL_TO, CONF_FILE)
        try:
            logger.info("Copying {} to {}".format(source, destination))
            shutil.copy2(source, destination)
        except OSError as exc:
            logger.error(
                "Could not copy file {} to {}: {}".format(source, destination, exc)
            )
            return False

        logger.info(
            "Running configuration from {}".format(NPBACKUP_INSTALLED_EXECUTABLE)
        )
        exit_code, output = command_runner(
            '"{}" --config-gui --config-file "{}"'.format(
                NPBACKUP_INSTALLED_EXECUTABLE, config_file
            ),
            shell=False,
            timeout=3600,
        )
        if exit_code != 0:
            logger.error("Could not run config gui:\n{}".format(output))
            return False

    else:
        destination = os.path.join(INSTALL_TO, os.path.basename(config_file))
        try:
            logger.info("Copying {} to {}".format(source, destination))
            shutil.copy2(config_file, destination)
        except OSError as exc:
            logger.error(
                "Could not copy file {} to {}: {}".format(source, destination, exc)
            )
            return False

    # Create task
    exit_code, output = command_runner(
        '"{}" --create-scheduled-task 15'.format(
            NPBACKUP_INSTALLED_EXECUTABLE, shell=False, timeout=300
        )
    )
    if exit_code != 0:
        logger.info("Could not create scheduled task:\n".format(output))
    else:
        logger.info("Created scheduled task.")

    logger.info("Installation succesful.")
    return True


if __name__ == "__main__":
    try:
        result = install(sys.argv[1:])
        if not result:
            sys.exit(12)
        sys.exit(0)
    except KeyboardInterrupt as exc:
        logger.error("Program interrupted by keyboard. {}".format(exc))
        logger.info("Trace:", exc_info=True)
        sys.exit(200)
    except Exception as exc:
        logger.error("Program interrupted by error. {}".format(exc))
        logger.info("Trace", exc_info=True)
        sys.exit(201)
