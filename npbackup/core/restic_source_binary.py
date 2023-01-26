import os
import glob

RESTIC_SOURCE_FILES_DIR = "RESTIC_SOURCE_FILES"


def get_restic_internal_binary(arch):
    binary = None
    if os.path.isdir(RESTIC_SOURCE_FILES_DIR):
        if os.name == "nt":
            if arch == "x64":
                binary = "restic_*_windows_amd64.exe"
            else:
                binary = "restic_*_windows_386.exe"
        else:
            if arch == "x64":
                binary = "restic_*_linux_amd64"
            else:
                binary = "restic_*_linux_386"
    if binary:
        guessed_path = glob.glob(os.path.join(RESTIC_SOURCE_FILES_DIR, binary))
        if guessed_path:
            return guessed_path[0]
