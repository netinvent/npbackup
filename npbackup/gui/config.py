#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.config"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023012601"


from logging import getLogger
import PySimpleGUI as sg
import npbackup.configuration as configuration
from npbackup.core.i18n_helper import _t

logger = getLogger(__intname__)


def config_gui(config_dict: dict, config_file: str):
    logger.info("Launching configuration GUI")

    # Don't let PySimpleGUI handle key errros since we might have new keys in config file
    sg.set_options(
        suppress_raise_key_errors=True,
        suppress_error_popups=True,
        suppress_key_guessing=True,
    )

    ENCRYPTED_DATA_PLACEHOLDER = "<{}>".format(_t("config_gui.encrypted_data"))

    def update_gui(window, config_dict, unencrypted=False):
        for section in config_dict.keys():
            if config_dict[section] is None:
                config_dict[section] = {}
            for entry in config_dict[section].keys():
                try:
                    value = config_dict[section][entry]
                    if not unencrypted:
                        if entry in [
                            "http_username",
                            "http_password",
                            "repository",
                            "password",
                        ]:
                            try:
                                if config_dict[section][entry] is None:
                                    continue
                                if not config_dict[section][entry].startswith(
                                    configuration.ID_STRING
                                ):
                                    value = ENCRYPTED_DATA_PLACEHOLDER
                            except (KeyError, TypeError):
                                pass

                    if isinstance(value, list):
                        value = "\n".join(value)
                    # window keys are section---entry
                    key = "{}---{}".format(section, entry)
                    window[key].Update(value)
                except KeyError:
                    logger.error("No GUI equivalent for {}.".format(entry))
                except TypeError as exc:
                    logger.error("{} for {}.".format(exc, entry))

    def update_config_dict(values, config_dict):
        for key, value in values.items():
            if value == ENCRYPTED_DATA_PLACEHOLDER:
                continue
            section, entry = key.split("---")
            # check whether we need to split into list
            if not isinstance(value, bool):
                result = value.split("\n")
                if len(result) > 1:
                    value = result
                else:
                    # Try to convert ints and floats before committing
                    if "." in value:
                        try:
                            value = float(value)
                        except ValueError:
                            pass
                    else:
                        try:
                            value = int(value)
                        except ValueError:
                            pass
            # Create section if not exists
            if section not in config_dict.keys():
                config_dict[section] = {}

            config_dict[section][entry] = value
        return config_dict

    right_click_menu = ["", [_t("generic.decrypt")]]

    backup_col = [
        [sg.Text(_t("config_gui.backup"), font="helvetica 16")],
        [
            sg.Text(_t("config_gui.compression"), size=(30, 1)),
            sg.Combo(["auto", "max", "off"], key="backup---compression", size=(48, 1)),
        ],
        [
            sg.Text(
                "{}\n({})".format(
                    _t("config_gui.backup_paths"), _t("config_gui.one_per_line")
                ),
                size=(30, 2),
            ),
            sg.Multiline(key="backup---paths", size=(48, 4)),
        ],
        [
            sg.Text(
                "{}\n({})".format(
                    _t("config_gui.use_fs_snapshot"), _t("config_gui.windows_only")
                ),
                size=(30, 2),
            ),
            sg.Checkbox("", key="backup---use_fs_snapshot", size=(0, 1)),
        ],
        [
            sg.Text(
                "{}\n({})".format(
                    _t("config_gui.exclude_files"), _t("config_gui.one_per_line")
                ),
                size=(30, 2),
            ),
            sg.Multiline(key="backup---exclude_files", size=(48, 4)),
        ],
        [
            sg.Text(
                "{}\n({})".format(
                    _t("config_gui.exclude_case_ignore"),
                    _t("config_gui.windows_always"),
                ),
                size=(30, 2),
            ),
            sg.Checkbox("", key="backup---exclude_case_ignore", size=(0, 1)),
        ],
        [
            sg.Text(_t("config_gui.exclude_cache_dirs"), size=(30, 1)),
            sg.Checkbox("", key="backup---exclude_caches", size=(0, 1)),
        ],
        [
            sg.Text(_t("config_gui.one_file_system"), size=(30, 1)),
            sg.Checkbox("", key="backup---one_file_system", size=(0, 1)),
        ],
        [
            sg.Text(_t("config_gui.pre_exec_command"), size=(30, 1)),
            sg.Input(key="backup---pre_exec_command", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.maximum_exec_time"), size=(30, 1)),
            sg.Input(key="backup---pre_exec_timeout", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.exec_failure_is_fatal"), size=(30, 1)),
            sg.Checkbox("", key="backup---pre_exec_failure_is_fatal", size=(0, 1)),
        ],
        [
            sg.Text(_t("config_gui.post_exec_command"), size=(30, 1)),
            sg.Input(key="backup---post_exec_command", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.maximum_exec_time"), size=(30, 1)),
            sg.Input(key="backup---post_exec_timeout", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.exec_failure_is_fatal"), size=(30, 1)),
            sg.Checkbox("", key="backup---post_exec_failure_is_fatal", size=(0, 1)),
        ],
        [
            sg.Text(
                "{}\n({})".format(_t("config_gui.tags"), _t("config_gui.one_per_line")),
                size=(30, 2),
            ),
            sg.Multiline(key="backup---tags", size=(48, 2)),
        ],
        [
            sg.Text(_t("config_gui.backup_priority"), size=(30, 1)),
            sg.Combo(["low", "normal", "high"], key="backup---priority", size=(48, 1)),
        ],
        [
            sg.Text(_t("config_gui.additional_parameters"), size=(30, 1)),
            sg.Input(key="backup---additional_parameters", size=(50, 1)),
        ],
    ]

    repo_col = [
        [sg.Text(_t("config_gui.backup_destination"), font="helvetica 16")],
        [
            sg.Text(
                "{}\n({})".format(
                    _t("config_gui.maximum_backup_age"), _t("generic.seconds")
                ),
                size=(30, 2),
            ),
            sg.Input(key="repo---minimum_backup_age", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.backup_repo_uri"), size=(30, 1)),
            sg.Input(key="repo---repository", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.backup_repo_password"), size=(30, 1)),
            sg.Input(key="repo---password", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.upload_speed"), size=(30, 1)),
            sg.Input(key="repo---upload_speed", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.download_speed"), size=(30, 1)),
            sg.Input(key="repo---download_speed", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.backend_connections"), size=(30, 1)),
            sg.Input(key="repo---backend_connections", size=(50, 1)),
        ],
    ]

    options_col = [
        [sg.Text(_t("config_gui.prometheus_config"), font="helvetica 16")],
        [sg.Text(_t("config_gui.explanation"))],
        [
            sg.Text(_t("config_gui.enable_prometheus"), size=(30, 1)),
            sg.Checkbox("", key="prometheus---metrics", size=(0, 1)),
        ],
        [
            sg.Text(_t("config_gui.job_name"), size=(30, 1)),
            sg.Input(key="prometheus---backup_job", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.metrics_destination"), size=(30, 1)),
            sg.Input(key="prometheus---destination", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.metrics_username"), size=(30, 1)),
            sg.Input(key="prometheus---http_username", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.metrics_password"), size=(30, 1)),
            sg.Input(key="prometheus---http_password", size=(50, 1)),
        ],
        [
            sg.Text(_t("config_gui.instance"), size=(30, 1)),
            sg.Input(key="prometheus---instance", size=(50, 1)),
        ],
        [
            sg.Text(_t("generic.group"), size=(30, 1)),
            sg.Input(key="prometheus---group", size=(50, 1)),
        ],
        [
            sg.Text(
                "{}\n({}\n{})".format(
                    _t("config_gui.additional_labels"),
                    _t("config_gui.one_per_line"),
                    _t("config_gui.format_equals"),
                ),
                size=(30, 3),
            ),
            sg.Multiline(key="prometheus---additional_labels", size=(48, 3)),
        ],
    ]

    env_col = [
        [sg.Text(_t("config_gui.environment_variables"), font="helvetica 16")],
        [
            sg.Text(
                "{}\n({}\n{})".format(
                    _t("config_gui.environment_variables"),
                    _t("config_gui.one_per_line"),
                    _t("config_gui.format_equals"),
                ),
                size=(30, 3),
            ),
            sg.Multiline(key="env---variables", size=(48, 3)),
        ],
    ]

    buttons = [
        [
            sg.Text(" " * 135),
            sg.Button(_t("generic.accept"), key="accept"),
            sg.Button(_t("generic.cancel"), key="cancel"),
        ]
    ]

    layout = [
        [
            sg.Column(
                [
                    [
                        sg.Column(
                            backup_col,
                            element_justification="L",
                            scrollable=False,
                            vertical_scroll_only=False,
                            size=(620, 610),
                            vertical_alignment="top",
                        ),
                    ]
                ],
                vertical_alignment="top",
            ),
            sg.Column(
                [
                    [
                        sg.Column(
                            repo_col,
                            element_justification="L",
                            scrollable=False,
                            vertical_scroll_only=False,
                            size=(620, 210),
                            vertical_alignment="top",
                        )
                    ],
                    [
                        sg.Column(
                            options_col,
                            element_justification="L",
                            scrollable=False,
                            vertical_scroll_only=False,
                            size=(620, 300),
                            vertical_alignment="top",
                        )
                    ],
                    [
                        sg.Column(
                            env_col,
                            element_justification="L",
                            scrollable=False,
                            vertical_scroll_only=False,
                            size=(620, 100),
                            vertical_alignment="top",
                        )
                    ],
                ],
                vertical_alignment="top",
            ),
        ],
        [sg.Column(buttons, element_justification="C")],
    ]

    window = sg.Window(
        "Configuration",
        layout,
        text_justification="L",
        auto_size_text=True,
        auto_size_buttons=False,
        no_titlebar=False,
        grab_anywhere=True,
        keep_on_top=False,
        alpha_channel=0.9,
        default_button_element_size=(12, 1),
        right_click_menu=right_click_menu,
        finalize=True,
    )

    update_gui(window, config_dict, unencrypted=False)

    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, "cancel"):
            break
        if event == "accept":
            config_dict = update_config_dict(values, config_dict)
            configuration.save_config(config_file, config_dict)
            sg.Popup(_t("config_gui.configuration_saved"), keep_on_top=True)
            logger.info("Configuration saved successfully.")
            break
        if event == _t("generic.decrypt"):
            if (
                sg.PopupGetText(_t("config_gui.enter_backup_admin_password"))
                == configuration.ADMIN_PASSWORD
            ):
                update_gui(window, config_dict, unencrypted=True)
            else:
                sg.PopupError(_t("config_gui.wrong_password"))
    window.close()
    return config_dict
