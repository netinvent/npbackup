This folder may contain overrides for NPBackup secrets.
If these files exist, NPBackup will be compiled as "private build".

Overrides are used by default if found at execution time.

In order to use them at compile time, one needs to run `compile.py --audience private`

1. You can create a file called _private_secret_keys.py to override default secret_keys.py file from npbackup
2. You may obfuscate the AES key at runtime by creating a file called `_private_obfuscation.py` that must contain
a function `obfuscation(bytes) -> bytes` like `aes_key_derivate = obfuscation(aes_key)` where aes_key_derivate must be 32 bytes.
3. You can create a distribution default configuration file here called _private.npbackup.conf.dist that will be bundled with NPBackupInstaller if present