#!/usr/bin/env bash
# Run the Field-3D GUI from a local virtualenv.
# Creates and populates the venv automatically on first run.
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"

if [[ ! -d "$VENV" ]]; then
    echo "[field3d] Creating virtualenv…"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip -q
    "$VENV/bin/pip" install -r requirements.txt -q
    echo "[field3d] Dependencies installed."
fi

exec "$VENV/bin/python" main.py "$@"
