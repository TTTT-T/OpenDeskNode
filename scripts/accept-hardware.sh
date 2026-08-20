#!/usr/bin/env bash
# Unified hardware acceptance entry for Phase 2C C4/C3/C5 + stock regression.
# Auto-checks what a machine can; prompts for the one human action per case.
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
STOCK="${STOCK_GATEWAY:-http://terrencenas.local:8000/healthz}"
OUT_DIR="${ROOT_DIR}/artifacts/phase-02c"
OUT_JSON="${OUT_DIR}/hw-acceptance.json"
HEAD="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
mkdir -p "$OUT_DIR"

echo "OpenDeskNode hardware acceptance"
echo "HEAD=$HEAD"
echo "Bridge=$BRIDGE"
echo

if [[ "${1:-}" == "--prompts" ]]; then
  PYTHONPYCACHEPREFIX=/tmp/esp32-phase-2c-pycache "$PYTHON_BIN" \
    "$ROOT_DIR/scripts/phase-02c-accept.py" --print-prompts
  exit 0
fi

echo "== preflight =="
if ! PYTHONPYCACHEPREFIX=/tmp/esp32-phase-2c-pycache "$PYTHON_BIN" - <<PY
import json, urllib.request, sys
url = "$BRIDGE/healthz"
try:
    body = json.loads(urllib.request.urlopen(url, timeout=3).read().decode())
except Exception as exc:
    print("bridge health FAIL:", exc)
    sys.exit(1)
print("bridge:", json.dumps(body, ensure_ascii=False))
if not body.get("ok"):
    sys.exit(1)
PY
then
  echo "Bridge is not healthy. Start it with scripts/run-bridge-local.sh" >&2
  exit 1
fi

echo
echo "Stock Gateway (non-blocking if unreachable):"
curl -fsS --max-time 3 "$STOCK" || echo "stock health unreachable (record during live test)"
echo
echo "Cases: C4_MULTI_TURN C3_LOCAL_STOP C5_BRIDGE_RECOVERY C5_GATEWAY_RECOVERY C5_WIFI_RECOVERY STOCK_REGRESSION"
echo "Human actions (one case at a time):"
PYTHONPYCACHEPREFIX=/tmp/esp32-phase-2c-pycache "$PYTHON_BIN" \
  "$ROOT_DIR/scripts/phase-02c-accept.py" --print-prompts
echo
echo "Watchers:"
echo "  python scripts/phase-02c-c4-live.py --bridge $BRIDGE"
echo "  python scripts/phase-02c-c3-live.py --bridge $BRIDGE"
echo "  python scripts/phase-02c-c5-live.py --bridge $BRIDGE --case bridge"
echo "  python scripts/phase-02c-c5-live.py --bridge $BRIDGE --case gateway"
echo "  python scripts/phase-02c-c5-live.py --bridge $BRIDGE --case wifi"
echo
echo "Collect ESP32 serial alongside each watcher. Do not restart ESP32 for C5."
echo "After each watcher exits, keep the JSON under artifacts/phase-02c/."
echo

PYTHONPYCACHEPREFIX=/tmp/esp32-phase-2c-pycache "$PYTHON_BIN" \
  "$ROOT_DIR/scripts/phase-02c-accept.py" --bridge "$BRIDGE" --out "$OUT_JSON" --head "$HEAD"
echo "Wrote $OUT_JSON and ${OUT_JSON%.json}.md"
echo "Fill PASS/FAIL from watcher JSON + speaker/stock human answers; do not mark untested items PASS."
