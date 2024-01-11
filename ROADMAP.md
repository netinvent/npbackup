## What's planned ahead

### Daemon mode

Instead of relying on scheduled tasks, we could launch backup & housekeeping operations as deamon.
Caveats:
 - We need a windows service (nuitka commercial implements one)
 - We need to use apscheduler
 - We need a resurrect service config for systemd and windows service

### Web interface

Since runner can discuss in JSON mode, we could simply wrap it all in FastAPI
Caveats:
 - We'll need a web interface, with templates, whistles and belles
 - We'll probably need an executor (Celery ?) in order to not block threads

### KVM Backup plugin
Since we run cube backup, we could "bake in" full KVM support
Caveats:
 - We'll need to re-implement libvirt controller class for linux

### Hyper-V Backup plugin
That's another story. Creating snapshots and dumping VM is easy.
Shall we go that route since alot of good commercial products exist ?

### Key management

Possibility to add new keys to current repo, and delete old keys if more than one key present

### Provision server

Possibility to auto load repo settings for new instances from central server
We actually could improve upgrade_server to do so