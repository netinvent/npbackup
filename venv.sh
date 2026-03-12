#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
export PYTHNOPATH="$SCRIPT_DIR:$PYTHONPATH"
venv/bin/activate