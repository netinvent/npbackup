#!/usr/bin/env bash

# This is an example compiler script

cd /opt/npbackup
git pull || exit 1

OLD_PYTHONPATH="$PYTHONPATH"
export PYTHONPATH=/opt/npbackup

# For RHEL 7 based builds, we need to define path to locally built tcl8.6
[ -d /usr/local/lib/tcl8.6 ] && export LD_LIBRARY_PATH=/usr/local/lib

/opt/npbackup/venv/bin/python RESTIC_SOURCE_FILES/update_restic.py || exit 1

/opt/npbackup/venv/bin/python -m pip install --upgrade pip || exit 1
/opt/npbackup/venv/bin/python -m pip install pytest ||exit 1
# Uninstall prior versions of Freesimplegui if present so we get to use the git commit version
# which otherwise would not overwrite existing setup
/opt/npbackup/venv/bin/python -m pip uninstall -y freesimplegui
/opt/npbackup/venv/bin/python -m pip install --upgrade -r npbackup/requirements.txt || exit 1

/opt/npbackup/venv/bin/python -m pytest /opt/npbackup/tests || exit 1

/opt/npbackup/venv/bin/python bin/compile.py $@

export PYTHONPATH="$OLD_PYTHONPATH"