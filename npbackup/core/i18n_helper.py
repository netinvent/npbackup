#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.core.i18n_helper"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2023032101"


import os
from logging import getLogger
from locale import getdefaultlocale
import i18n
from npbackup.path_helper import BASEDIR


logger = getLogger(__intname__)


TRANSLATIONS_DIR = os.path.join(BASEDIR, "translations")

# getdefaultlocale returns a tuple like ('fr-FR', 'cp1251')
# Let's only use the fr part, so other french speaking countries also have french translation
_locale = os.environ.get("NPBACKUP_LOCALE", getdefaultlocale()[0])
try:
    _locale, _ = _locale.split("_")
except (ValueError, AttributeError):
    try:
        _locale, _ = _locale.split("-")
    except (ValueError, AttributeError):
        pass

try:
    i18n.load_path.append(TRANSLATIONS_DIR)
except OSError as exc:
    logger.error("Cannot load translations: {}".format(exc))
i18n.set("locale", _locale)
i18n.set("fallback", "en")


def _t(*args, **kwargs):
    try:
        return i18n.t(*args, **kwargs)
    except OSError as exc:
        logger.error("Translation not found in {}: {}".format(TRANSLATIONS_DIR, exc))
