from datetime import datetime
from logging import getLogger
import ofunctions.logger_utils


logger = getLogger()


EXIT_CODE = 0


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
    global EXIT_CODE

    end_time = datetime.utcnow()

    logger_worst_level = 0
    for flt in logger.filters:
        if isinstance(flt, ofunctions.logger_utils.ContextFilterWorstLevel):
            logger_worst_level = flt.worst_level

    log_level_reached = "success"
    EXIT_CODE = logger_worst_level
    try:
        if logger_worst_level >= 40:
            log_level_reached = "errors"
        elif logger_worst_level >= 30:
            log_level_reached = "warnings"
    except AttributeError as exc:
        logger.error("Cannot get worst log level reached: {}".format(exc))
    logger.info(
        "ExecTime = {}, finished, state is: {}.".format(
            end_time - start_time, log_level_reached
        )
    )
    # using sys.exit(code) in a atexit function will swallow the exitcode and render 0