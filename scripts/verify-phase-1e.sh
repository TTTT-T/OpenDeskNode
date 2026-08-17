#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stock_dir="$repo_root/firmware/product/components/stock"
cjson_dir="$repo_root/firmware/product/managed_components/espressif__cjson/cJSON"
python_bin="${PYTHON_BIN:-python3}"

required_files=(
  "$stock_dir/Kconfig"
  "$stock_dir/idf_component.yml"
  "$stock_dir/include/stock_gateway_client.h"
  "$stock_dir/include/stock_gateway_parser.h"
  "$stock_dir/stock_gateway_client.c"
  "$stock_dir/stock_gateway_parser.c"
  "$stock_dir/test/test_stock_gateway_parser.c"
)
for file in "${required_files[@]}"; do
  [[ -f "$file" ]] || { echo "Missing Phase 1E file: $file" >&2; exit 1; }
done
[[ -f "$cjson_dir/cJSON.c" ]] || {
  echo "Managed cJSON is missing; run bash scripts/build-clean-firmware.sh first" >&2
  exit 1
}

# Production producer and bounded LAN-only contract.
rg -q 'stock_gateway_fetch' "$stock_dir/stock_service.c"
rg -q 'network_is_connected' "$stock_dir/stock_service.c"
rg -q 'STOCK_STALE_AFTER_MS = 5 \* 60 \* 1000' "$stock_dir/stock_service.c"
rg -q 'intraday_samples=%u' "$stock_dir/stock_gateway_client.c"
rg -q 'MAX_RESPONSE_BYTES = 128U \* 1024U' "$stock_dir/stock_gateway_client.c"
rg -q 'CONFIG_STOCK_GATEWAY_BASE_URL' "$stock_dir/stock_gateway_client.c"
if rg -q 'stock_mock' "$stock_dir/stock_service.c"; then
  echo "Production stock service must not use the deterministic mock" >&2
  exit 1
fi
if rg -n 'finance\.pae\.baidu\.com|qt\.gtimg\.cn|api\.tenclass\.net|xiaozhi\.me' \
  "$repo_root/firmware/product" --glob '*.[ch]' --glob Kconfig; then
  echo "Firmware must not contain provider or Xiaozhi cloud endpoints" >&2
  exit 1
fi

# Gateway keeps its full default response and only bounds explicitly requested
# firmware projections.
rg -q 'intraday_samples: Optional\[int\] = Query\(None, ge=2, le=64\)' \
  "$repo_root/gateway/app.py"
rg -q 'downsample_sequence' "$repo_root/gateway/service.py"
"$python_bin" -m unittest tests.test_gateway_refresh -v

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

# Accepted Phase 1C pure model/mock regression.
cc -std=c99 -Wall -Werror -Wextra -I"$stock_dir/include" \
  "$stock_dir/test/test_stock_host.c" "$stock_dir/stock_model.c" \
  "$stock_dir/stock_mock.c" -o "$work_dir/test_stock_host"
"$work_dir/test_stock_host"

# Strict schema-v1 parser regression against the pinned cJSON dependency.
cc -std=c99 -Wall -Werror -Wextra -I"$stock_dir/include" -I"$cjson_dir" \
  "$stock_dir/test/test_stock_gateway_parser.c" "$stock_dir/stock_model.c" \
  "$stock_dir/stock_gateway_parser.c" "$cjson_dir/cJSON.c" -lm \
  -o "$work_dir/test_stock_gateway_parser"
"$work_dir/test_stock_gateway_parser"

# The generated font must cover the complete declared dynamic-name range.
"$python_bin" - "$stock_dir" <<'PY'
import re
import sys

stock_dir = sys.argv[1]
font = open(f"{stock_dir}/fonts/stock_font_cjk_24.c", encoding="utf-8").read()
covered = {
    int(codepoint, 16)
    for codepoint in re.findall(r'/\* U\+([0-9A-Fa-f]{4,6}) "[^"]+" \*/', font)
}

required_range = set(range(0x4E00, 0x9FF0)) | {0x25B2, 0x25BC}
missing_range = required_range - covered
if missing_range:
    raise SystemExit(
        f"Font missing {len(missing_range)} declared code points; "
        f"first={hex(min(missing_range))}"
    )

sources = [
    f"{stock_dir}/stock_model.c",
    f"{stock_dir}/stock_mock.c",
    f"{stock_dir}/test/test_stock_gateway_parser.c",
]
needed = set()
for source in sources:
    text = open(source, encoding="utf-8").read()
    needed.update(ch for ch in text if 0x4E00 <= ord(ch) <= 0x9FFF)
    needed.update(ch for ch in text if ch in "▲▼")
missing = {ord(ch) for ch in needed} - covered
if missing:
    raise SystemExit(f"Font missing live UI glyphs: {[hex(cp) for cp in sorted(missing)]}")
print(f"PHASE1E_FONT_GLYPH_COVERAGE_OK ({len(required_range)} declared code points)")
PY

PYTHONPYCACHEPREFIX=/tmp/esp32-phase-1e-pycache "$python_bin" -m py_compile \
  "$repo_root/gateway/app.py" "$repo_root/gateway/service.py"
git -C "$repo_root" diff --check
echo "PHASE_1E_OFFLINE_CHECKS_OK"
