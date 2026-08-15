#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$ROOT_DIR"
"$PYTHON_BIN" -m unittest discover -s tests -p 'test_*.py' -v
"$PYTHON_BIN" -c 'import json; from pathlib import Path; p=json.loads(Path("config/phase-01d0-provider-bakeoff.json").read_text()); assert p["symbols"] == ["600519", "000001", "300750", "688981"]; assert p["intraday_repeats"] >= 3; assert p["intraday_request_date"] == "2026-08-14"; assert set(p["providers"]) == {"akshare-eastmoney", "adata-sina", "adata-tencent", "easyquotation-sina", "easyquotation-tencent", "baidu-direct"}; print("phase-01d0 config: OK")'
