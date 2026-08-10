#!/usr/bin/env bash
# One command from a fresh clone: makes a virtualenv if needed, installs numpy,
# starts the server and opens the page.
#
#   ./run.sh                # start it on the handles in .env, if any
#   ./run.sh your_handle    # and warm that handle's contests in the background
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
command -v "$PY" >/dev/null || { echo "python3 not found"; exit 1; }

if [ ! -d .venv ]; then
  echo "setting up (first run only)…"
  "$PY" -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
fi

exec ./.venv/bin/python -m vrating "$@"
