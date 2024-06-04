#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.sign_windows"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024060401"
__version__ = "1.1.2"


import os
try:
    from windows_tools.signtool import SignTool
except ImportError:
    print("This tool needs windows_tools.signtool >= 0.3.1")


basepath = r"C:\GIT\npbackup\BUILDS"
audiences = ["private", "public"]
arches = ["x86", "x64"]
binaries = ["npbackup-cli", "npbackup-gui", "npbackup-viewer"]

signer = SignTool()

for audience in audiences:
    for arch in arches:
        for binary in binaries:
            one_file_exe_path = exe_path = os.path.join(basepath, audience, "windows", arch, binary + f"-{arch}.exe")
            standalone_exe_path = os.path.join(basepath, audience, "windows", arch, binary + ".dist", binary + f".exe")
            for exe_file in (one_file_exe_path, standalone_exe_path):
                if os.path.isfile(exe_file):
                    print(f"Signing {exe_file}")
                    result = signer.sign(exe_file, bitness=arch)
                    if not result:
                        raise EnvironmentError(
                            "Could not sign executable ! Is the PKI key connected ?"
                        )
