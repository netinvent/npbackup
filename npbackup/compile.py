#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.compile-and-package-for-windows"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023012201"
__version__ = "1.3.0"


import sys
import os
from command_runner import command_runner
from npbackup import __version__ as npbackup_version
from NPBackupInstaller import __version__ as installer_version
from customization import (
    COMPANY_NAME,
    TRADEMARKS,
    PRODUCT_NAME,
    FILE_DESCRIPTION,
    COPYRIGHT,
    LICENSE_FILE,
)
from core.restic_source_binary import get_restic_internal_binary
from path_helper import BASEDIR


def check_private_build():
    private = False
    try:
        import _private_secret_keys

        print("WARNING: Building with private secret key")
        private = True
    except ImportError:
        try:
            import secret_keys

            print("Building with default secret key")
        except ImportError:
            print("Cannot find secret keys")
            sys.exit()

    dist_conf_file_path = get_private_conf_dist_file()
    if "_private" in dist_conf_file_path:
        print("WARNING: Building with a private conf.dist file")
        private = True

    return private


def get_private_conf_dist_file():
    private_dist_conf_file = "_private_npbackup.conf.dist"
    dist_conf_file = "npbackup.conf.dist"
    dist_conf_file_path = os.path.join(BASEDIR, "examples", private_dist_conf_file)
    if not os.path.isfile(dist_conf_file_path):
        dist_conf_file_path = os.path.join(BASEDIR, "examples", dist_conf_file)

    return dist_conf_file_path


def compile(arch="64"):
    OUTPUT_DIR = os.path.join(
        BASEDIR, "BUILD" + "-PRIVATE" if check_private_build() else ""
    )

    if not os.path.isdir(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    PYTHON_EXECUTABLE = sys.executable

    # npbackup compilation
    # Strip possible version suffixes '-dev'
    _npbackup_version = npbackup_version.split("-")[0]
    PRODUCT_VERSION = _npbackup_version + ".0"
    FILE_VERSION = _npbackup_version + ".0"

    file_description = "{} P{}-{}".format(FILE_DESCRIPTION, sys.version_info[1], arch)

    restic_source_file = get_restic_internal_binary(arch)
    if not restic_source_file:
        print("Cannot find restic source file.")
        return
    output_arch_dir = os.path.join(
        OUTPUT_DIR,
        "win-p{}{}-{}".format(sys.version_info[0], sys.version_info[1], arch),
    )

    if os.name == "nt":
        program_executable = "npbackup.exe"
    else:
        program_executable = "npbackup"
    program_executable_path = os.path.join(output_arch_dir, program_executable)

    translations_dir = "translations"
    translations_dir_path = os.path.join(BASEDIR, translations_dir)

    # Override default config file with a private version if needed
    private_dist_conf_file = "_private_npbackup.conf.dist"
    dist_conf_file = "npbackup.conf.dist"
    dist_conf_file_path = get_private_conf_dist_file()

    excludes_dir = "excludes"
    excludes_dir_path = os.path.join(BASEDIR, excludes_dir)

    EXE_OPTIONS = '--company-name="{}" --product-name="{}" --file-version="{}" --product-version="{}" --copyright="{}" --file-description="{}" --trademarks="{}"'.format(
        COMPANY_NAME,
        PRODUCT_NAME,
        FILE_VERSION,
        PRODUCT_VERSION,
        COPYRIGHT,
        file_description,
        TRADEMARKS,
    )
    CMD = '{} -m nuitka --python-flag=no_docstrings --python-flag=-O --onefile --plugin-enable=tk-inter --include-data-dir="{}"="{}" --include-data-file="{}"=LICENSE.md --include-data-file={}=restic.exe --windows-icon-from-ico=npbackup_icon.ico {} --output-dir="{}" npbackup.py'.format(
        PYTHON_EXECUTABLE,
        translations_dir_path,
        translations_dir,
        LICENSE_FILE,
        restic_source_file,
        EXE_OPTIONS,
        output_arch_dir,
    )

    print(CMD)
    errors = False
    exit_code, output = command_runner(CMD, timeout=0, live_output=True)
    if exit_code != 0:
        errors = True

    # installer compilation
    _installer_version = installer_version.split("-")[0]
    PRODUCT_VERSION = _installer_version + ".0"
    FILE_VERSION = _installer_version + ".0"
    EXE_OPTIONS = '--company-name="{}" --product-name="{}" --file-version="{}" --product-version="{}" --copyright="{}" --file-description="{}" --trademarks="{}"'.format(
        COMPANY_NAME,
        PRODUCT_NAME,
        FILE_VERSION,
        PRODUCT_VERSION,
        COPYRIGHT,
        file_description,
        TRADEMARKS,
    )
    CMD = '{} -m nuitka --python-flag=no_docstrings --python-flag=-O --onefile --plugin-enable=tk-inter --include-data-file="{}"="{}" --include-data-file="{}"="{}" --include-data-dir="{}"="{}" --windows-icon-from-ico=npbackup_icon.ico --windows-uac-admin {} --output-dir="{}" NPBackupInstaller.py'.format(
        PYTHON_EXECUTABLE,
        program_executable_path,
        program_executable,
        dist_conf_file_path,
        dist_conf_file,
        excludes_dir_path,
        excludes_dir,
        EXE_OPTIONS,
        output_arch_dir,
    )

    print(CMD)
    exit_code, output = command_runner(CMD, timeout=0, live_output=True)
    if exit_code != 0:
        errors = True

    print("ERRORS", errors)


if __name__ == "__main__":
    # I know, I could improve UX here

    compile(arch=sys.argv[1])
    check_private_build()
