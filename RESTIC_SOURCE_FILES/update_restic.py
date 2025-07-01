#! /usr/bin/env python3
#  -*- coding: utf-8 -*-


__intname__ = "npbackup.restic_update"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2024-2025 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2025062901"

import os
import sys
import bz2
from pathlib import Path
import requests
import json
import shutil
from pprint import pprint


sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from npbackup.path_helper import BASEDIR


def download_restic_binaries(arch: str = "amd64") -> bool:
    """
    We must first download latest restic binaries to make sure we can run all tests and/or compile
    """
    org = "restic"
    repo = "restic"

    response = requests.get(
        f"https://api.github.com/repos/{org}/{repo}/releases/latest"
    )
    # print("RESPONSE: ", response)
    if response.status_code != 200:
        print(f"ERROR: Cannot get latest restic release: {response.status_code}")
        print("RESPONSE TEXT: ", response.text)
        return False
    json_response = json.loads(response.text)
    current_version = json_response["tag_name"].lstrip("v")

    # print("JSON RESPONSE")
    # pprint(json_response, indent=5)

    dest_dir = Path(BASEDIR).absolute().parent.joinpath("RESTIC_SOURCE_FILES")
    if os.name == "nt":
        fname = f"_windows_{arch}"
        suffix = ".exe"
        arch_suffix = ".zip"
    elif sys.platform.lower() == "darwin":
        fname = f"_darwin_{arch}"
        suffix = ""
        arch_suffix = ".bz2"
    else:
        fname = f"_linux_{arch}"
        suffix = ""
        arch_suffix = ".bz2"

    if not dest_dir.joinpath("ARCHIVES").is_dir():
        os.makedirs(dest_dir.joinpath("ARCHIVES"))

    dest_file = dest_dir.joinpath("restic_" + current_version + fname + suffix)
    print(f"Projected dest file is {dest_file}")

    if dest_file.is_file():
        print(f"RESTIC SOURCE ALREADY PRESENT. NOT DOWNLOADING {dest_file}")
        return True
    else:
        print(f"DOWNLOADING RESTIC {dest_file}")
        # Also we need to move any earlier file that may not be current version to archives
        for file in dest_dir.glob(f"restic_*{fname}{suffix}"):
            # We need to keep legacy binary for Windows 7 / Server 2008
            if "legacy" in file.name:
                try:
                    archive_file = dest_dir.joinpath("ARCHIVES").joinpath(file.name)
                    if archive_file.is_file():
                        archive_file.unlink()
                    shutil.move(
                        file,
                        archive_file,
                    )
                except OSError as exc:
                    print(
                        f"CANNOT MOVE OLD FILES ARCHIVE: {file} to {archive_file}: {exc}"
                    )
                    return False

    downloaded = False
    for entry in json_response["assets"]:
        if f"{fname}{arch_suffix}" in entry["browser_download_url"]:
            file_request = requests.get(
                entry["browser_download_url"], allow_redirects=True
            )
            print("FILE REQUEST RESPONSE", file_request)
            filename = entry["browser_download_url"].rsplit("/", 1)[1]
            full_path = dest_dir.joinpath(filename)
            print("PATH TO DOWNLOADED ARCHIVE: ", full_path)
            if arch_suffix == ".bz2":
                final_executable = str(full_path).rstrip(arch_suffix)
                with open(final_executable, "wb") as fp:
                    fp.write(bz2.decompress(file_request.content))
                # We also need to make that file executable
                os.chmod(str(full_path).rstrip(arch_suffix), 0o775)
            else:
                with open(full_path, "wb") as fp:
                    fp.write(file_request.content)
                # Assume we have a zip or tar.gz
                shutil.unpack_archive(full_path, dest_dir)
                final_executable = dest_dir.joinpath(filename)
            try:
                # We don't drop the bz2 files on disk, so no need to move them to ARCHIVES
                if arch_suffix != ".bz2":
                    if dest_dir.joinpath("ARCHIVES").joinpath(filename).is_file():
                        dest_dir.joinpath("ARCHIVES").joinpath(filename).unlink()
                    shutil.move(
                        full_path, dest_dir.joinpath("ARCHIVES").joinpath(filename)
                    )
            except OSError as exc:
                print(
                    f'CANNOT MOVE TO ARCHIVE: {full_path} to {dest_dir.joinpath("ARCHIVES").joinpath(filename)}: {[exc]}'
                )
                return False
            print(f"DOWNLOADED {final_executable}")
            downloaded = True
            break
    if not downloaded:
        print(f"NO RESTIC BINARY FOUND for {arch}")
        return False
    return True


def download_restic_binaries_for_arch():
    """
    Shortcut to be used in compile script
    """
    if os.name == "nt":
        if not download_restic_binaries("amd64") or not download_restic_binaries("386"):
            sys.exit(1)
    else:
        if (
            not download_restic_binaries("amd64")
            or not download_restic_binaries("arm64")
            or not download_restic_binaries("arm")
        ):
            sys.exit(1)
    return True


if __name__ == "__main__":
    download_restic_binaries_for_arch()
