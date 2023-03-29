#!/usr/bin/env bash

# This is an example compiler script

machine="$(printf %.3s "$(uname -m)")"

cd /opt/npbackup

OLD_PYTHONPATH="$PYTHONPATH"
export PYTHONPATH=/opt/npbackup

if [ "$machine" = "arm" ]; then
        opts=" --no-gui"
        echo "BUILDING WITHOUT GUI because arm detected"
else
        otps=""
fi

/opt/npbackup/venv/bin/python bin/compile.py --audience all $opts

export PYTHONPATH="$OLD_PYTHONPATH"