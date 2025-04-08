## Compatibility for various platforms

### Linux

We need Python 3.7 to compile on RHEL 7, which uses glibc 2.17
These builds will be "legacy" builds, 64 bit builds are sufficient.

### Windows

We need Python 3.7 to compile on Windows 7 / Server 2008 R2
These builds will be "legacy" builds.

Also, last restic version to run on Windows 7 is 0.16.2, see https://github.com/restic/restic/issues/4636 (basically go1.21 is not windows 7 compatible anymore)
So we actually need to compile restic ourselves with go1.20.12 which is done via restic_legacy_build.cmd script

