# NPF-SEC-00001: SECURITY-ADMIN-BACKUP-PASSWORD ONLY AVAILABLE ON PRIVATE COMPILED BUILDS

In gui.config we have a function that allows to show unencrypted values of the yaml config file
While this is practical, it should never be allowed on non compiled builds or with the default backup admin password

# NPF-SEC-00002: pre & post execution as well as password commands can be a security risk

All these commands are run with npbackup held privileges.
In order to avoid a potential attack, the config file has to be world readable only.

# NPF-SEC-00003: Avoid password command divulgation

Password command is encrypted in order to avoid it's divulgation if config file is world readable.
Password command is also not logged.

# NPF-SEC-00004: Client should never know the repo password

Partially covered with password_command feature.
We should have a central password server that holds repo passwords, so password is never actually stored in config.
This will prevent local backups, so we need to think of a better zero knowledge strategy here.

# NPF-SEC-00005: Viewer mode can bypass permissions

Since viewer mode requires actual knowledge of repo URI and repo password, there's no need to manage local permissions.
Viewer mode permissions are set to "restore".