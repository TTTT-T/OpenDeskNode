#!/usr/bin/env bash
# Phase 1C static + host validation: stock display skeleton.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
product_dir="$repo_root/firmware/product"
stock_dir="$product_dir/components/stock"

required_files=(
  "$stock_dir/CMakeLists.txt"
  "$stock_dir/include/stock_model.h"
  "$stock_dir/include/stock_mock.h"
  "$stock_dir/include/stock_view.h"
  "$stock_dir/include/stock_service.h"
  "$stock_dir/stock_model.c"
  "$stock_dir/stock_mock.c"
  "$stock_dir/stock_view.c"
  "$stock_dir/stock_service.c"
  "$stock_dir/fonts/stock_font_cjk_24.c"
  "$stock_dir/fonts/stock_font_num_48.c"
  "$stock_dir/fonts/README.md"
  "$stock_dir/test/test_stock_host.c"
)
for file in "${required_files[@]}"; do
  [[ -f "$file" ]] || { echo "Missing required stock component file: $file" >&2; exit 1; }
done

# --- Model shape: exactly 4 quotes, fixed-point, states, session, freshness. ---
rg -q '#define STOCK_COUNT 4' "$stock_dir/include/stock_model.h"
rg -q 'STOCK_MARKET_NORMAL' "$stock_dir/include/stock_model.h"
rg -q 'STOCK_MARKET_LIMIT_UP' "$stock_dir/include/stock_model.h"
rg -q 'STOCK_MARKET_LIMIT_DOWN' "$stock_dir/include/stock_model.h"
rg -q 'STOCK_MARKET_SUSPENDED' "$stock_dir/include/stock_model.h"
rg -q 'stock_session_t session;' "$stock_dir/include/stock_model.h"
rg -q 'int64_t last_success_update_ms;' "$stock_dir/include/stock_model.h"
rg -q 'stock_price_t prev_close;' "$stock_dir/include/stock_model.h"
rg -q 'stock_price_t intraday\[STOCK_INTRADAY_SAMPLES\];' "$stock_dir/include/stock_model.h"
rg -Fq 'typedef int32_t stock_price_t;' "$stock_dir/include/stock_model.h"

# --- Exact up/down semantics in a pure, host-testable formatter. ---
rg -Fq 'snprintf(buffer, size, "\xe2\x96\xb2 +%ld.%02ld%%", whole, frac);' "$stock_dir/stock_model.c"
rg -Fq 'snprintf(buffer, size, "\xe2\x96\xbc -%ld.%02ld%%", whole, frac);' "$stock_dir/stock_model.c"
rg -Fq 'snprintf(buffer, size, "0.00%%");' "$stock_dir/stock_model.c"
rg -q 'stock_quote_change_pct_x100' "$stock_dir/stock_model.c"
rg -q 'void stock_format_change_percent_with_state' "$stock_dir/stock_model.c"

# --- View: every panel always shows name, price, change amount, change
# --- percent; special states only prefix the percent line, never replace data. ---
rg -q 'stock_format_change_percent_with_state' "$stock_dir/stock_view.c"
rg -Fq 'stock_format_change_amount(amount, sizeof(amount), quote);' "$stock_dir/stock_view.c"
rg -Fq 'lv_label_set_text(view->status_label, amount);' "$stock_dir/stock_view.c"
rg -Fq 'lv_label_set_text(view->name_label, quote->name);' "$stock_dir/stock_view.c"
rg -Fq 'lv_label_set_text(view->price_label, price);' "$stock_dir/stock_view.c"
if rg -qn 'stock_market_state_text' "$stock_dir/stock_view.c"; then
  echo "View must keep the change amount on status_label; state text belongs to the percent line" >&2
  exit 1
fi

# --- Production startup is task-owned: the stock service task (explicit
# --- stack budget) creates the view, resets the mock, and renders the first
# --- update before its first ~10 second delay. ---
python3 - "$stock_dir/stock_service.c" <<'PY'
import re
import sys

src = open(sys.argv[1], encoding="utf-8").read()


def func_body(name):
    header = re.search(r'\b' + name + r'\s*\([^)]*\)\s*\{', src)
    if header is None:
        print(f"stock_service.c: missing function {name}()", file=sys.stderr)
        sys.exit(1)
    depth = 0
    start = header.end() - 1
    for i in range(start, len(src)):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start + 1:i]
    print(f"stock_service.c: unbalanced braces in {name}()", file=sys.stderr)
    sys.exit(1)


task = func_body("stock_service_task")
cycle = func_body("run_update_cycle")
start = func_body("stock_service_start")

if "stock_view_update(stock_mock_snapshot())" not in cycle:
    print("run_update_cycle must refresh the view from the mock snapshot", file=sys.stderr)
    sys.exit(1)

# Startup runs inside the service task: create the view, reset the
# deterministic mock, and render the first update before the first delay.
for token in ("stock_view_create", "stock_mock_reset()", "run_update_cycle",
              "vTaskDelay", "stock_mock_tick"):
    if token not in task:
        print(f"stock_service_task must contain {token}", file=sys.stderr)
        sys.exit(1)
create_at = task.index("stock_view_create")
reset_at = task.index("stock_mock_reset()")
update_at = task.index("run_update_cycle")
delay_at = task.index("vTaskDelay")
if not create_at < reset_at < update_at < delay_at:
    print("stock_service_task must create the view, reset the mock, and render once before its first delay", file=sys.stderr)
    sys.exit(1)
if delay_at > task.index("stock_mock_tick"):
    print("stock_service_task must delay before its first tick", file=sys.stderr)
    sys.exit(1)

# stock_service_start only spawns the budgeted task; initialization must not
# run in the caller's (main task) context.
if "s_service_task != NULL" not in start:
    print("stock_service_start must stay idempotent", file=sys.stderr)
    sys.exit(1)
