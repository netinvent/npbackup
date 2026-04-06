#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.constants"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026031301"


from npbackup.core.i18n_helper import _t

combo_boxes = {
    "repo_opts.compression": {
        "auto": _t("config_gui.auto"),
        "max": _t("config_gui.max"),
        "off": _t("config_gui.off"),
    },
    "backup_opts.source_type": {
        "folder_list": _t("config_gui.folder_list"),
        "files_from": _t("config_gui.files_from"),
        "files_from_verbatim": _t("config_gui.files_from_verbatim"),
        "files_from_raw": _t("config_gui.files_from_raw"),
        "stdin_from_command": _t("config_gui.stdin_from_command"),
    },
    "backup_opts.priority": {
        "low": _t("config_gui.low"),
        "normal": _t("config_gui.normal"),
        "high": _t("config_gui.high"),
    },
    "permissions": {
        "backup": _t("config_gui.backup_perms"),
        "restore": _t("config_gui.restore_perms"),
        "restore_only": _t("config_gui.restore_only_perms"),
        "full": _t("config_gui.full_perms"),
    },
    "backends": {
        "local": _t("config_gui.backend_local"),
        "sftp": _t("config_gui.backend_sftp"),
        # "rclone": _t("config_gui.backend_rclone"),
        "b2": _t("config_gui.backend_b2"),
        "s3": _t("config_gui.backend_s3"),
        "azure": _t("config_gui.backend_azure"),
        "gs": _t("config_gui.backend_gs"),
        "rest": _t("config_gui.backend_rest"),
    },
    "backup_interval_unit": {
        "minutes": _t("generic.minutes"),
        "hours": _t("generic.hours"),
        "days": _t("generic.days"),
        "weeks": _t("generic.weeks"),
        "months": _t("generic.months"),
    },
}

byte_units = ["B", "KB", "KiB", "MB", "MiB", "GB", "GiB", "TB", "TiB", "PB", "PiB"]
