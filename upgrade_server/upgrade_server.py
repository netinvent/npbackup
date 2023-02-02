#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_server.upgrade_server"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "202303102"
__version__ = "1.1.0"


DEVEL = True

import sys
import os
from upgrade_server import configuration
from ofunctions.logger_utils import logger_get_logger


config_dict = configuration.load_config()
try:
    listen = config_dict["http_server"]["listen"]
except KeyError:
    listen = None
try:
    port = config_dict["http_server"]["port"]
except KeyError:
    listen = None

if DEVEL:
    import uvicorn as server

    server_args = {
        "workers": 1,
        "log_level": "debug",
        "reload": True,
        "host": listen if listen else "0.0.0.0",
        "port": port if port else 8080,
    }
else:
    import gunicorn as server

    server_args = {
        "workers": 8,
        "reload": False,
        "host": listen if listen else "0.0.0.0",
        "port": port if port else 8080,
    }

logger = logger_get_logger()

if __name__ == "__main__":
    try:

        server.run("upgrade_server.api:app", **server_args)
    except KeyboardInterrupt as exc:
        logger.error("Program interrupted by keyoard: {}".format(exc))
        sys.exit(200)
    except Exception as exc:
        logger.error("Program interrupted by error: {}".format(exc))
        logger.critical("Trace:", exc_info=True)
        sys.exit(201)
