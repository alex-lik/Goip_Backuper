#!/bin/bash
set -e

BASEDIR="$(dirname "$0")"
PROJECT_PATH="$(cd "$BASEDIR" && pwd)"

cd "$PROJECT_PATH"

if [ -f "venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

python3 main.py
