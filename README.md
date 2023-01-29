[![License](https://img.shields.io/badge/license-GPLv3-blu.svg)](https://opensource.org/licenses/GPL-3.0)
[![Percentage of issues still open](http://isitmaintained.com/badge/open/netinvent/npbackup.svg)](http://isitmaintained.com/project/netinvent/npbackup "Percentage of issues still open")
[![GitHub Release](https://img.shields.io/github/release/netinvent/npbackup.svg?label=Latest)](https://github.com/netinvent/npbackup/releases/latest)


# NPBackup

A one fits all backup solution that solves modern problems with modern solutions

## Features

- Data deduplication and fast zstd compression
- Client side data encryption
- Wide storage backend support
  - local files
  - SFTP
  - High performance HTTP REST server
  - Amazon S3/Minio/Wasabi
  - Blackblaze B2
  - Microsoft Azure Blob Storage
  - Google Cloud Storage
  - OpenStack Swift
  - Alibaba Cloud (Aliyun) Object Storage System (OSS)
- Full CLI interface for scheduled task usage
  - Checks for recent backups before launching a backup
- Optional end user GUI
  - Backup content view and restore
  - Configuration interface
  - Internationalization support (en, fr as of jan 2023)
- Performance
  - Backup process and IO priority settings
  - Upload / download speed limits
  - Concurrency settings
- Comes with complete exclusion lists for Linux and Windows files and folders
- First class prometheus support
  - Grafana dashboard included
  - node_exporter file collector support
  - Optional push gateway metrics uploading
- First class Windows support
  - VSS snapshots
  - Cloud file exclusions (reparse points)
  - Windows pre-built executables
  - Windows installer
- Additional security
  - repository uri / password and http metrics identification is encrypted
- yaml file configuration (or gui configuration)

## About

So, a new backup solution out of nowhere, packed with too much features for it's own good ? Not really !

NPBackup relies on the well known [restic](https://restic.net) backup program, which has been battle proven for years.
While restic is a fanstastic program, NPBackup tries to complete restic in order to offer a broader user experience.

## Quickstart

On Windows, use `NPBackupInstaller.exe` to install NPBackup into program files.
On Linux, just copy `npbackup` to `/usr/local/bin` or use `pip install npbackup`

Copy the example config from model `examples/npbackup.conf.dist` into the directory where npbackup is installed.

You can adjust the parameters directly in the file, or via a config GUI by launching `npbackup --config-file=npbackup.conf --config-gui`

Once configured, you can launch manual backups via `npbackup --backup`. Those can be scheduled.
Windows schedule is created automatically by the installer program. On Linux, you'll have to create a cronjob or a systemd timer.

Since NPBackup is configured to only proceed with backups when no recent backups are detected, you should consider scheduling npbackup executions quite often.
The default schedule should be somewhere around 15 minutes.

You can use `npbackup --list` or the GUI to list backups.

The GUI allows an end user to check current backups & restore files.rom backups:

The YAML configuration file encrypts sensible data so the end user doesn't have to know repository URI or password.

### The difficulty of laptop backups

As a matter of fact, laptop backups are the hardest. No one can predict when a laptop is on, and if it has access to internet.
Creating a backup strategy in those cases isn't a simple task.

NPBackup solves this by checking every 15 minutes if a backup newer than 24h exists.
If so, nothing is done. In the case no recent backup exists, a backup is immediately launched.
OF course, both time options are configurable.
In order to avoid sluggish user experience while backing up, process and io priority can be lowered.
Once done, NPBackup can send backup results in Prometheus format directly to a push gateway, for prometheus to catch them.

### A good server backup solution

Server backups can be achieved by setting up a scheduled task / cron job.

Of course, since NPBackup supports pre-exec and post-exec commands, it can be used to backup various services like virtual hosts or databases where snapshot/dump operations are required.
When run on a server, prometheus support can be shifted from a push gateway to a file, which will be picked up by node_exporter file collector.

### End user expericence

While admin user experience is important, NPBackup also offers a GUI for end user experience, allowing to list all backup contents, navigate and restore files, without the need of an admin. The end user can also check if they have a recent backup completed, and launch backups manually if needed.

### Security

NPBackup inherits all security measures of restic (AES-256 client side encryption including metadata), append only mode REST server backend.

On top of those, NPBackup itself encrypts sensible information like the repo uri and password, as well as the metrics http username and password.
This ensures that end users can restore data without the need to know any password, without compromising a secret. Note that in order to use this function, one needs to use the compiled version of NPBackup, so AES-256 keys are never exposed. Internally, NPBackup never directly uses the AES-256 key, so even a memory dump won't be enough to get the key.

## Compilation

In order to fully protect the AES key that is needed to support NPBackup, one can compile the program with Nuitka.
Compiling needs restic binary for the target platform in `RESTIC_SOURCE_FILES` folder, files must be named `restic_{version}_{platform}_{arch}[.extension]` like provided by restic.net or [github](github.com/restic/restic)
Compile options are available in `compile.py`. Nevertheless, you should probably go for the official binaries.
Also, We maintain a special 32 bit binary for Windows 7 which allows to backup those old machines until they get replaced.

## Smart shield, antivirus and reputation

Official binaries for Windows provided by NetInvent are signed with a certificate, allowing to gain trust and reputation in antivirus analysis.
Also, official binaries are compiled using Nuitka Commercial grade, which is more secure in storing secrets.

## Misc

NPBackup supports internationalization and automatically detects system's locale.
Still, locale can be overrided via an environment variable, eg on Linux:
```
export NPBACKUP_LOCALE=en
```
On Windows:
```
set NPBACKUP_LOCALE=en
```
