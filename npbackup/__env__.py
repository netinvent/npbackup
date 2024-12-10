#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.__env__"
__author__ = "Orsiris de Jong"
__site__ = "https://www.netperfect.fr/npbackup"
__description__ = "NetPerfect Backup Client"
__copyright__ = "Copyright (C) 2023-2024 NetInvent"


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