if "xTaskCreate" not in start:
    print("stock_service_start must spawn the refresh task", file=sys.stderr)
    sys.exit(1)
if "STOCK_SERVICE_STACK_BYTES" not in start:
    print("stock_service_start must pass the explicit stack budget to xTaskCreate", file=sys.stderr)
    sys.exit(1)
for token in ("stock_view_create", "stock_mock_reset", "run_update_cycle", "vTaskDelay"):
    if token in start:
        print(f"stock_service_start must not run {token}; startup belongs to the service task", file=sys.stderr)
        sys.exit(1)
print("STOCK_SERVICE_TASK_OWNED_STARTUP_OK")
PY

# --- app_main only starts the service; it must not build or refresh the
# --- stock view in the main task. ---
rg -q 'stock_service_start\(\)' "$product_dir/main/app_main.c"
if rg -qn 'stock_view_create|stock_view_update|stock_view\.h' "$product_dir/main/app_main.c"; then
  echo "app_main must only start the stock service; view startup belongs to the service task" >&2
  exit 1
fi

# --- Mock: deterministic table, ~10s tick, no randomness. ---
rg -q '#define STOCK_MOCK_CYCLE_TICKS 24' "$stock_dir/include/stock_mock.h"
rg -q '#define STOCK_MOCK_TICK_INTERVAL_MS 10000' "$stock_dir/include/stock_mock.h"
if rg -qn 'rand\(|srand\(|esp_random|esp_http_client|esp_wifi|http://' "$stock_dir"/stock_model.c "$stock_dir"/stock_mock.c; then
  echo "Stock model/mock must stay deterministic and network-free" >&2
  exit 1
fi

# --- View: 2x2 equal panels, sparkline, dashed previous-close baseline. ---
rg -q '#define STOCK_VIEW_PANEL_WIDTH 200' "$stock_dir/stock_view.c"
rg -q '#define STOCK_VIEW_PANEL_HEIGHT 150' "$stock_dir/stock_view.c"
rg -q 'stock_font_num_48' "$stock_dir/stock_view.c"
rg -q 'stock_font_cjk_24' "$stock_dir/stock_view.c"
rg -q 'lv_line_set_points' "$stock_dir/stock_view.c"
rg -q 'line_dash_width' "$stock_dir/stock_view.c"
rg -q 'line_dash_gap' "$stock_dir/stock_view.c"

# --- Out-of-scope product behavior must not appear in the stock component. ---
if rg -qn '持仓|盈亏|提醒|详情|alert|holdings|stock_code|detail' "$stock_dir" --glob '!fonts/*'; then
  echo "Stock component contains out-of-scope product behavior" >&2
  exit 1
fi

# --- No Xiaozhi / cloud imports in product sources (same rule as phase 1B.1). ---
if rg -n --glob '*.[ch]' --glob 'CMakeLists.txt' --glob 'idf_component.yml' \
  '#include[[:space:]]+[<"][^>"]*(xiaozhi|application\.h|wifi_board\.h)|add_subdirectory\([^)]*xiaozhi|EXTRA_COMPONENT_DIRS[^\n]*xiaozhi' \
  "$product_dir"; then
  echo "Product source imports the frozen reference" >&2
  exit 1
fi
if rg -n --glob '*.[ch]' --glob 'CMakeLists.txt' --glob 'idf_component.yml' \
  'api\.tenclass\.net|xiaozhi\.me' "$product_dir"; then
  echo "Product source contains a forbidden reference-cloud host" >&2
  exit 1
fi

# --- Font provenance is documented and reproducible. ---
rg -q 'lv_font_conv@1\.5\.3' "$stock_dir/fonts/README.md"
rg -Fq 'SourceHanSansSC-Normal.otf' "$stock_dir/fonts/README.md"
rg -q 'SIL Open Font License' "$stock_dir/fonts/README.md"
rg -q 'lv_font_t stock_font_cjk_24' "$stock_dir/fonts/stock_font_cjk_24.c"
rg -q 'lv_font_t stock_font_num_48' "$stock_dir/fonts/stock_font_num_48.c"

# --- Every CJK glyph the model/mock renders exists in the cjk font subset. ---
python3 - "$stock_dir" <<'PY'
import re
import sys

stock_dir = sys.argv[1]
font_path = f"{stock_dir}/fonts/stock_font_cjk_24.c"
sources = [f"{stock_dir}/stock_model.c", f"{stock_dir}/stock_mock.c"]

font = open(font_path, encoding="utf-8").read()
covered = set()
for _, glyph in re.findall(r'/\* U\+([0-9A-Fa-f]{4,6}) "([^"]+)" \*/', font):
    if int(_, 16) > 0x7F:
        covered.update(glyph)

needed = set()
for source in sources:
    text = open(source, encoding="utf-8").read()
    needed.update(ch for ch in text if 0x4E00 <= ord(ch) <= 0x9FFF)
    needed.update(ch for ch in text if ch in "\u25b2\u25bc")

missing = needed - covered
if missing:
    print(f"Font subset missing glyphs: {sorted(missing)}", file=sys.stderr)
    sys.exit(1)
print(f"FONT_GLYPH_COVERAGE_OK ({len(needed)} glyphs)")
PY

# --- Host tests: pure model/mock compiled natively. ---
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
cc -std=c99 -Wall -Werror -Wextra -I"$stock_dir/include" \
  "$stock_dir/test/test_stock_host.c" "$stock_dir/stock_model.c" "$stock_dir/stock_mock.c" \
  -o "$work_dir/test_stock_host"
"$work_dir/test_stock_host"

git -C "$repo_root" diff --check
echo "PHASE_1C_STATIC_CHECKS_OK"
