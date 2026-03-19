#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.__env__"
__author__ = "Orsiris de Jong"
__site__ = "https://www.netperfect.fr/npbackup"
__description__ = "NetPerfect Backup Client"
__copyright__ = "Copyright (C) 2023-2026 NetInvent"


import os
import sys
from base64 import b64encode, b64decode
from binascii import Error as binascii_Error
import pickle


##################
# CONSTANTS FILE #
##################

# Interval for timeout in queue reads
# The lower, the faster we get backend results, but at the expense of cpu
CHECK_INTERVAL = 0.005

# The lower the snappier the GUI, but also more cpu hungry
# Should not be lower than CHECK_INTERVAL
GUI_CHECK_INTERVAL = 0.005


# Interval on which we log a status message stating we're still alive
# This is useful for long running operations
HEARTBEAT_INTERVAL = 3600

# Arbitrary timeout for init / init checks.
# If init takes more than a minute, we really have a problem in our backend
FAST_COMMANDS_TIMEOUT = 180

# # Wait x seconds before we actually do the upgrade so current program could quit before being erased
UPGRADE_DEFER_TIME = 60

# Maximum allowed time offset in seconds to allow policy operations to run
MAX_ALLOWED_NTP_OFFSET = 600.0

if "BUILD_TYPE" not in globals():
    BUILD_TYPE = "UnknownBuildType"


def set_build_type(build_type: str) -> None:
    global BUILD_TYPE
    BUILD_TYPE = build_type


# Allowed server ids for upgrade
ALLOWED_UPGRADE_SERVER_IDS = ("npbackup.upgrader", "npbackup.deployment_server")

# Replacement string for sensitive data
HIDDEN_BY_NPBACKUP = "_[o_O]_hidden_by_npbackup"

# Maximum number of characters for details content in emails
MAX_EMAIL_DETAIL_LENGTH = 1000

# How much storage size history do we keep for heuristics
STORAGE_HISTORY_KEEP = 30

# How many storage size points do we use for heuristic evaluation
STORAGE_HISTORY_EVALUATION_HISTORY_COUNT = 5

# How many storage modified file points do we use for heuristic ransomware evaluation
MODIFIED_FILES_HISTORY_EVALUATION_HISTORY_COUNT = 30

######################################################################
# ALLOWED ENVIRONMENT VARIABLES WE'LL PORT TO UAC ELEVATED PROCESSES #
######################################################################

def create_env_argument():
        try:
            env = {
                "_DEBUG":  os.environ.get("_NPBACKUP_AUDIENCE", None),
                "_NPBACKUP_AUDIENCE": os.environ.get("_NPBACKUP_AUDIENCE", None)
            }

            env_bytes = b64encode(pickle.dumps(env)).decode()
            sys.argv.append("--NPBACKUP_ENV")
            sys.argv.append(env_bytes)
        except Exception as exc:
            print(f"Error creating environment argument for elevated process: {exc}")

def restore_env_from_argument():
    """
    Since we cannot keep environment variables when elevating a process on windows,
    we need a way to port (only some for security reasons) environment variables to the elevated process. 
    """
    if sys.argv and "--NPBACKUP_ENV" in sys.argv:
        env = sys.argv[sys.argv.index("--NPBACKUP_ENV") + 1]
        sys.argv.pop(sys.argv.index("--NPBACKUP_ENV"))
        sys.argv.pop(sys.argv.index(env))
        try:
            env_bytes = b64decode(env)
        except (TypeError, binascii_Error):
            print("Invalid environment variables passed to elevated process. Ignoring.")
        else:
            try:
                env = pickle.loads(env_bytes)
            # May happen on unpickled data when pickling failed on encryption and fallback was used
            # ModuleNotFoundError may happen if we unpickle a class which was not loaded
            except (pickle.UnpicklingError, TypeError, OverflowError, KeyError, ModuleNotFoundError):
                print("Invalid environment variables objects to elevated process. Ignoring.")
            else:
                for key, value in env.items():
                    if key is not None and value is not None:
                        os.environ[key] = value