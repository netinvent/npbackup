#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.customization_creator"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2024-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2025051101"
__version__ = "1.0.0"

import os
import re
import base64
from npbackup.path_helper import BASEDIR


"""
Launching this file will update customization.py inline png images and gif animations with files from resources directory, if exist
"""


def image_to_data_url(filename, as_url: bool = False):
    ext = filename.split(".")[-1]
    with open(filename, "rb") as f:
        img = f.read()
    if as_url:
        return f"data:image/{ext};base64," + base64.b64encode(img).decode("utf-8")
    else:
        return base64.b64encode(img).decode("utf-8")


def update_custom_icons():
    """
    Update customization.py file with icon content
    """

    custom_resources = {
        "FILE_ICON": "file_icon.png",
        "FOLDER_ICON": "folder_icon.png",
        "INHERITED_FILE_ICON": "inherited_file_icon.png",
        "INHERITED_FOLDER_ICON": "inherited_folder_icon.png",
        "INHERITED_ICON": "inherited_icon.png",
        "INHERITED_IRREGULAR_FILE_ICON": "inherited_irregular_file_icon.png",
        "INHERITED_NEUTRAL_ICON": "inherited_neutral_icon.png",
        "INHERITED_TREE_ICON": "inherited_tree_icon.png",
        "IRREGULAR_FILE_ICON": "irregular_file_icon.png",
        "NON_INHERITED_ICON": "non_inherited_icon.png",
        "MISSING_FILE_ICON": "missing_file_icon.png",
        "INHERITED_MISSING_FILE_ICON": "inherited_missing_file_icon.png",
        "INHERITED_SYMLINK_ICON": "inherited_symlink_icon.png",
        "SYMLINK_ICON": "symlink_icon.png",
        "TREE_ICON": "tree_icon.png",
        "LOADING_ANIMATION": "loading.gif",
        "OEM_LOGO": "oem_logo.png",
        "OEM_ICON": "oem_icon.png",
        "THEME_CHOOSER_ICON": "theme_chooser_icon.png",
    }

    resources_dir = os.path.join(BASEDIR, os.path.pardir, "resources")
    customization_py = os.path.join(resources_dir, "customization.py")
    with open(customization_py, "r", encoding="utf-8") as f:
        customization = f.read()
    for var_name, file in custom_resources.items():
        file_path = os.path.join(resources_dir, file)
        if os.path.exists(file_path):
            print(f"Updating {var_name} with {file_path}")
            encoded_b64 = image_to_data_url(file_path)
            customization = re.sub(
                f'\n{var_name} = .*', f'\n{var_name} = b"{encoded_b64}"', customization, re.MULTILINE
            )
        else:
            print("No file found for", var_name)
    with open(customization_py, "w", encoding="utf-8") as f:
        f.write(customization)


if __name__ == "__main__":
    update_custom_icons()
