#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__appname__ = "npbackup_upgrade_server"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024091701"
__version__ = "3.0.0"


import sys
import os
import multiprocessing
from argparse import ArgumentParser
from upgrade_server import configuration
from ofunctions.logger_utils import logger_get_logger
import upgrade_server.api
from upgrade_server.__debug__ import _DEBUG


if __name__ == "__main__":
    _DEV = os.environ.get("_DEV", False)

    parser = ArgumentParser(
        prog="{} {} - {}".format(__appname__, __copyright__, __license__),
        description="""NPBackup Upgrade server""",
    )

    parser.add_argument(
        "--dev", action="store_true", help="Run with uvicorn in devel environment"
    )

    parser.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        type=str,
        default=None,
        required=False,
        help="Path to upgrade_server.conf file",
    )

    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        required=False,
        help="Optional path for logfile, overrides config file values",
    )

    args = parser.parse_args()
    if args.dev:
        _DEV = True

    if args.log_file:
        log_file = args.log_file
    else:
        if os.name == "nt":
            log_file = os.path.join(f"{__appname__}.log")
        else:
            log_file = f"/var/log/{__appname__}.log"
    logger = logger_get_logger(log_file, debug=_DEBUG)

    if args.config_file:
        config_dict = configuration.load_config(args.config_file)
    else:
        config_dict = configuration.load_config()

    try:
        if not args.log_file:
            logger = logger_get_logger(
                config_dict["http_server"]["log_file"], debug=_DEBUG
            )
    except (AttributeError, KeyError, IndexError, TypeError):
        pass

    try:
        listen = config_dict["http_server"]["listen"]
    except (TypeError, KeyError):
        listen = None
    try:
        port = config_dict["http_server"]["port"]
    except (TypeError, KeyError):
        port = None

    logger = logger_get_logger()
    # Cannot run gunicorn on Windows
    if _DEV or os.name == "nt":
        logger.info("Running dev version")
        import uvicorn

        server_args = {
            "workers": 1,
            "log_level": "debug",
            "reload": True,
            "host": listen if listen else "0.0.0.0",
            "port": port if port else 8080,
        }
    else:
        import gunicorn.app.base

        class StandaloneApplication(gunicorn.app.base.BaseApplication):
            """
            This class supersedes gunicorn's class in order to load config before launching the app
            """

            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                config = {
                    key: value
                    for key, value in self.options.items()
                    if key in self.cfg.settings and value is not None
                }
                for key, value in config.items():
                    self.cfg.set(key.lower(), value)

            def load(self):
                return self.application

        server_args = {
            "workers": (multiprocessing.cpu_count() * 2) + 1,
            "bind": f"{listen}:{port}" if listen else "0.0.0.0:8080",
            "worker_class": "uvicorn.workers.UvicornWorker",
        }

    try:
        if _DEV or os.name == "nt":
            uvicorn.run("upgrade_server.api:app", **server_args)
        else:
            StandaloneApplication(upgrade_server.api.app, server_args).run()
    except KeyboardInterrupt as exc:
        logger.error("Program interrupted by keyoard: {}".format(exc))
        sys.exit(200)
    except Exception as exc:
        logger.error("Program interrupted by error: {}".format(exc))
        logger.critical("Trace:", exc_info=True)
        sys.exit(201)
