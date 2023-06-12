# How to compile NPBackup from scratch

This document explains how to compile NPBackup from scratch, including setting up security.  

## Requirements

NPBackup will need a working Python 3.6+ interpreter, which is out of scope of this document.  
- On Windows, you should download and install python from [Python official website](https://www.python.org)
- On Linux, you should probably install python using your distribution's package manager, ex `yum install python3` or `apt install python`
- On macOS, you should probably use [brew](https://brew.sh) to install python, `brew install python3`

Please bear in mind that the python interpreter bitness will decide which executable bitness you'll have, eg if you want windows x64 executables, you'll need to download python x64.

For the rest of this manual, we'll assume the you use:
- On Windows:
  - `C:\python310-64\python.exe` as python interpreter
  - `C:\npbackup` as folder containing the NPBackup sources you downloaded and extracted / cloned from git
- On Linux:
  - `python3` as python interpreter
  - `/opt/npbackup` as folder containing the NPBackup sources you downloaded and extracted / cloned from git
- On macOS:
  - `~/npbackup` as folder containing the NPBackup sources you downloaded and extracted / cloned from git
  - as python interpreter
    - Intel: `/usr/local/bin/python3`
    - ARM: `/opt/homebrew/bin/python3`

You may also use a python virtual environement (venv) to have a python "sub interpreter", but this is out of scope here too.

Once you've got yourself a working Python environment, you should download and extract the NPBackup sources (or clone the git). NPBackup has multiple python dependencies, which are stated in a file named `requirements.txt`.  
You can install them all toghether by running `python -m pip install -r path/to/requirements.txt` (please note that `path/to/requirements.txt` would give something like `C:\path\to\requirements` on Windows)

Examples:
- On Windows: `C:\python310-64\python.exe -m pip install -r c:\npbackup\npbackup\requirements.txt`
- On Linux: `python3 -m pip install -r /opt/npbackup/npbackup/requirements.txt`
- On macOS:
  - Intel: `/usr/local/bin/python3 -m pip install -r ~/npbackup/npbackup/requirements.txt`
  - ARM: `/opt/homebrew/bin/python3 -m pip install -r ~/npbackup/npbackup/requirements.txt`

You will also need to install the [Nuitka Python compiler](https://www.nuitka.net). Pre-built executables are built with the commercial version of Nuitka, which has multiple advantages over the open source version, but the latter will suffice for a working build.

Example:
- On Windows: `C:\python310-64\python.exe -m pip install nuitka`
- On Linux: `python3 -m pip install nuitka`
- On macOS:
  - Intel: `/usr/local/bin/python3 -m pip install nuitka`
  - ARM: `/opt/homebrew/bin/python3 -m pip install nuitka`

## Backup backend

NPBackup relies on the excellent [restic](https://restic.net) backup program.  
In order for NPBackup to work, you'll need to download restic binaries from [the restic repo](https://github.com/restic/restic/releases/) into `npbackup/RESTIC_SOURCE_FILES` and uncompress them. On Windows, you'll probably want something that can uncompress bzip2 files, like 7zip or [7zip-zstd](https://github.com/mcmilk/7-Zip-zstd). On Linux, your standard `bzip2 -d` command will do. Please keep all restic binaries at the root of the source folder, without any subfolders.

## Additional requirements

On Linux and macOS, in order to get the GUI working, you will need to install tcl/tk 8.6 using
- On Linux, `yum install python-tkinter` or `apt install python3-tk` or whatever package manager you're using.
- On macOS, `brew install tcl-tk python-tk`

You can still use NPBackup in CLI mode without tcl/tk.

Keep in mind that linux built executables will only work on machines with equivalent or newer glibc version. You should always try to build NPBackup on the oldest working machine so your builds will work everywhere (I build on RHEL 7).



## Setup security

NPBackup uses AES-256 keys to encrypt it's configuration. You'll have to generate a new AES key.
Easiest way to achieve this is by launching the following:

Example:
- On Windows: `c:\Python310-64\python.exe -c "from cryptidy.symmetric_encryption import generate_key; print(generate_key())"`
- On Linux: `python3 -c "from cryptidy.symmetric_encryption import generate_key; print(generate_key())"`
- On macOS:
  - Intel: `/usr/local/bin/python3 -c "from cryptidy.symmetric_encryption import generate_key; print(generate_key())"`
  - ARM: `/opt/homebrew/bin/python3 -c "from cryptidy.symmetric_encryption import generate_key; print(generate_key())"`

The output of the above command should be something like `b'\xa1JP\r\xff\x11u>?V\x15\xa1\xfd\xaa&tD\xdd\xf9\xde\x07\x93\xd4\xdd\x87R\xd0eb\x10=/'`

Now copy that string into the file `npbackup/secret_keys.py`, which should look like:
```
AES_KEY = b'\xa1JP\r\xff\x11u>?V\x15\xa1\xfd\xaa&tD\xdd\xf9\xde\x07\x93\xd4\xdd\x87R\xd0eb\x10=/'
DEFAULT_BACKUP_ADMIN_PASSWORD = "MySuperSecretPassword123"
```

Note that we also changed the default backup admin password, which is used to see unencrypted configurations in the GUI.

## Actual compilation

Easiest way to compile NPBackup is to run the `bin/compile.py` script, which can build public (the executables on github) or private (your executables).

On Windows, run the following commands after adjusting the paths:
```
cd C:\NPBACKUP_GIT
SET PYTHONPATH=C:\NPBACKUP_GIT
C:\python310-64\python.exe bin\compile.py --audience private
```

On Linux, run the following commands after adjusting the paths:
```
cd /opt/npbackup
export PYTHONPATH=/opt/npbackup
python3 bin/compile.py --audience private
```

On macOS Intel, run the following commands after adjusting the paths:
```
cd ~/npbackup
export PYTHONPATH=~/npbackup
export TCL_LIBRARY=/usr/local/lib/tcl8.6
export TK_LIBRARY=/usr/local/lib/tcl8.6
/usr/local/bin/python3 bin/compile.py --audience private
```

On macOS ARM, run the following commands after adjusting the paths:
```
cd ~/npbackup
export PYTHONPATH=~/npbackup
export TCL_LIBRARY=/opt/homebrew/lib/tcl8.6
export TK_LIBRARY=/opt/homebrew/lib/tcl8.6
/opt/homebrew/bin/python3 bin/compile.py --audience private
```

If you need to compile for headless machines (arm/arm64), you can give the `--no-gui` parameter to `compile.py`.  

Target binaries will be found in `BUILDS/{audience}/{platform}/{arch}/npbackup.bin` where:
- audience is [private|public]
- platform is [linux|windows|darwin]
- arch is [x86|x64|arm|arm64]

## Cross compilation

On Linux, you might want to build for arm / aarch64, this can be achieved using a chrooted arm environment, than following the instructions all over again once chrooted.

Debian has `debootstrap` which allows to install a full Debian OS for another arch/platform.

Install an arm emulator and the necessary debian OS with `apt-get install qemu-user-static binfmt-support debootstrap`

Setup an armv71 (arm 32 bits) environment
```
debootstrap --arch=armhf stretch /chroots/stretch-armhf http://ftp.debian.org/debian/
cp /usr/bin/qemu-arm-static /chroots/stretch-armhf/bin
chroot /chroots/stretch-armhf qemu-arm-static /bin/bash
```

Setup an arm64 environment:
```
debootstrap --arch=arm64 stretch /chroots/stretch-arm64 http://ftp.debian.org/debian/
cp /usr/bin/qemu-aarch64-static /chroots/stretch-arm64/bin
chroot /chroots/stretch-arm64 qemu-aarch64-static /bin/bash
```

Once you're in the chroot, install and compile as for any other linux platform.

## Troubleshooting

Compiled without working GUI ? Launch the program with `--gui-status` in order to get more information.