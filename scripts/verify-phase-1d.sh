#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PYTHON_CACHE="${PYTHONPYCACHEPREFIX:-/tmp/esp32-phase-1d-pycache}"

cd "$ROOT_DIR"
PYTHONPYCACHEPREFIX="$PYTHON_CACHE" "$PYTHON_BIN" -m unittest discover -s tests -p 'test_*.py' -v
PYTHONPYCACHEPREFIX="$PYTHON_CACHE" "$PYTHON_BIN" -m py_compile \
  gateway/config.py gateway/models.py gateway/repository.py gateway/calendar.py \
  gateway/providers.py gateway/service.py gateway/schemas.py gateway/logging_config.py \
  gateway/app.py scripts/stock-provider-smoke.py
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

compose = Path("compose.yaml").read_text()
dockerfile = Path("Dockerfile").read_text()
assert "restart: unless-stopped" in compose
assert "json-file" in compose and 'max-file: "3"' in compose
assert "HEALTHCHECK" in dockerfile and "USER gateway" in dockerfile
assert Path("requirements.txt").exists()
assert Path("gateway/web/index.html").read_text().find("明确保存") >= 0
print("phase-1d deployment/static checks: OK")
PY
git diff --check
echo "phase-1d offline verification: OK"
