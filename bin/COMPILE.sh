#!/usr/bin/env bash

# This is an example compiler script

cd /opt/npbackup

OLD_PYTHONPATH="$PYTHONPATH"
export PYTHONPATH=/opt/npbackup

/opt/npbackup/venv/bin/python bin/compile.py --audience all

export PYTHONPATH="$OLD_PYTHONPATH"