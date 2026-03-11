#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.common_gui"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2026 NetInvent"
__license__ = "GPL-3.0-only"

"""
Note that all layouts are functions so we don't modify global objects between calls
This is important because some elements are generated dynamically and we don't want to have duplicate keys in the layout
"""

import os
from datetime import datetime
from logging import getLogger
import FreeSimpleGUI as sg
import textwrap
from npbackup.core.i18n_helper import _t
from npbackup.gui.ttk_theme import TITLE_FONT, SUBTITLE_FONT
from resources.customization import NON_INHERITED_ICON, INHERITED_ICON

try:
    from resources.customization import MONITORING_ENABLE
except ImportError:
    # Unless specified, enable all monitoring options
    MONITORING_ENABLE = ["prometheus", "zabbix", "email", "healthchecksio", "webhooks"]

from npbackup.gui.constants import combo_boxes

logger = getLogger()


MONITORING_HELP = """\
When setting up monitoring, you can use the following variables as placeholder for your url endpoints and instance names:

- ${HOSTNAME}: Current hostname as provided by OS
- ${BACKUP_JOB}: Backup job name, as defined in your config, or "default" if not defined
- ${REPO_NAME}: Repository name as defined in your config, or "default" if not defined
- ${REPO_GROUP}: Repository group as defined in your config, or "default_group" if not defined
- ${MACHINE_ID}: Machine ID as defined in your config
- ${MACHINE_GROUP}: Machine group as defined in your config
- ${RANDOM}[n]: Random char between 0 and n-1

By default, we'll set MACHINE_ID to ${HOSTNAME}_${RANDOM}[4] in order to avoid multiple machine IDs with the same name such as "PC1" or "LAPTOP"

MACHINE_GROUP can be used as a way to group backups from the same customer, provider, or else together.
"""

datepicker_options = {
    "format": "%Y-%m-%d",
    "default_date_m_d_y": (
        datetime.now().month,
        datetime.now().day,
        datetime.now().year,
    ),
    "close_when_date_chosen": True,
}


def add_source_menu():
    return [
        "-ADD-SOURCE-",
        [
            _t("generic.add_files"),
            _t("generic.add_folder"),
            # WIP: features not yet implemented, hide for now
            #    _t("generic.add_system"),
            #   _t("generic.add_hyper_v"),
            #    _t("generic.add_kvm"),
            _t("generic.add_manually"),
        ],
    ]


def email_recipient_row(index: int):
    """
    A "Row" in this case is a Button with an "X", an Input element and a Text element showing the current counter
    :param index: The number to use in the tuple for each element
    :type:           int
    :return:         List
    """
    row = [
        sg.pin(
            sg.Col(
                [
                    [
                        sg.In(size=(40, 1), k=("-EMAIL-RECIPIENT-ADDR-", index)),
                        sg.Checkbox(
                            _t("generic.success").capitalize(),
                            default=True,
                            k=("-EMAIL-ON-BACKUP-SUCCESS-", index),
                            size=(5, 1),
                            pad=(1, 0),
                        ),
                        sg.Checkbox(
                            _t("generic.failure").capitalize(),
                            default=True,
                            k=("-EMAIL-ON-BACKUP-FAILURE-", index),
                            size=(5, 1),
                            pad=(1, 0),
                        ),
                        sg.Checkbox(
                            _t("generic.success").capitalize(),
                            default=False,
                            k=("-EMAIL-ON-OPERATIONS-SUCCESS-", index),
                            size=(5, 1),
                            pad=(1, 0),
                        ),
                        sg.Checkbox(
                            _t("generic.failure").capitalize(),
                            default=True,
                            k=("-EMAIL-ON-OPERATIONS-FAILURE-", index),
                            size=(5, 1),
                            pad=(1, 0),
                        ),
                        sg.B(
                            "❌",
                            border_width=0,
                            button_color=(
                                sg.theme_text_color(),
                                sg.theme_background_color(),
                            ),
                            k=("-REMOVE-EMAIL-RECIPIENT-", index),
                            tooltip=_t("generic.delete"),
                        ),
                    ],
                ],
                k=("-EMAIL-RECIPIENT-", index),
            )
        )
    ]
    return row


