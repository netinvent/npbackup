#! /usr/bin/env python3
#  -*- coding: utf-8 -*-


__intname__ = "npbackup.restic_update"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2024 NetInvent"
__license__ = "BSD-3-Clause"
__build__ = "2024121001"

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


def download_restic_binaries(arch: str = "amd64", move_is_fatal: bool = True) -> bool:
    """
    We must first download latest restic binaries to make sure we can run all tests and/or compile
    """
    org = "restic"
    repo = "restic"

    response = requests.get(
        f"https://api.github.com/repos/{org}/{repo}/releases/latest"
    )
    # print("RESPONSE: ", response)
    json_response = json.loads(response.text)
    current_version = json_response["tag_name"].lstrip("v")
    # print("JSON RESPONSE")
    # pprint(json_response, indent=5)

    dest_dir = Path(BASEDIR).absolute().parent.joinpath("RESTIC_SOURCE_FILES")
    if os.name == "nt":
        fname = f"_windows_{arch}.zip"
        suffix = ".exe"
    else:
        fname = f"_linux_{arch}.bz2"
        suffix = ""

    dest_file = dest_dir.joinpath("restic_" + current_version + fname).with_suffix(
        suffix
    )
    if dest_file.is_file():
        print(f"RESTIC SOURCE ALREADY PRESENT. NOT DOWNLOADING {dest_file}")
        return True
    else:
        print(f"DOWNALOADING RESTIC {dest_file}")

    downloaded = False
    for entry in json_response["assets"]:
        if fname in entry["browser_download_url"]:
            file_request = requests.get(
                entry["browser_download_url"], allow_redirects=True
            )
            print("FILE REQUEST RESPONSE", file_request)
            filename = entry["browser_download_url"].rsplit("/", 1)[1]
            full_path = dest_dir.joinpath(filename)
            print("PATH TO DOWNLOADED ARCHIVE: ", full_path)
            if fname.endswith("bz2"):
                with open(full_path.with_suffix(""), "wb") as fp:
                    fp.write(bz2.decompress(file_request.content))
                # We also need to make that file executable
                os.chmod(full_path.with_suffix(""), 0o775)
            else:
                with open(full_path, "wb") as fp:
                    fp.write(file_request.content)
                # Assume we have a zip or tar.gz
                shutil.unpack_archive(full_path, dest_dir)
            try:
                if not dest_dir.joinpath("ARCHIVES").is_dir():
                    os.makedirs(dest_dir.joinpath("ARCHIVES"))
                shutil.move(full_path, dest_dir.joinpath("ARCHIVES").joinpath(filename))
            except OSError:
                if move_is_fatal:
                    print(
                        f'CANNOT MOVE TO ARCHIVE: {full_path} to {dest_dir.joinpath("ARCHIVES").joinpath(filename)}'
                    )
                    return False
            print(f"DOWNLOADED {dest_dir}")
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


if __name__ == "__main__":
    download_restic_binaries_for_arch()
