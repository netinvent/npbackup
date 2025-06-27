#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.sign_windows"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024090801"
__version__ = "1.2.0"


import os
import sys
import argparse
from cryptidy.symmetric_encryption import decrypt_message

try:
    from windows_tools.signtool import SignTool
except ImportError:
    print("This tool needs windows_tools.signtool >= 0.4.0")


basepath = r"C:\GIT\npbackup\BUILDS"
audiences = ["private", "public"]
arches = ["x86", "x64"]
binaries = ["npbackup-cli", "npbackup-gui", "npbackup-viewer"]


def check_private_ev():
    """
    Test if we have private ev data
    """
    try:
        from PRIVATE._ev_data import AES_EV_KEY
        from PRIVATE._obfuscation import obfuscation

        print("We have private EV certificate DATA")
        return obfuscation(AES_EV_KEY)
    except ImportError as exc:
        print("ERROR: Cannot load private EV certificate DATA: {}".format(exc))
        sys.exit(1)


def get_ev_data(cert_data_path):
    """
    This retrieves specific data for crypto env
    """
    aes_key = check_private_ev()
    with open(cert_data_path, "rb") as fp:
        ev_cert_data = fp.read()
    try:
        timestamp, ev_cert = decrypt_message(ev_cert_data, aes_key=aes_key)
        (
            pkcs12_certificate,
            pkcs12_password,
            container_name,
            cryptographic_provider,
        ) = ev_cert
    except Exception as exc:
        print(f"EV Cert data is corrupt: {exc}")
        sys.exit(1)
    return pkcs12_certificate, pkcs12_password, container_name, cryptographic_provider


def sign(
    executable: str = None,
    arch: str = None,
    ev_cert_data: str = None,
    dry_run: bool = False,
):
    if ev_cert_data:
        (
            pkcs12_certificate,
            pkcs12_password,
            container_name,
            cryptographic_provider,
        ) = get_ev_data(ev_cert_data)
        signer = SignTool(
            certificate=pkcs12_certificate,
            pkcs12_password=pkcs12_password,
            container_name=container_name,
            cryptographic_provider=cryptographic_provider,
        )
    else:
        signer = SignTool()

    if executable:
        print(f"Signing {executable}")
        result = signer.sign(executable, bitness=arch, dry_run=dry_run)
        if not result:
            # IMPORTANT: If using an automated crypto USB EV token, we need to stop on error so we don't lock ourselves out of the token with bad password attempts
            raise EnvironmentError(
                "Could not sign executable ! Is the PKI key connected ?"
            )
        return result

    for audience in audiences:
        for arch in arches:
            for binary in binaries:
                one_file_exe_path = os.path.join(
                    basepath, audience, "windows", arch, binary + f"-{arch}.exe"
                )
                standalone_exe_path = os.path.join(
                    basepath,
                    audience,
                    "windows",
                    arch,
                    binary + ".dist",
                    binary + ".exe",
                )
                for exe_file in (one_file_exe_path, standalone_exe_path):
                    if os.path.isfile(exe_file):
                        print(f"Signing {exe_file}")
                        result = signer.sign(exe_file, bitness=arch, dry_run=dry_run)
                        if not result:
                            # IMPORTANT: If using an automated crypto USB EV token, we need to stop on error so we don't lock ourselves out of the token with bad password attempts
                            raise EnvironmentError(
                                "Could not sign executable ! Is the PKI key connected ?"
                            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="npbackup sign_windows.py",
        description="Windows executable signer for NPBackup",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        required=False,
        help="Don't actually sign anything, just test command",
    )
    parser.add_argument(
        "--ev-cert-data",
        type=str,
        default=None,
        required=False,
        help="Path to EV certificate data",
    )

    args = parser.parse_args()

    sign(ev_cert_data=args.ev_cert_data, dry_run=args.dry_run)