def generic_row(
    name: str,
    index: int,
    size=(30, 1),
    optional_prefix_object=None,
    inherited: bool = False,
):
    """
    A "Row" in this case is a Button with an "X", an Input element and a Text element showing the current counter
    :param index: The number to use in the tuple for each element
    :type:           int
    :return:         List
    """
    row = [
        sg.pin(
            sg.Col(
                [
                    [
                        optional_prefix_object if optional_prefix_object else "",
                        sg.Image(
                            NON_INHERITED_ICON if not inherited else INHERITED_ICON,
                            key=(f"inherited-{name}-", index),
                            tooltip=_t("config_gui.group_inherited"),
                            pad=1,
                        ),
                        sg.In(size=size, k=(f"-{name}-", index)),
                        sg.B(
                            "❌",
                            border_width=0,
                            button_color=(
                                sg.theme_text_color(),
                                sg.theme_background_color(),
                            ),
                            k=(f"-REMOVE-ROW-{name}-", index),
                            tooltip=_t("generic.delete"),
                        ),
                    ],
                ],
                k=(f"-GENERIC-{name}-COLUMN-", index),
            )
        )
    ]
    return row


def per_object_monitoring_identity_col():
    return [
        [sg.Text(_t("config_gui.available_variables"))],
        [
            sg.Text(_t("config_gui.job_name"), size=(40, 1)),
            sg.Image(
                NON_INHERITED_ICON,
                key="inherited.monitoring.backup_job",
                tooltip=_t("config_gui.group_inherited"),
                pad=1,
            ),
            sg.Input(key="monitoring.backup_job", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.instance_name"), size=(40, 1)),
            sg.Image(
                NON_INHERITED_ICON,
                key="inherited.monitoring.instance",
                tooltip=_t("config_gui.group_inherited"),
                pad=1,
            ),
            sg.Input(key="monitoring.instance", size=(50, 1)),
        ],
        [
            sg.Text(_t("generic.group"), size=(40, 1)),
            sg.Image(
                NON_INHERITED_ICON,
                key="inherited.monitoring.group",
                tooltip=_t("config_gui.group_inherited"),
                pad=1,
            ),
            sg.Input(key="monitoring.group", size=(50, 1)),
        ],
        [
            sg.HorizontalSeparator(),
        ],
        [
            sg.Text(
                _t("config_gui.additional_labels"), font=SUBTITLE_FONT, size=(40, 1)
            ),
        ],
        [
            sg.Push(),
            sg.Button(
                _t("generic.remove_selected"),
                key="--REMOVE-MONITORING-LABEL--",
                size=(18, 1),
            ),
            sg.Button(
                _t("generic.add") + " ▾", key="--ADD-MONITORING-LABEL--", size=(18, 1)
            ),
        ],
        [
            sg.Tree(
                sg.TreeData(),
                key="monitoring.additional_labels",
                headings=[_t("generic.value")],
                col0_heading=_t("config_gui.additional_labels"),
                col0_width=1,
                auto_size_columns=True,
                justification="L",
                num_rows=4,
                expand_x=True,
                expand_y=True,
            )
        ],
    ]


def global_prometheus_col():
    return [
        [
            sg.Checkbox(
                _t("config_gui.prometheus_enable"),
                key="global_prometheus.enabled",
                enable_events=True,
                size=(41, 1),
            ),
        ],
        [
            sg.Col(
                [
                    [
                        sg.Text(_t("config_gui.metrics_destination"), size=(40, 1)),
                        sg.Input(key="global_prometheus.destination", size=(50, 1)),
                    ],
                    [
                        sg.Text("", size=(40, 1)),
                        sg.Text(
                            "Ex: /var/lib/node_exporter/textfile_collector/npbackup.prom",
                            size=(50, 1),
                        ),
                    ],
                    [
                        sg.Text("", size=(40, 1)),
                        sg.Text(
                            "Ex: https://push.domain.tld/metrics/job/${BACKUP_JOB}",
                            size=(50, 1),
                        ),
                    ],
                    [
                        sg.Text(_t("config_gui.no_cert_verify"), size=(40, 1)),
                        sg.Checkbox(
                            "", key="global_prometheus.no_cert_verify", size=(41, 1)
                        ),
                    ],
                    [
                        sg.Text(_t("config_gui.metrics_username"), size=(40, 1)),
                        sg.Input(key="global_prometheus.http_username", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("config_gui.metrics_password"), size=(40, 1)),
                        sg.Input(key="global_prometheus.http_password", size=(50, 1)),
                    ],
                ],
                visible=False,
                key="-GLOBAL-PROMETHEUS-SETTINGS-",
                expand_x=True,
                expand_y=True,
                pad=0,
            ),
        ],
    ]


def global_email_col():
    return [
        [
            sg.Checkbox(
                _t("config_gui.email_enable"),
                key="global_email.enabled",
                enable_events=True,
                size=(41, 1),
            ),
        ],
        [
            sg.Col(
                [
                    [
                        sg.Text(_t("config_gui.smtp_server"), size=(40, 1)),
                        sg.Input(key="global_email.smtp_server", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("config_gui.smtp_port"), size=(40, 1)),
                        sg.Input(key="global_email.smtp_port", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("config_gui.smtp_security"), size=(40, 1)),
                        sg.Combo(
                            ["None", "ssl", "tls"],
                            key="global_email.smtp_security",
                            size=(50, 1),
                        ),
                    ],
                    [
                        sg.Text(_t("config_gui.smtp_username"), size=(40, 1)),
                        sg.Input(key="global_email.smtp_username", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("config_gui.smtp_password"), size=(40, 1)),
                        sg.Input(key="global_email.smtp_password", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("config_gui.email_sender"), size=(40, 1)),
                        sg.Input(key="global_email.sender", size=(50, 1)),
                    ],
                    [
                        sg.Col(
                            [
                                [
                                    sg.Text(
                                        _t("config_gui.email_recipients"), size=(40, 1)
                                    ),
                                    sg.Text(_t("config_gui.backup"), size=(16, 1)),
                                    sg.Text(_t("config_gui.operations"), size=(16, 1)),
                                ],
                            ]
                        )
                    ],
                    [
                        sg.Col(
                            [],
                            key="-EMAIL-RECIPIENT-COLUMN-",
                            size=(None, 100),
                            expand_x=True,
                            expand_y=False,
                            scrollable=True,
                            vertical_scroll_only=True,
                        )
                    ],
                    [
                        sg.Col(
                            [
                                [
                                    sg.Button(
                                        _t("config_gui.add_recipient"),
                                        key="-ADD-EMAIL-RECIPIENT-",
                                        size=(24, 1),
                                    ),
                                    sg.Button(
                                        _t("config_gui.test_email"),
                                        key="-TEST-EMAIL-",
                                        size=(24, 1),
                                    ),
                                ]
                            ],
                            pad=0,
                            justification="C",
                        ),
                    ],
                ],
                visible=False,
                key="-GLOBAL-EMAIL-SETTINGS-",
                expand_x=True,
                expand_y=True,
                pad=0,
            ),
        ],
    ]


def global_zabbix_col():
    return [
        [
            sg.Checkbox(
                _t("config_gui.zabbix_enable"),
                key="global_zabbix.enabled",
                enable_events=True,
                size=(41, 1),
            ),
        ],
        [
            sg.Col(
                [
                    [
                        sg.Text(_t("config_gui.zabbix_server"), size=(40, 1)),
                        sg.Input(key="global_zabbix.server", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("config_gui.zabbix_port"), size=(40, 1)),
                        sg.Input(key="global_zabbix.port", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("config_gui.psk_identity"), size=(40, 1)),
                        sg.Input(key="global_zabbix.psk_identity", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("config_gui.psk"), size=(40, 1)),
                        sg.Input(key="global_zabbix.psk", size=(50, 1)),
                    ],
                ],
                visible=False,
                key="-GLOBAL-ZABBIX-SETTINGS-",
                expand_x=True,
                expand_y=True,
                pad=0,
            )
        ],
    ]


def global_healthchecksio_col():
    return [
        [
            sg.Checkbox(
                _t("config_gui.healthchecksio_enable"),
                key="global_healthchecksio.enabled",
                enable_events=True,
                size=(41, 1),
            ),
        ],
        [
            sg.Col(
                [
                    [
                        sg.Text(_t("config_gui.healthchecksio_url"), size=(40, 1)),
                        sg.Input(key="global_healthchecksio.url", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("config_gui.no_cert_verify"), size=(40, 1)),
                        sg.Checkbox(
                            "", key="global_healthchecksio.no_cert_verify", size=(41, 1)
                        ),
                    ],
                    [
                        sg.Text(_t("generic.username"), size=(40, 1)),
                        sg.Input(key="global_healthchecksio.username", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("generic.password"), size=(40, 1)),
                        sg.Input(key="global_healthchecksio.password", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("generic.timeout"), size=(40, 1)),
                        sg.Input(key="global_healthchecksio.timeout", size=(50, 1)),
                    ],
                ],
                visible=False,
                key="-GLOBAL-HEALTHCHECKSIO-SETTINGS-",
                expand_x=True,
                expand_y=True,
                pad=0,
            )
        ],
    ]


def global_webhooks_col():
    return [
        [
            sg.Checkbox(
                _t("config_gui.webhooks_enable"),
                key="global_webhooks.enabled",
                enable_events=True,
                size=(41, 1),
            ),
        ],
        [
            sg.Col(
                [
                    [
                        sg.Text(_t("config_gui.webhooks_url"), size=(40, 1)),
                        sg.Input(key="global_webhooks.destination", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("config_gui.no_cert_verify"), size=(40, 1)),
                        sg.Checkbox(
                            "", key="global_webhooks.no_cert_verify", size=(41, 1)
                        ),
                    ],
                    [
                        sg.Text(_t("config_gui.webhooks_method"), size=(40, 1)),
                        sg.Combo(
                            ["POST", "GET"],
                            default_value="POST",
                            key="global_webhooks.method",
                            size=(50, 1),
                        ),
                    ],
                    [
                        sg.Text(_t("generic.username"), size=(40, 1)),
                        sg.Input(key="global_webhooks.username", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("generic.password"), size=(40, 1)),
                        sg.Input(key="global_webhooks.password", size=(50, 1)),
                    ],
                    [
                        sg.Text(_t("config_gui.webhook_spretty_json"), size=(40, 1)),
                        sg.Input(key="global_webhooks.pretty_json", size=(50, 1)),
                    ],
                ],
                visible=False,
                key="-GLOBAL-WEBHOOKS-SETTINGS-",
                expand_x=True,
                expand_y=True,
                pad=0,
            )
        ],
    ]


def global_monitoring_identity_col():
    return [
        [
            sg.Text(
                _t("wizard_gui.monitoring_identity_description"),
                size=(60, 1),
                font=SUBTITLE_FONT,
                expand_x=True,
            ),
        ],
        [
            sg.Text(_t("config_gui.machine_id"), size=(40, 1)),
            sg.Input(key="identity.machine_id", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.machine_group"), size=(40, 1)),
            sg.Input(key="identity.machine_group", size=(50, 1)),
        ],
        [
            sg.Text(
                _t("generic.help"),
                size=(50, 1),
                font=SUBTITLE_FONT,
                expand_x=True,
                justification="center",
            ),
        ],
        [
            sg.Multiline(
                MONITORING_HELP,
                size=(40, 1),
                expand_x=True,
                expand_y=True,
                disabled=True,
            ),
        ],
    ]


def retention_col():

    return [
        [
            sg.Combo(
                values=[],
                key="-RETENTION-POLICIES-",
                enable_events=True,
            )
        ],
        [
            sg.Push(),
            sg.Button(
                _t("generic.advanced_settings"),
                key="-RETENTION-POLICY-ADVANCED-",
            ),
        ],
        [
            sg.Col(
                [
                    [
                        sg.Col(
                            [
                                [
                                    sg.Text(_t("config_gui.keep"), size=(10, 1)),
                                ]
                            ],
                            vertical_alignment="top",
                        ),
                        sg.Col(
                            [
                                [
                                    sg.Image(
                                        NON_INHERITED_ICON,
                                        key="inherited.repo_opts.retention_policy.last",
                                        tooltip=_t("config_gui.group_inherited"),
                                        pad=1,
                                    ),
                                    sg.Input(
                                        key="repo_opts.retention_policy.last",
                                        size=(3, 1),
                                    ),
                                    sg.Text(_t("config_gui.last"), size=(12, 1)),
                                ],
                                [
                                    sg.Image(
                                        NON_INHERITED_ICON,
                                        key="inherited.repo_opts.retention_policy.hourly",
                                        tooltip=_t("config_gui.group_inherited"),
                                        pad=1,
                                    ),
                                    sg.Input(
                                        key="repo_opts.retention_policy.hourly",
                                        size=(3, 1),
                                    ),
                                    sg.Text(_t("config_gui.hourly"), size=(12, 1)),
                                ],
                            ],
                        ),
                        sg.Col(
                            [
                                [
                                    sg.Image(
                                        NON_INHERITED_ICON,
                                        key="inherited.repo_opts.retention_policy.daily",
                                        tooltip=_t("config_gui.group_inherited"),
                                        pad=1,
                                    ),
                                    sg.Input(
                                        key="repo_opts.retention_policy.daily",
                                        size=(3, 1),
                                    ),
                                    sg.Text(_t("config_gui.daily"), size=(12, 1)),
                                ],
                                [
                                    sg.Image(
                                        NON_INHERITED_ICON,
                                        key="inherited.repo_opts.retention_policy.weekly",
                                        tooltip=_t("config_gui.group_inherited"),
                                        pad=1,
                                    ),
                                    sg.Input(
                                        key="repo_opts.retention_policy.weekly",
                                        size=(3, 1),
                                    ),
                                    sg.Text(_t("config_gui.weekly"), size=(12, 1)),
                                ],
                            ]
                        ),
                        sg.Col(
                            [
                                [
                                    sg.Image(
                                        NON_INHERITED_ICON,
                                        key="inherited.repo_opts.retention_policy.monthly",
                                        tooltip=_t("config_gui.group_inherited"),
                                        pad=1,
                                    ),
                                    sg.Input(
                                        key="repo_opts.retention_policy.monthly",
                                        size=(3, 1),
                                    ),
                                    sg.Text(_t("config_gui.monthly"), size=(12, 1)),
                                ],
                                [
                                    sg.Image(
                                        NON_INHERITED_ICON,
                                        key="inherited.repo_opts.retention_policy.yearly",
                                        tooltip=_t("config_gui.group_inherited"),
                                        pad=1,
                                    ),
                                    sg.Input(
                                        key="repo_opts.retention_policy.yearly",
                                        size=(3, 1),
                                    ),
                                    sg.Text(_t("config_gui.yearly"), size=(12, 1)),
                                ],
                            ]
                        ),
                    ],
                    [
                        sg.Image(
                            NON_INHERITED_ICON,
                            key="inherited.repo_opts.retention_policy.keep_within",
                            tooltip=_t("config_gui.group_inherited"),
                            pad=1,
                        ),
                        sg.Checkbox(
                            _t("config_gui.keep_within"),
                            key="repo_opts.retention_policy.keep_within",
                            size=(100, 1),
                        ),
                    ],
                    [sg.Text(_t("config_gui.policiy_group_by"))],
                    [
                        sg.Image(
                            NON_INHERITED_ICON,
                            key="inherited.repo_opts.retention_policy.group_by_host",
                            tooltip=_t("config_gui.group_inherited"),
                            pad=1,
                        ),
                        sg.Checkbox(
                            _t("config_gui.group_by_host"),
                            key="repo_opts.retention_policy.group_by_host",
                        ),
                        sg.Image(
                            NON_INHERITED_ICON,
                            key="inherited.repo_opts.retention_policy.group_by_paths",
                            tooltip=_t("config_gui.group_inherited"),
                            pad=1,
                        ),
                        sg.Checkbox(
                            _t("config_gui.group_by_paths"),
                            key="repo_opts.retention_policy.group_by_paths",
                        ),
                        sg.Image(
                            NON_INHERITED_ICON,
                            key="inherited.repo_opts.retention_policy.group_by_tags",
                            tooltip=_t("config_gui.group_inherited"),
                            pad=1,
                        ),
                        sg.Checkbox(
                            _t("config_gui.group_by_tags"),
                            key="repo_opts.retention_policy.group_by_tags",
                        ),
                    ],
                    [sg.Text(_t("config_gui.policiy_group_by_explanation"))],
                    [sg.HorizontalSeparator()],
                    [
                        sg.Col(
                            [
                                [
                                    sg.Text(_t("config_gui.keep_tags"), expand_x=True),
                                    sg.Push(),
                                    sg.Button(
                                        _t("generic.add") + " ▾",
                                        key="-ADD-RETENTION-KEEP-TAG-",
                                        size=(14, 1),
                                    ),
                                ],
                            ],
                            pad=0,
                            expand_x=True,
                        ),
                        sg.Col(
                            [
                                [
                                    sg.Text(
                                        _t("config_gui.apply_on_tags"), expand_x=True
                                    ),
                                    sg.Push(),
                                    sg.Button(
                                        _t("generic.add") + " ▾",
                                        key="-ADD-RETENTION-APPLY-ON-TAG-",
                                        size=(14, 1),
                                    ),
                                ],
                            ],
                            pad=0,
                            expand_x=True,
                        ),
                    ],
                    [
                        sg.Col(
                            [[]],
                            key="-RETENTION-KEEP-TAG-COLUMN-",
                            size=(None, 100),
                            expand_x=True,
                            expand_y=False,
                            scrollable=True,
                            vertical_scroll_only=True,
                        ),
                        sg.Col(
                            [[]],
                            key="-RETENTION-APPLY-ON-TAG-COLUMN-",
                            size=(None, 100),
                            expand_x=True,
                            expand_y=False,
                            scrollable=True,
                            vertical_scroll_only=True,
                        ),
                    ],
                    [
                        sg.HorizontalSeparator(),
                    ],
                    [
                        sg.Image(
                            NON_INHERITED_ICON,
                            key="inherited.repo_opts.retention_policy.ntp_server",
                            tooltip=_t("config_gui.group_inherited"),
                            pad=1,
                        ),
                        sg.Text(_t("config_gui.optional_ntp_server_uri"), size=(40, 1)),
                        sg.Input(
                            key="repo_opts.retention_policy.ntp_server", size=(50, 1)
                        ),
                    ],
                ],
                visible=False,
                key="-RETENTION-POLICY-ADVANCED-COLUMN-",
            )
        ],
    ]


def scheduling_col(is_wizard: bool = False, task_types: list = None):
    object_selector = [
        [
            sg.Column(
                [
                    [
                        sg.Text(
                            _t("config_gui.select_task_scope"),
                            font=SUBTITLE_FONT,
                            expand_x=True,
                        ),
                    ],
                    [
                        sg.Text(_t("config_gui.select_object")),
                        sg.Combo(
                            [],
                            # We need to specify {object_type}: {object_name} as default value
                            # since we use the standard get_object_from_combo() fn
                            default_value="Repo: default", 
                            key="-OBJECT-SELECT-TASKS-",
                            enable_events=True,
                        ),
                        sg.Text(_t("config_gui.task_type")),
                        sg.Combo(
                            values=task_types if task_types else [],
                            default_value=task_types[0] if task_types else "backup",
                            key="-TASK-TYPE-",
                            size=(15, 1),
                        ),
                    ],
                ],
                visible=not is_wizard,
            )
        ]
    ]

    first_backup_scheduling = [
        [
            sg.Text(
                _t("wizard_gui.first_backup_date"), font=SUBTITLE_FONT, expand_x=True
            )
        ],
        [
            sg.Text(
                _t("generic.date").capitalize(),
                size=(8, 1),
            ),
            sg.CalendarButton(
                "📅",
                target="-FIRST-BACKUP-DATE-",
                key="CALENDAR",
                pad=(0, 0),
                font=TITLE_FONT,
                **datepicker_options,
            ),
            sg.Input(
                "YYYY/MM/DD",
                key="-FIRST-BACKUP-DATE-",
                size=(14, 1),
                background_color=sg.theme_background_color(),
            ),
            sg.Text(
                _t("generic.time").capitalize(),
                size=(8, 1),
            ),
            sg.Combo(
                values=[h for h in range(0, 24)],
                default_value=0,
                key="-FIRST-BACKUP-HOUR-",
                size=(3, 1),
            ),
            sg.Text(":"),
            sg.Combo(
                values=[m for m in range(0, 60)],
                default_value=0,
                key="-FIRST-BACKUP-MINUTE-",
                size=(3, 1),
            ),
        ],
    ]

    schedule = [
        [sg.Text(_t("wizard_gui.backup_frequency"), font=SUBTITLE_FONT, expand_x=True)],
        [
            sg.Text(
                _t("generic.every").capitalize(),
                size=(10, 1),
            ),
            sg.Input(
                "1",
                key="-BACKUP-FREQUENCY-",
                size=(5, 1),
                background_color=sg.theme_background_color(),
            ),
            sg.Combo(
                values=list(combo_boxes["backup_frequency_unit"].values()),
                default_value=combo_boxes["backup_frequency_unit"]["days"],
                key="-BACKUP-FREQUENCY-UNIT-",
                size=(15, 1),
            ),
        ],
        [
            sg.Text(
                _t("wizard_gui.only_if_no_recent_backup_exists"),
                size=(60, 1),
            ),
            sg.Input("", key="repo_opts.minimum_backup_age", size=(4, 1)),
            sg.Text(_t("generic.minutes")),
        ],
        [
            sg.Text(_t("config_gui.random_delay_before_backup"), size=(60, 1)),
            sg.Input("", key="repo_opts.random_delay_before_backup", size=(4, 1)),
            sg.Text(_t("generic.minutes")),
        ],
        [sg.Text(_t("wizard_gui.authorized_days"), size=(80, 2), font=SUBTITLE_FONT)],
        [
            sg.Checkbox(
                _t("generic.monday").capitalize(), key="-DAY-monday-", default=True
            ),
            sg.Checkbox(
                _t("generic.tuesday").capitalize(), key="-DAY-tuesday-", default=True
            ),
            sg.Checkbox(
                _t("generic.wednesday").capitalize(),
                key="-DAY-wednesday-",
                default=True,
            ),
            sg.Checkbox(
                _t("generic.thursday").capitalize(), key="-DAY-thursday-", default=True
            ),
            sg.Checkbox(
                _t("generic.friday").capitalize(), key="-DAY-friday-", default=True
            ),
        ],
        [
            sg.Checkbox(
                _t("generic.saturday").capitalize(), key="-DAY-saturday-", default=True
            ),
            sg.Checkbox(
                _t("generic.sunday").capitalize(), key="-DAY-sunday-", default=True
            ),
        ],
    ]

    # Conststruct object depending on environment
    schedule_col = object_selector
    if not is_wizard:
        schedule_col = schedule_col + [[sg.HorizontalSeparator()]]
    if os.name == "nt":
        schedule_col = (
            schedule_col + first_backup_scheduling + [[sg.HorizontalSeparator()]]
        )
    schedule_col += schedule
    return schedule_col


def backup_tags_col():
    return [
        [
            sg.Col(
                [
                    [
                        sg.Text(
                            textwrap.fill(
                                _t("config_gui.backup_tags_explanation"), width=60
                            )
                        ),
                    ],
                ]
            )
        ],
        [
            sg.Push(),
            sg.Button(
                _t("generic.add") + " ▾",
                key="-ADD-BACKUP-TAG-",
                size=(8, 1),
                font=SUBTITLE_FONT,
            ),
        ],
        [
            sg.Col(
                [[]],
                key="-BACKUP-TAG-COLUMN-",
                size=(None, 100),
                expand_x=True,
                expand_y=False,
                scrollable=True,
                vertical_scroll_only=True,
            )
        ],
    ]


def global_monitoring_tab_group():
    return [
        [
            tab
            for index, tab in {
                "prometheus": sg.Tab(
                    _t("config_gui.prometheus"),
                    global_prometheus_col(),
                    k="prometheus_tab",
                ),
                "zabbix": sg.Tab(
                    _t("config_gui.zabbix"),
                    global_zabbix_col(),
                    k="zabbix_tab",
                ),
                "email": sg.Tab(
                    _t("config_gui.email"),
                    global_email_col(),
                    k="email_tab",
                ),
                "healthchecksio": sg.Tab(
                    _t("config_gui.healthchecksio"),
                    global_healthchecksio_col(),
                    k="healthchecksio_tab",
                ),
                "webhooks": sg.Tab(
                    _t("config_gui.webhooks"),
                    global_webhooks_col(),
                    k="webhooks_tab",
                ),
            }.items()
            if index in MONITORING_ENABLE
        ]
    ]
