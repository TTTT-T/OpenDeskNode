#!/usr/bin/env bash
# Unified hardware acceptance entry: starts C4/C3/C5 watchers, prompts for
# the one human action per case, reads watcher JSON, collects YES/NO, writes
# artifacts/phase-02c/hw-acceptance.json and .md.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x /tmp/eva-bridge-venv/bin/python ]]; then
    PYTHON_BIN=/tmp/eva-bridge-venv/bin/python
  elif [[ -x /tmp/esp32-phase-1d-venv/bin/python ]]; then
    PYTHON_BIN=/tmp/esp32-phase-1d-venv/bin/python
  else
    PYTHON_BIN=python3
  fi
fi

BRIDGE="${EVA_VOICE_BRIDGE:-http://127.0.0.1:8090}"
OUT_JSON="${ROOT_DIR}/artifacts/phase-02c/hw-acceptance.json"
HEAD="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
export PYTHON_BIN
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/esp32-phase-2c-pycache}"

if [[ "${1:-}" == "--prompts" ]]; then
  exec "$PYTHON_BIN" "$ROOT_DIR/scripts/phase-02c-accept.py" --print-prompts
fi

echo "OpenDeskNode hardware acceptance"
echo "HEAD=$HEAD"
echo "Bridge=$BRIDGE"
echo "This runner starts watchers itself. Do not restart ESP32 for C5."
echo

exec "$PYTHON_BIN" "$ROOT_DIR/scripts/phase-02c-accept.py" \
  --run --bridge "$BRIDGE" --out "$OUT_JSON" --head "$HEAD" "$@"
