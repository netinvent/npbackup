#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.sign_windows"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023050301"
__version__ = "1.0.0"


import os
from windows_tools.signtool import SignTool


basepath = r"C:\GIT\npbackup\BUILDS"
audiences = ["private", "public"]
arches = ["x86", "x64"]
binaries = ["NPBackup.exe", "NPBackupInstaller.exe"]

signer = SignTool()

for audience in audiences:
    for arch in arches:
        for binary in binaries:
            exe_path = os.path.join(basepath, audience, "windows", arch, binary)
            result = signer.sign(exe_path, bitness=arch)
            if not result:
                raise EnvironmentError("Could not sign executable ! Is the PKI key connected ?")