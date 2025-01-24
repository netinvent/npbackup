#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.common"
__author__ = "Orsiris de Jong"
__site__ = "https://www.netperfect.fr/npbackup"
__description__ = "NetPerfect Backup Client"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023121801"


from datetime import datetime, timezone
from logging import getLogger
import ofunctions.logger_utils


logger = getLogger()


def execution_logs(start_time: datetime) -> None:
    """
    Try to know if logger.warning or worse has been called
    logger._cache contains a dict of values like {10: boolean, 20: boolean, 30: boolean, 40: boolean, 50: boolean}
    where
    10 = debug, 20 = info, 30 = warning, 40 = error, 50 = critical
    so "if 30 in logger._cache" checks if warning has been triggered
    ATTENTION: logger._cache does only contain cache of current main, not modules, deprecated in favor of
    ofunctions.logger_utils.ContextFilterWorstLevel

    ATTENTION: For ofunctions.logger_utils.ContextFilterWorstLevel will only check current logger instance
    So using logger = getLogger("anotherinstance") will create a separate instance from the one we can inspect
    Makes sense ;)
    """

    end_time = datetime.now(timezone.utc)

    logger_worst_level = 0
    for flt in logger.filters:
        if isinstance(flt, ofunctions.logger_utils.ContextFilterWorstLevel):
            logger_worst_level = flt.worst_level

    log_level_reached = "success"
    try:
        if logger_worst_level >= 50:
            log_level_reached = "critical"
        elif logger_worst_level >= 40:
            log_level_reached = "errors"
        elif logger_worst_level >= 30:
            log_level_reached = "warnings"
    except AttributeError as exc:
        logger.error(f"Cannot get worst log level reached: {exc}")
    logger.info(
        f"ExecTime = {end_time - start_time}, finished, state is: {log_level_reached}."
    )
    # using sys.exit(code) in a atexit function will swallow the exitcode and render 0
    # Using sys.exit(logger.get_worst_logger_level()) is the way to go, when using ofunctions.logger_utils >= 2.4.1
