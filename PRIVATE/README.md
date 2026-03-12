This folder may contain overrides for NPBackup secrets and customization
If these files exist, NPBackup can be launched as private build.

In order to create a private build:

1. Create a directory in PRIVATE which will be named after your private build (audience) and copy files from example directory

Directory structure

PRIVATE
  |
  example
    |
    _customization.py
    _obfuscation.py
    _private_secret_keys.py
  your_build
    |
    _customization.py
    _obfuscation.py
    _private_secret_keys.py
  audience.py

2. Update the KEYWORD variable in `_obfuscation.py` to whatever you want, or replace the `obfuscation.py` function
3. Update the AES_KEY in `_private_secret_keys.py` according to the instructions you'll find in that file
4. Optionally update `_customization.py`
5. Copy `audience.dist.py` file to `audience.py` and update both `CURRENT_AUDIENCE` and `AUDIENCES` variables to include your audience name


In order to use them at compile time, one needs to run `compile.py --audience {audience_name}`
In our above example: `compile.py --audience your_build`

