#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.compile"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026042701"
__version__ = "2.4.1"


"""
Nuitka compilation script tested for
 - windows 32 bits (Vista+)
 - windows 64 bits
 - Linux i386
 - Linux i686
 - Linux armv71

 Also optionally signs windows executables

"""


from typing import Optional
import sys
import os
import shutil
import atexit
import argparse
import fileinput
from ofunctions.logger_utils import logger_get_logger
from command_runner import command_runner
from ofunctions.platform import python_arch
from npbackup.__version__ import IS_LEGACY

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from npbackup.path_helper import BASEDIR

SIGN_EXTERNALY = False
sign = None
if os.name == "nt":
    EXTERNAL_SIGNER = r"C:\ev_signer_npbackup\ev_signer_npbackup.exe"
    if os.path.isfile(EXTERNAL_SIGNER):
        SIGN_EXTERNALY = True
    else:
        SIGN_EXTERNALY = False
        from npbackup.windows.sign_windows import sign

try:
    from npbackup.audience import CURRENT_AUDIENCE, AUDIENCES
except ImportError:
    AUDIENCES = ["public"]

PRIVATE_AUDIENCE_FILE = os.path.abspath(os.path.join(BASEDIR, "..", "PRIVATE", "audience.py"))
INITIAL_AUDIENCE = CURRENT_AUDIENCE
BUILD_TYPES = ["cli", "gui", "viewer"]
BUILDS_DIR = os.path.abspath(os.path.join(BASEDIR, os.pardir, "BUILDS"))

# Insert parent dir as path se we get to use npbackup as package
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))


from resources.customization import (
    COMPANY_NAME,
    TRADEMARKS,
    PRODUCT_NAME,
    FILE_DESCRIPTION,
    COPYRIGHT,
)
from npbackup.core.restic_source_binary import get_restic_internal_binary
from npbackup.path_helper import BASEDIR
import glob


LICENSE_FILE = os.path.join(BASEDIR, os.pardir, "LICENSE")
NUITKA_STANDALONE_SUFFIX = ".dist"

del sys.path[0]


logger = logger_get_logger("compile.log")

def _set_audience(audience: str):
    with fileinput.FileInput(PRIVATE_AUDIENCE_FILE, inplace=True) as file:
        for line in file:
            if line.startswith("CURRENT_AUDIENCE"):
                line.split("=")[1].strip().strip("'\"")
                print(f"CURRENT_AUDIENCE = \"{audience}\"")
            else:
                print(line, end="")
    os.environ["_NPBACKUP_AUDIENCE"] = audience


def _read_file(filename: str) -> str:
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


def get_metadata(package_file: str) -> dict:
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


def extract_executable_name(executable_path: str) -> Optional[str]:
    for line in _read_file(executable_path).splitlines():
        if line.startswith("EXECUTABLE"):
            delim = "="
            return line.split(delim)[1].strip().strip("'\"")
    return None

def have_nuitka_commercial() -> bool:
    try:
        import nuitka.plugins.commercial

        logger.info("Running with nuitka commercial")
        return True
    except ImportError:
        logger.info("Running with nuitka open source")
        return False


