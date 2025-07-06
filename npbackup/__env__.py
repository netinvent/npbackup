#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.__env__"
__author__ = "Orsiris de Jong"
__site__ = "https://www.netperfect.fr/npbackup"
__description__ = "NetPerfect Backup Client"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"


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
