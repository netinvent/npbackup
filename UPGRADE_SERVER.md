## Setup upgrade server

Clone git repository into a directory and create a venv environment

```
cd /opt
git clone https://github.com/netinvnet/npbackup
cd npbackup
python -m venv venv
```

Install requirements
```
venv/bin/python -m pip install -r upgrade_server/requirements.txt
```

## Configuration file

Create a configuration file ie `/etc/npbackup_upgrade_server.conf` with the following content

```
# NPBackup v3 upgrade server
http_server:
  # These are the passwords that need to be set in the upgrade settings of NPBackup client
  username: npbackup_upgrader
  password: SomeSuperSecurePassword
  listen: 0.0.0.0
  port: 8080
upgrades:
  data_root: /opt/upgrade_server_root
  statistics_file: /opt/upgrade_server_root/stats.csv
```

You should also create the upgrade server root path
```
mkdir /opt/upgrade_server_root
```

## Provisioning files

Basically, upgrade_server serves compressed versions of NPBackup, than can directly be downloaded from git releases. Those compressed files will contain a single directory, like `npbackup-gui` or `npbackup-cli` which contain all the files (.zip and .tar.gz files are supported)


When uploading new versions, you need to create a file in the data root called `VERSION` which should contain current NPBackup version, example `3.0.1`  
This way, every NPBackup client will download this file and compare with it's current version in order to verify if an upgrade is needed.

If an upgrade is needed, NPBackup will try to download it from `/download/{platform}/{arch}/{build_type}`  

Current platforms are: `windows`, `linux`
Current arches are `x64`, `x64-legacy`, `x86-legacy`, `arm-legacy` and `arm64-legacy`.

Basically, if you want to update the current NPBackup client, you should have copy your new npbackup archives to the according locations 
```
/opt/upgrade_server_root/linux/x64/npbackup-cli.tar.gz
/opt/upgrade_server_root/windows/x64/npbackup-gui.zip
```


## Run server

You can run server with
```
venv/bin/python upgrade_server/upgrade_server.py -c /etc/npbackup_upgrade_server.conf
```

## Create a service

You can create a systemd service for the upgrade server as `/etc/systemd/system/npbackup_upgrade_server.service`, see the systemd file in the example directory.

## Statistics

You can find the CSV file containing statistics, which contain:

- Operation: check_version|get_file_info|download_upgrade
- IP Address
- Machine ID as defined in client
- NPBackup version
- Machine Group as defined in client
- Platform
- Arch