def _compile(
    arch: str,
    audience: str,
    build_type: str,
    onefile: bool,
    create_tar_only: bool,
    ev_cert_data: Optional[str] = None,
    sign_only: bool = False,
    npbackup_version: Optional[str] = None,
):
    if build_type not in BUILD_TYPES:
        logger.error("CANNOT BUILD BOGUS BUILD TYPE")
        sys.exit(1)

    # Try to get alternative executable name
    audience_customization = os.path.join(BASEDIR, "..", "PRIVATE", audience, "_customization.py")
    
    executable_name = "npbackup"
    if os.path.isfile(audience_customization):
        executable_name = extract_executable_name(audience_customization)
        if isinstance(executable_name, str):
            logger.info(f"Found audience specific executable name {executable_name} for audience {audience}")
        else:
            logger.info("Using default executable name")
            executable_name = "npbackup"

    initial_source_program = "bin/npbackup-{}".format(build_type)
    audience_source_program = "bin/{}-{}".format(executable_name, build_type)
    if initial_source_program != audience_source_program:
        shutil.copyfile(initial_source_program, audience_source_program)
    

    if IS_LEGACY:
        arch = f"{arch}-legacy"
    if onefile:
        suffix = "-{}-{}-{}".format(build_type, arch, audience)
        if os.name == "nt":
            program_executable = "{}{}.exe".format(executable_name, suffix)
            restic_executable = "restic.exe"
            other_executables = ["klink.exe"]
            platform = "windows"
        elif sys.platform.lower() == "darwin":
            platform = "darwin"
            program_executable = "{}-{}{}".format(executable_name, platform, suffix)
            restic_executable = "restic"
            other_executables = []
        else:
            platform = "linux"
            program_executable = "{}-{}{}".format(executable_name, platform, suffix)
            restic_executable = "restic"
            other_executables = []
    else:
        if os.name == "nt":
            program_executable = "{}-{}.exe".format(executable_name, build_type)
            restic_executable = "restic.exe"
            platform = "windows"
            other_executables = ["klink.exe"]
        elif sys.platform.lower() == "darwin":
            platform = "darwin"
            program_executable = "{}-{}".format(executable_name, build_type)
            restic_executable = "restic"
            other_executables = []
        else:
            platform = "linux"
            program_executable = "{}-{}".format(executable_name, build_type)
            restic_executable = "restic"
            other_executables = []

    PACKAGE_DIR = "npbackup"

    OUTPUT_DIR = os.path.join(BUILDS_DIR, audience, platform, arch)

    if not os.path.isdir(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    PYTHON_EXECUTABLE = sys.executable

    # npbackup compilation
    # Strip possible version suffixes '-dev'
    logger.info(f"Compiling version {npbackup_version} for {audience} {platform} {arch}")
    _npbackup_version = npbackup_version.split("-")[0]
    PRODUCT_VERSION = _npbackup_version + ".0"
    FILE_VERSION = _npbackup_version + ".0"

    file_description = "{} P{}-{}-{}".format(
        FILE_DESCRIPTION,
        sys.version_info[1],
        arch,
        audience,
    )

    restic_source_file = get_restic_internal_binary(arch)
    if not restic_source_file:
        logger.error(f"Cannot find restic source file for arch {arch}.")
        return False
    else:
        os.chmod(restic_source_file, 0o775)
    restic_dest_file = os.path.join(PACKAGE_DIR, restic_executable)

    translations_dir = "translations"
    translations_dir_source = os.path.join(BASEDIR, translations_dir)
    translations_dir_dest = os.path.join(PACKAGE_DIR, translations_dir)

    license_dest_file = os.path.join(PACKAGE_DIR, os.path.basename(LICENSE_FILE))

    icon_file = os.path.join(BASEDIR, os.pardir, "resources", "npbackup_icon.ico")

    excludes_dir = "excludes"
    excludes_dir_source = os.path.join(BASEDIR, os.pardir, excludes_dir)
    excludes_dir_dest = excludes_dir

    # Include sv_ttk theme since we use an inline version with some fixes
    sv_ttl_dir_source = os.path.join(BASEDIR, "gui", "sv_ttk")
    sv_ttl_dir_dest = os.path.join(PACKAGE_DIR, "gui", "sv_ttk")

    # NUITKA_OPTIONS = " --clang"
    # As of Nuitka v1.8, `-c` parameter is used to prevent fork bomb self execution
    # We don't need this, so let's disable it so we can use `-c`as `--config-file` shortcut
    NUITKA_OPTIONS = " --no-deployment-flag=self-execution"
    NUITKA_OPTIONS += " --enable-plugin=data-hiding" if have_nuitka_commercial() else ""

    # Depending on audience, we will need to include private keys
    if audience != "public" and audience in AUDIENCES:
        logger.info("Updating audience file {} with audience {}".format(PRIVATE_AUDIENCE_FILE, audience))
        _set_audience(audience)

        NUITKA_OPTIONS += f" --include-module=PRIVATE.audience"
        NUITKA_OPTIONS += f" --include-module=PRIVATE.customization"
        NUITKA_OPTIONS += f" --include-module=PRIVATE.obfuscation"
        NUITKA_OPTIONS += f" --include-module=PRIVATE.secret_keys"
        NUITKA_OPTIONS += f" --include-module=PRIVATE.{audience}._customization"
        NUITKA_OPTIONS += f" --include-module=PRIVATE.{audience}._obfuscation"
        NUITKA_OPTIONS += f" --include-module=PRIVATE.{audience}._private_secret_keys"
    else:
        logger.info("Updating audience file {} with audience public".format(PRIVATE_AUDIENCE_FILE))
        _set_audience("public")

    if build_type in ("gui", "viewer"):
        NUITKA_OPTIONS += f" --plugin-enable=tk-inter --include-data-dir={sv_ttl_dir_source}={sv_ttl_dir_dest}"
        # So for an unknown reason, some windows builds will not hide the console, see #146
        # We replaced this option with a python version in gui\windiws_gui_helper.py
        NUITKA_OPTIONS += " --windows-console-mode=hide"
        # Since GUI can run as CLI, we need to include all cli modules
        if build_type == "viewer":
            NUITKA_OPTIONS += " --nofollow-import-to=npbackup.__main__"
    else:
        NUITKA_OPTIONS += " --plugin-disable=tk-inter"
        NUITKA_OPTIONS += " --nofollow-import-to=FreeSimpleGUI"
        NUITKA_OPTIONS += " --nofollow-import-to=_tkinter"
        NUITKA_OPTIONS += " --nofollow-import-to=npbackup.gui"
        NUITKA_OPTIONS += " --nofollow-import-to=npbackup.gui.__main__"

    if onefile:
        NUITKA_OPTIONS += " --onefile"
        # Stupid fix for synology RS816 where /tmp is mounted with `noexec`.
        if "arm" in arch:
            NUITKA_OPTIONS += " --onefile-tempdir-spec=/var/tmp"
    else:
        NUITKA_OPTIONS += " --standalone"

    if os.name != "nt":
        NUITKA_OPTIONS += " --nofollow-import-to=npbackup.windows"

    EXE_OPTIONS = f'--company-name="{COMPANY_NAME}" --product-name="{PRODUCT_NAME}" --file-version="{FILE_VERSION}"'
    EXE_OPTIONS += f' --product-version="{PRODUCT_VERSION}" --copyright="{COPYRIGHT}"'
    EXE_OPTIONS += f' --file-description="{file_description}" --trademarks="{TRADEMARKS}"'

    cmd = f'{PYTHON_EXECUTABLE} -m nuitka --python-flag=no_docstrings --python-flag=-O'
    cmd += f' {NUITKA_OPTIONS} {EXE_OPTIONS}'
    cmd += f' --include-data-dir="{excludes_dir_source}"="{excludes_dir_dest}"'
    cmd += f' --include-data-dir="{translations_dir_source}"="{translations_dir_dest}"'
    cmd += f' --include-data-file="{LICENSE_FILE}"="{license_dest_file}"'
    cmd += f' --include-data-file="{restic_source_file}"="{restic_dest_file}"'
    for other_executable in other_executables or []:
        src_file = os.path.join(os.path.dirname(restic_source_file), other_executable)
        dest_file = os.path.join(os.path.dirname(restic_dest_file), other_executable)
        cmd += f' --include-data-file="{src_file}"="{dest_file}"'
    cmd += f' --windows-icon-from-ico="{icon_file}"'
    cmd += f' --output-dir="{OUTPUT_DIR}" --output-filename="{program_executable}" {audience_source_program}'

    errors = False
    if not create_tar_only and not sign_only:
        logger.debug(cmd)
        exit_code, output = command_runner(cmd, timeout=0, live_output=True)
        if exit_code != 0:
            errors = True

        ## Create version file
        with open(
            os.path.join(BUILDS_DIR, audience, "VERSION"), "w", encoding="utf-8"
        ) as fh:
            fh.write(npbackup_version)
        if not errors:
            logger.info("COMPILED {} {} {} {} {} WITH SUCCESS".format(executable_name, build_type, audience, platform, arch))
        else:
            logger.error("COMPILED {} {} {} {} {} WITH ERRORS".format(executable_name, build_type, audience, platform, arch))

    if initial_source_program != audience_source_program:
        shutil.move(audience_source_program, initial_source_program)

    if os.name == "nt" and ev_cert_data:
        compiled_output_dir = os.path.join(
            OUTPUT_DIR, f"{executable_name}-{build_type}{NUITKA_STANDALONE_SUFFIX}"
        )
        npbackup_executable = os.path.join(
            compiled_output_dir, f"{executable_name}-{build_type}.exe"
        )
        if SIGN_EXTERNALY:
            logger.info(f"Signing with external signer {EXTERNAL_SIGNER}")
            cmd = f"{EXTERNAL_SIGNER} --executable {npbackup_executable}"
            logger.debug(cmd)
            exit_code, output = command_runner(cmd, shell=True)
            if exit_code != 0:
                logger.error(f"Could not sign: {output}")
                errors = True
        elif os.path.isfile(ev_cert_data):
            logger.info(f"Signing with internal signer {ev_cert_data}")
            sign(
                executable=npbackup_executable,
                arch=arch,
                ev_cert_data=ev_cert_data,
                dry_run=args.dry_run,
            )
        else:
            logger.error(f"Cannot sign windows executable: {SIGN_EXTERNALY} {ev_cert_data}")
            errors = True

    if not onefile:
        if not create_archive(
            platform=platform,
            arch=arch,
            audience=audience,
            build_type=build_type,
            output_dir=OUTPUT_DIR,
            executable_name=executable_name,
        ):
            errors = True
    return not errors


def create_archive(
    platform: str, arch: str, audience: str, build_type: str, output_dir: str, executable_name: str
):
    """
    Create tar releases for each compiled version
    """

    compiled_output = os.path.join(
        output_dir, "{}-{}{}".format(executable_name, build_type, NUITKA_STANDALONE_SUFFIX)
    )
    new_compiled_output = compiled_output[: -len(NUITKA_STANDALONE_SUFFIX)]
    if os.path.isdir(new_compiled_output):
        shutil.rmtree(new_compiled_output)
    shutil.move(compiled_output, new_compiled_output)
    if os.name == "nt":
        archive_extension = "zip"
    else:
        archive_extension = "tar.gz"

    target_archive = os.path.join(BUILDS_DIR, f"{executable_name}-{platform}-{arch}-{build_type}-{audience}.{archive_extension}")
    if os.path.isfile(target_archive):
        os.remove(target_archive)
    if os.name == "nt":
        # This supposes Windows 10 that comes with tar
        # This tar version will create a plain zip file when used with -a (and without -z which creates gzip files)
        cmd = f"tar -a -c -f {target_archive} -C {output_dir} {os.path.basename(new_compiled_output)}"
    else:
        cmd = f"tar -czf {target_archive} -C {output_dir} ./{os.path.basename(new_compiled_output)}"
    logger.info(f"Creating archive {target_archive}")
    exit_code, output = command_runner(cmd, timeout=0, live_output=True, shell=True)
    shutil.move(new_compiled_output, compiled_output)
    if exit_code != 0:
        logger.error(f"Cannot create archive file for {platform} {arch} {audience} {build_type}:")
        logger.error(output)
        return False
    return True


class AudienceAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if values not in AUDIENCES + ["all"]:
            logger.info("Got value:", values)
            raise argparse.ArgumentError(self, f"Audiences '{values}' is not a valid audience")
        setattr(namespace, self.dest, values)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="npbackup compile.py", description="Compiler script for NPBackup"
    )

    parser.add_argument(
        "--audience",
        type=str,
        dest="audience",
        default="all",
        required=False,
        help="Target audience, public or private builds (default: all)",
    )

    parser.add_argument(
        "--build-type",
        type=str,
        dest="build_type",
        default=None,
        required=False,
        help="Build cli, gui or viewer target",
    )

    parser.add_argument(
        "--onefile",
        action="store_true",
        default=False,
        required=False,
        help="Build single file executable (more prone to AV detection)",
    )

    parser.add_argument(
        "--sign",
        type=str,
        dest="ev_cert_data",
        default=False,
        required=False,
        help="Digitally sign windows executables",
    )

    parser.add_argument(
        "--sign-only",
        action="store_true",
        default=False,
        required=False,
        help="Only digitally sign built executables",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        required=False,
        help="Dry run current action",
    )

    parser.add_argument(
        "--create-tar-only",
        action="store_true",
        default=False,
        required=False,
        help="Only create tar files, shortcut when we need to package signed binaries",
    )

    args = parser.parse_args()

    try:
        errors = False
        if args.audience.lower() == "all":
            audiences = AUDIENCES
        else:
            audiences = [args.audience.lower()]

        if args.build_type:
            if args.build_type.lower() not in BUILD_TYPES:
                build_types = BUILD_TYPES
            else:
                build_types = [args.build_type.lower()]
        else:
            build_types = BUILD_TYPES

        create_tar_only = args.create_tar_only
        sign_only = args.sign_only

        atexit.register(_set_audience, audience=INITIAL_AUDIENCE)

        build_count = 0
        to_build = len(audiences) * len(build_types)
        for audience in audiences:
            npbackup_version = get_metadata(os.path.join(BASEDIR, "__version__.py"))[
                "version"
            ]
            for build_type in build_types:
                build_count += 1
                logger.info("Building {}/{} items ({} {})".format(build_count, to_build, audience, build_type))
                result = _compile(
                    arch=python_arch(),
                    audience=audience,
                    build_type=build_type,
                    onefile=args.onefile,
                    create_tar_only=create_tar_only,
                    ev_cert_data=args.ev_cert_data,
                    sign_only=sign_only,
                    npbackup_version=npbackup_version,
                )
                if not create_tar_only and not sign_only:
                    if result:
                        logger.info(
                            f"SUCCESS: MADE {build_type} build for audience {audience}"
                        )
                    else:
                        logger.error(
                            f"Failed making {build_type} build for audience {audience}"
                        )
                        errors = True
        if errors:
            logger.error("ERRORS IN BUILD PROCESS")
        else:
            logger.info("SUCCESS BUILDING")
    except Exception:
        logger.error("COMPILATION FAILED")
        raise
