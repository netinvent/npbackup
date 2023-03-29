#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.compile"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023032901"
__version__ = "1.8.1"


"""
Nuitka compilation script tested for
 - windows 32 bits (Vista+)
 - windows 64 bits
 - Linux i386
 - Linux i686
 - Linux armv71
"""


import sys
import os
import argparse
import atexit
from command_runner import command_runner
from ofunctions.platform import python_arch

AUDIENCES = ["public", "private"]

# Insert parent dir as path se we get to use npbackup as package
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))


from npbackup.customization import (
    COMPANY_NAME,
    TRADEMARKS,
    PRODUCT_NAME,
    FILE_DESCRIPTION,
    COPYRIGHT,
    LICENSE_FILE,
)
from npbackup.core.restic_source_binary import get_restic_internal_binary
from npbackup.path_helper import BASEDIR
import glob

del sys.path[0]


def _read_file(filename):
    here = os.path.abspath(os.path.dirname(__file__))
    if sys.version_info[0] < 3:
        # With python 2.7, open has no encoding parameter, resulting in TypeError
        # Fix with io.open (slow but works)
        from io import open as io_open

        try:
            with io_open(
                os.path.join(here, filename), "r", encoding="utf-8"
            ) as file_handle:
                return file_handle.read()
        except IOError:
            # Ugly fix for missing requirements.txt file when installing via pip under Python 2
            return ""
    else:
        with open(os.path.join(here, filename), "r", encoding="utf-8") as file_handle:
            return file_handle.read()

def get_metadata(package_file):
    """
    Read metadata from package file
    """

    _metadata = {}

    for line in _read_file(package_file).splitlines():
        if line.startswith("__version__") or line.startswith("__description__"):
            delim = "="
            _metadata[line.split(delim)[0].strip().strip("__")] = (
                line.split(delim)[1].strip().strip("'\"")
            )
    return _metadata



def check_private_build(audience):
    private = None
    try:
        import PRIVATE._private_secret_keys
        print("INFO: Building with private secret key")
        private = True
    except ImportError:
        try:
            import npbackup.secret_keys

            print("INFO: Building with default secret key")
            private = False
        except ImportError:
            print("ERROR: Cannot find secret keys")
            sys.exit()

    # Drop private files if exist in memory
    try:
        del PRIVATE._private_secret_keys
    except Exception:
        pass

    dist_conf_file_path = get_conf_dist_file(audience)
    if dist_conf_file_path and "_private" in dist_conf_file_path:
        print("INFO: Building with a private conf.dist file")
        if audience != "private":
            print("ERROR: public build uses private conf.dist file")
            sys.exit(6)

    return private


def move_audience_files(audience):
    for dir in [os.path.join(BASEDIR, os.pardir, "PRIVATE"), BASEDIR]:
        if audience == "private":
            possible_non_used_path = "_NOUSE_private_"
            guessed_files = glob.glob(
                os.path.join(dir, "{}*".format(possible_non_used_path))
            )
            for file in guessed_files:
                new_file = file.replace(possible_non_used_path, "_private_")
                os.rename(file, new_file)
        elif audience == "public":
            possible_non_used_path = "_private_"
            guessed_files = glob.glob(
                os.path.join(dir, "{}*".format(possible_non_used_path))
            )
            for file in guessed_files:
                new_file = file.replace(
                        possible_non_used_path,
                        "_NOUSE{}".format(possible_non_used_path),
                    )
                os.rename(
                    file, new_file
                )
        else:
            raise "Bogus audience"


def get_conf_dist_file(audience):
    if audience == "private":
        dist_conf_file_path = os.path.join(BASEDIR, os.pardir, "PRIVATE", "_private_npbackup.conf.dist")
    else:
        dist_conf_file_path = os.path.join(BASEDIR, os.pardir, "examples", "npbackup.conf.dist")
    if not os.path.isfile(dist_conf_file_path):
        print("DIST CONF FILE NOT FOUND: {}".format(dist_conf_file_path))
        return None
    return dist_conf_file_path


def have_nuitka_commercial():
    try:
        import nuitka.plugins.commercial
        print("Running with nuitka commercial")
        return True
    except ImportError:
        print("Running with nuitka open source")
        return False


