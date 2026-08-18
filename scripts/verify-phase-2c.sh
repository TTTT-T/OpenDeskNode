#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x /tmp/esp32-phase-1d-venv/bin/python ]]; then
    PYTHON_BIN=/tmp/esp32-phase-1d-venv/bin/python
  else
    PYTHON_BIN=python3
  fi
fi
PYTHON_CACHE="${PYTHONPYCACHEPREFIX:-/tmp/esp32-phase-2c-pycache}"

cd "$ROOT_DIR"
PYTHONPYCACHEPREFIX="$PYTHON_CACHE" "$PYTHON_BIN" -m unittest \
  tests.test_bridge_protocol tests.test_bridge_audio tests.test_bridge_c0 -v
PYTHONPYCACHEPREFIX="$PYTHON_CACHE" "$PYTHON_BIN" -m py_compile \
  bridge/__init__.py bridge/protocol.py bridge/audio.py bridge/config.py \
  bridge/talk.py bridge/session.py bridge/app.py bridge/__main__.py
git diff --check
echo "phase-2c C0 host verification: OK"
