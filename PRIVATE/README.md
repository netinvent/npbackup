This folder may contain private overrides for NPBackup secrets.

1. You can create a file called _private_secret_keys.py to override default secret_keys.py file from npbackup
2. You may obfuscate the AES key at runtime by creating a file called `_private_obfuscation.py` that must contain
a function `obfuscation(bytes) -> bytes` like `aes_key_derivate = obfuscation(aes_key)` where aes_key_derivate must be 32 bytes.