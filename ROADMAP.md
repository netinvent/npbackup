## What's planned / considered post v3

### Daemon mode (planned)
Instead of relying on scheduled tasks, we could launch backup & housekeeping operations as daemon.
Caveats:
 - We need a windows service (nuitka commercial implements one)
 - We need to use apscheduler (wait for v4)
 - We need a resurrect service config for systemd and windows service
 - Upgrade checks will be done via service

### Fallback (considered)
 - Repository uri should allow to have a fallback server
 - Prometheus support should have a push gateway fallback server option.
 - Upgrade server should have a fallback server

### Web interface (planned)
Since runner can discuss in JSON mode, we could simply wrap it all in FastAPI
Caveats:
 - We'll need a web interface, with templates, whistles and bells
 - We'll probably need an executor (Celery ?) in order to not block threads

### KVM Backup plugin (planned, already exists as external script)
Since we run cube backup, we could "bake in" full KVM support
Caveats:
 - We'll need to re-implement libvirt controller class for linux

### Proxmox Backup plugin
Assumption: Since we can backup KVM, we can also backup Proxmox ?
Caveats:
 - vzdump produces a specific archive format (using lzop) which would need to be decompressed to allow good deduplication (https://git.proxmox.com/?p=pve-qemu.git;a=blob;f=vma_spec.txt; )
 - vzdump vanilla files can be deduped with block dedup tech, but badly (test done using two vzdump backups, one after another to zfs 2.3.0 with fast dedup and a 160GB ddt table limit):
     - 1M recordsize = 0%
     - 128K recordsize = 1%
     - 64K recordsize = 19%
     - 32K recordsize = 65%
     - 16k recordsize = 79%
  - So basically block dedup is bad for vzdump files. restic uses 4M pack sizes minimum. Tests have shown restic dedup algorithm to dedup 0% of data properly in the same file (rsync tests have shown about 40% file differences using patch method)
  - We need to "open" the vzdump files in order to store them properly (with vma utility), but present them to proxmox as vzdump files. We could check if vzdump can produce proper tar files with --stdout, or we could also just not use vzdump but rather do it the good old way of backing up qcow2 + xml files via qm
  
### SQL Backups
That's a pre-script job ;)
Perhaps, provide pre-scripts for major SQL engines
Perhaps, provide an alternative dump | npbackup-cli syntax.
In the latter case, shell (bash, zsh, ksh) would need `shopt -o pipefail`, and minimum backup size set.
The pipefail will not be given to npbackup-cli, so we'd need to wrap everything into a script, which defeats the prometheus metrics.

### Key management
Possibility to add new keys to current repo, and delete old keys if more than one key present

### Provision server (planned)
Possibility to auto load repo settings for new instances from central server
We actually could improve upgrade_server to do so

### Hyper-V Backup plugin
That's another story. Creating snapshots and dumping VM is easy
Shall we go that route since a lot of good commercial products exist ? Probably not

### Full disk cloning
Out of scope of NPBackup. There are plenty of good tools out there, designed for that job

### Rust rewrite
That would be my "dream" project in order to learn a new language in an existing usecase.
But this would need massive sponsoring as I couldn't get the non-paid time to do so.

### More backends support
Rustic is a current alternative backend candidate I tested. Might happen if enough traction.

### Branding manager
We might want to put all files into `resources` directory and have `customization.py` files generated from there.

### New installer
We might need to code an installer script for Linux, and perhaps a NSIS installer for Windows.

### Security
Check that the config file is not world writable, so nobody can inject pre/post commands