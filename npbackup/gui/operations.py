#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.operations"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023083101"


from typing import Tuple
from logging import getLogger
import re
import queue
import PySimpleGUI as sg
import npbackup.configuration as configuration
from ofunctions.threading import threaded, Future
from npbackup.core.runner import NPBackupRunner
from npbackup.core.i18n_helper import _t
from npbackup.customization import (
    OEM_STRING,
    OEM_LOGO,
    GUI_LOADER_COLOR,
    GUI_LOADER_TEXT_COLOR,
    GUI_STATE_OK_BUTTON,
    GUI_STATE_OLD_BUTTON,
    GUI_STATE_UNKNOWN_BUTTON,
    LOADER_ANIMATION,
    FOLDER_ICON,
    FILE_ICON,
    LICENSE_TEXT,
    LICENSE_FILE,
)


logger = getLogger(__intname__)


def add_repo(config_dict: dict) -> dict:
    pass


def get_friendly_repo_name(repository: str) -> Tuple[str, str]:
    backend_type = repository.split(":")[0].upper()
    if backend_type.upper() in ["REST", "SFTP"]:
        # Filter out user / password
        res = re.match(r"(sftp|rest).*:\/\/(.*):?(.*)@(.*)", repository, re.IGNORECASE)
        if res:
            backend_uri = res.group(1) + res.group(2) + res.group(4)
            backend_uri = repository
    elif backend_type.upper() in [
                "S3",
                "B2",
                "SWIFT",
                "AZURE",
                "GS",
                "RCLONE",
            ]:
        backend_uri = repository
    else:
        backend_type = 'LOCAL'
        backend_uri = repository
    return backend_type, backend_uri

def gui_update_state(window, config_dict: dict) -> list:
    repo_list = []
    try:
        for repo_name in config_dict['repos']:
            if config_dict['repos'][repo_name]['repository'] and config_dict['repos'][repo_name]['password']:
                backend_type, repo = get_friendly_repo_name(config_dict['repos'][repo_name]['repository'])
                repo_list.append("[{}] {}".format(backend_type, repo))
            else:
                logger.warning("Incomplete operations repo {}".format(repo_name))
    except KeyError:
        logger.info("No operations repos configured")
    if config_dict['repo']['repository'] and config_dict['repo']['password']:
        backend_type, repo = get_friendly_repo_name(config_dict['repo']['repository'])
        repo_list.append("[{}] {}".format(backend_type, repo))
    window['repo-list'].update(repo_list)
    return repo_list

def operations_gui(config_dict: dict, config_file: str) -> dict:
    """
    Operate on one or multiple repositories
    """
    layout = [
    [
        sg.Column(
            [
                [
                    sg.Column(
                        [[sg.Image(data=OEM_LOGO, size=(64, 64))]], vertical_alignment="top"
                    ),
                    sg.Column(
                        [
                            [sg.Text(OEM_STRING, font="Arial 14")],
                        ],
                        justification="C",
                        element_justification="C",
                        vertical_alignment="top",
                    ),
                ],
                [
                    sg.Text(_t("operations_gui.configured_repositories"))
                ],
                [sg.Listbox(values=[], key="repo-list", size=(80, 15))],
                [sg.Button(_t("operations_gui.add_repo"), key="add-repo"), sg.Button(_t("operations_gui.edit_repo"), key="edit-repo"), sg.Button(_t("operations_gui.remove_repo"), key="remove-repo")],
                [sg.Button(_t("operations_gui.quick_check"), key="quick-check"), sg.Button(_t("operations_gui.full_check"), key="full-check")],
                [sg.Button(_t("operations_gui.forget_using_retention_policy"), key="forget")],
                [sg.Button(_t("operations_gui.standard_prune"), key="standard-prune"), sg.Button(_t("operations_gui.max_prune"), key="max-prune")],
                [sg.Button(_t("generic.quit"), key="exit")],
            ],
            element_justification="C",
        )
    ]
]


    window = sg.Window(
    "Configuration",
    layout,
    size=(600,600),
    text_justification="C",
    auto_size_text=True,
    auto_size_buttons=True,
    no_titlebar=False,
    grab_anywhere=True,
    keep_on_top=False,
    alpha_channel=1.0,
    default_button_element_size=(12, 1),
    finalize=True,
    )

    full_repo_list = gui_update_state(window, config_dict)
    window.Element('repo-list').Widget.config(selectmode = sg.LISTBOX_SELECT_MODE_EXTENDED)
    while True:
        event, values = window.read(timeout=60000)

        if event in (sg.WIN_CLOSED, "exit"):
            break
        if event == 'add-repo':
            pass
        if event in ['add-repo', 'remove-repo']:
            if not values["repo-list"]:
                sg.Popup(_t("main_gui.select_backup"), keep_on_top=True)
                continue
            if event == 'add-repo':
                config_dict = add_repo(config_dict)
                # Save to config here #TODO #WIP
                event == 'state-update'
            elif event == 'remove-repo':
                result = sg.popup(_t("generic.are_you_sure"), custom_text = (_t("generic.yes"), _t("generic.no")))
                if result == _t("generic.yes"):
                    # Save to config here #TODO #WIP
                    event == 'state-update'
        if event == 'forget':
            pass
        if event in ['forget', 'quick-check', 'full-check', 'standard-prune', 'max-prune']:
            if not values["repo-list"]:
                result = sg.popup(_t("operations_gui.apply_to_all"), custom_text = (_t("generic.yes"), _t("generic.no")))
                if not result == _t("generic.yes"):
                    continue
                repos = full_repo_list
            else:
                repos = values["repo-list"]
            result_queue = queue.Queue()
            runner = NPBackupRunner()
            runner.group_runner(repos, result_queue)
        if event == 'state-update':
            full_repo_list = gui_update_state(window, config_dict)


    return config_dict