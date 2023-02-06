#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.upgrade_server.configuration"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023020601"


import os
from ruamel.yaml import YAML
from logging import getLogger


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
config_file = os.path.join(ROOT_DIR, "upgrade_server.conf")

logger = getLogger(__intname__)


def load_config(config_file: str = config_file):
    """
    Using ruamel.yaml preserves comments and order of yaml files
    """
    logger.debug("Using configuration file {}".format(config_file))
    try:
        with open(config_file, "r", encoding="utf-8") as file_handle:
            # RoundTrip loader is default and preserves comments and ordering
            yaml = YAML(typ="rt")
            config_dict = yaml.load(file_handle)
            return config_dict
    except FileNotFoundError:
        logger.error("config file %s not found", config_file)
        return None
    except TypeError:
        logger.error("No config file given")
        return None


def save_config(config_file, config_dict):
    with open(config_file, "w", encoding="utf-8") as file_handle:
        yaml = YAML(typ="rt")
        yaml.dump(config_dict, file_handle)