def compile(arch, audience, no_gui=False):
    if os.name == "nt":
        program_executable = "npbackup.exe"
        restic_executable = "restic.exe"
        platform = "windows"
    else:
        program_executable = "npbackup"
        restic_executable = "restic"
        platform = "linux"

    PACKAGE_DIR = "npbackup"

    BUILDS_DIR = os.path.abspath(os.path.join(BASEDIR, os.pardir, "BUILDS"))
    OUTPUT_DIR = os.path.join(BUILDS_DIR, audience, platform, arch)

    if not os.path.isdir(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    PYTHON_EXECUTABLE = sys.executable

    # npbackup compilation
    # Strip possible version suffixes '-dev'
    _npbackup_version = npbackup_version.split("-")[0]
    PRODUCT_VERSION = _npbackup_version + ".0"
    FILE_VERSION = _npbackup_version + ".0"

    file_description = "{} P{}-{}{}".format(
        FILE_DESCRIPTION,
        sys.version_info[1],
        arch,
        "priv" if audience == "private" else "",
    )

    restic_source_file = get_restic_internal_binary(arch)
    if not restic_source_file:
        print("Cannot find restic source file.")
        return False
    else:
        os.chmod(restic_source_file, 0o775)
    restic_dest_file = os.path.join(PACKAGE_DIR, restic_executable)

    translations_dir = "translations"
    translations_dir_source = os.path.join(BASEDIR, translations_dir)
    translations_dir_dest = os.path.join(PACKAGE_DIR, translations_dir)

    license_dest_file = os.path.join(PACKAGE_DIR, os.path.basename(LICENSE_FILE))

    icon_file = os.path.join(PACKAGE_DIR, "npbackup_icon.ico")

    # Installer specific files, no need for a npbackup package directory here

    program_executable_path = os.path.join(OUTPUT_DIR, program_executable)

    dist_conf_file_source = get_conf_dist_file(audience)
    if not dist_conf_file_source:
        print("Stopped {} compilation".format(audience))
        return
    dist_conf_file_dest = os.path.basename(
        dist_conf_file_source.replace("_private_", "")
    )

    excludes_dir = "excludes"
    excludes_dir_source = os.path.join(BASEDIR, os.pardir, excludes_dir)
    excludes_dir_dest = excludes_dir

    NUITKA_OPTIONS = ""
    NUITKA_OPTIONS += " --enable-plugin=data-hiding" if have_nuitka_commercial() else ""
    
    # Stupid fix for synology RS816 where /tmp is mounted with `noexec`.
    if "arm" in arch:
        NUITKA_OPTIONS += " --onefile-temp-spec=/var/tmp"

    if no_gui:
        NUITKA_OPTIONS += " --plugin-disable=tk-inter --nofollow-import-to=PySimpleGUI"
    else:
        NUITKA_OPTIONS += " --plugin-enable=tk-inter"

    EXE_OPTIONS = '--company-name="{}" --product-name="{}" --file-version="{}" --product-version="{}" --copyright="{}" --file-description="{}" --trademarks="{}"'.format(
        COMPANY_NAME,
        PRODUCT_NAME,
        FILE_VERSION,
        PRODUCT_VERSION,
        COPYRIGHT,
        file_description,
        TRADEMARKS,
    )

    CMD = '{} -m nuitka --python-flag=no_docstrings --python-flag=-O {} {} --onefile --include-data-dir="{}"="{}" --include-data-file="{}"="{}" --include-data-file="{}"="{}" --windows-icon-from-ico="{}" --output-dir="{}" bin/npbackup'.format(
        PYTHON_EXECUTABLE,
        NUITKA_OPTIONS,
        EXE_OPTIONS,
        translations_dir_source,
        translations_dir_dest,
        LICENSE_FILE,
        license_dest_file,
        restic_source_file,
        restic_dest_file,
        icon_file,
        OUTPUT_DIR,
    )

    print(CMD)
    errors = False
    exit_code, output = command_runner(CMD, timeout=0, live_output=True)
    if exit_code != 0:
        errors = True

    # windows only installer compilation
    if os.name == "nt":
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
        CMD = '{} -m nuitka --python-flag=no_docstrings --python-flag=-O {} {} --onefile --include-data-file="{}"="{}" --include-data-file="{}"="{}" --include-data-dir="{}"="{}" --windows-icon-from-ico="{}" --windows-uac-admin --output-dir="{}" bin/NPBackupInstaller.py'.format(
            PYTHON_EXECUTABLE,
            NUITKA_OPTIONS,
            EXE_OPTIONS,
            program_executable_path,
            program_executable,
            dist_conf_file_source,
            dist_conf_file_dest,
            excludes_dir_source,
            excludes_dir_dest,
            icon_file,
            OUTPUT_DIR,
        )

        print(CMD)
        exit_code, output = command_runner(CMD, timeout=0, live_output=True)
        if exit_code != 0:
            errors = True
        else:
            ## Create version file
            with open(os.path.join(BUILDS_DIR, audience, "VERSION"), "w") as fh:
                fh.write(npbackup_version)

    print("COMPILE ERRORS", errors)
    return not errors


class AudienceAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if values not in AUDIENCES + ["all"]:
            print("Got value:", values)
            raise argparse.ArgumentError(self, "Not a valid audience")
        setattr(namespace, self.dest, values)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="npbackup compile.py", description="Compiler script for NPBackup"
    )

    parser.add_argument(
        "--audience",
        type=str,
        dest="audience",
        default="public",
        required=False,
        help="Target audience, private or public",
    )

    parser.add_argument(
        "--no-gui",
        action="store_true",
        default=False,
        help="Don't compile GUI support"
    )

    args = parser.parse_args()

    # Make sure we get out dev environment back when compilation ends / fails
    atexit.register(
        move_audience_files,
        "private",
    )
    try:
        errors = False
        if args.audience.lower() == "all":
            audiences = AUDIENCES
        else:
            audiences = [args.audience]

        for audience in audiences:
            move_audience_files(audience)
            npbackup_version = get_metadata(os.path.join(BASEDIR, "__main__.py"))["version"]
            installer_version = get_metadata(os.path.join(BASEDIR, os.pardir, "bin", "NPBackupInstaller.py"))["version"]

            private_build = check_private_build(audience)
            if private_build and audience != "private":
                print("ERROR: Requested public build but private data available")
                errors = True
                continue
            elif not private_build and audience != "public":
                print("ERROR: Requested private build but no private data available")
                errors = True
                continue
            result = compile(arch=python_arch(), audience=audience, no_gui=args.no_gui)
            build_type = 'private' if private_build else 'public'
            if result:
                print("SUCCESS: MADE {} build for audience {}".format(build_type, audience))
            else:
                print("ERROR: Failed making {} build for audience {}".format(build_type, audience))
                errors = True
        if errors:
            print("ERRORS IN BUILD PROCESS")
        else:
            print("SUCCESS BUILDING")
    except Exception:
        print("COMPILATION FAILED")
        raise