#!/usr/bin/env bash

# This is an example compiler script

machine="$(uname -m)"

cd /opt/npbackup

OLD_PYTHONPATH="$PYTHONPATH"
export PYTHONPATH=/opt/npbackup

if [ "$(printf %.3s $machine)" = "arm" ] || [ "$machine" = "aarch64" ]; then
        opts=" --no-gui"
        echo "BUILDING WITHOUT GUI because arm detected"
else
        otps=""
        echo "BUILDING WITH GUI"
fi

/opt/npbackup/venv/bin/python bin/compile.py --audience all $opts

export PYTHONPATH="$OLD_PYTHONPATH"