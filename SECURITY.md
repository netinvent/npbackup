# Retired since v2.3.0, replaced by NPF-SEC-00007
# NPF-SEC-00001: SECURITY-ADMIN-BACKUP-PASSWORD ONLY AVAILABLE ON PRIVATE COMPILED BUILDS

In gui.config we have a function that allows to show unencrypted values of the yaml config file
While this is practical, it should never be allowed on non compiled builds or with the default backup admin password

# NPF-SEC-00002: pre & post execution as well as password commands can be a security risk

All these commands are run with npbackup held privileges.
In order to avoid a potential attack, the config file has to be world readable only.
We need to document this, and perhaps add a line in installer script

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

# NPF-SEC-00006: Never inject permissions if some are already present

Since v3.0.0, we insert permissions directly into the encrypted repo URI.
Hence, update permissions should only happen in two cases:
- CLI: Recreate repo_uri entry and add permission field from YAML file
- GUI: Enter permission password to update permissions

# NPF-SEC-00007: Encrypted data needs to be protected

Since encryption is symmetric, we need to protect our sensible data.
Best ways:
- Compile with alternative aes-key
- Use --aes-key with alternative aes-key which is protected by system

# NPF-SEC-00008: Don't show manager password / sensible data with --show-config

Since v3.0.0, we have config inheritance. Showing the actual config helps diag issues, but we need to be careful not
to show actual secrets.

# NPF-SEC-00009: Manager password in CLI mode

When using `--show-config` or right click `show unecrypted`, we should only show unencrypted config if password is set.  
Envivironmnt variable `NPBACKUP_MANAGER_PASSWORD` will be read to verify access.
Also, when wrong password is entered, we should wait in order to reduce brute force attacks.

# NPF-SEC-00010: Date attacks

When using retention policies, we need to make sure that current system date is good, in order to avoid wrong retention deletions.  
When set, an external NTP server is used to get the offset. If offset is high enough (10 min), we avoid executing the retention policies.