#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo 'Install Python 3.11 or later from https://www.python.org/downloads/macos/ first.'
  exit 1
fi
sudo "$PYTHON_BIN" -I macos/manage.py install
read -r -p 'Press Enter to close.'
