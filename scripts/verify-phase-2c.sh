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
voice_dir="$ROOT_DIR/firmware/product/components/voice"

cd "$ROOT_DIR"

required_files=(
  "$voice_dir/voice_protocol.c"
  "$voice_dir/voice_runtime.c"
  "$voice_dir/include/voice_protocol.h"
  "$voice_dir/include/voice_runtime.h"
  "$ROOT_DIR/firmware/product/components/audio/audio_owner.c"
  "$ROOT_DIR/firmware/product/components/audio/include/audio_owner.h"
  "$ROOT_DIR/tests/test_bridge_c1.py"
  "$ROOT_DIR/tests/test_bridge_c3.py"
  "$ROOT_DIR/tests/test_c2_live_watcher.py"
  "$ROOT_DIR/tests/test_c3_live_watcher.py"
  "$ROOT_DIR/scripts/phase-02c-c2-live.py"
  "$ROOT_DIR/scripts/phase-02c-c3-live.py"
  "$voice_dir/voice_vad.c"
  "$voice_dir/include/voice_vad.h"
)
for file in "${required_files[@]}"; do
  [[ -f "$file" ]] || { echo "Missing Phase 2C C1 file: $file" >&2; exit 1; }
done

rg -q 'audio_owner_acquire' "$ROOT_DIR/firmware/product/components/audio/audio_selftest.c"
rg -q 'audio_owner_acquire' "$voice_dir/voice_runtime.c"
rg -q 'AUDIO_OWNER_VOICE' "$voice_dir/voice_runtime.c"
rg -q 'AUDIO_OWNER_SELFTEST' "$ROOT_DIR/firmware/product/components/audio/audio_selftest.c"
rg -q 'voice_runtime_start' "$ROOT_DIR/firmware/product/main/app_main.c"
rg -q 'voice_runtime_request_talk' "$ROOT_DIR/firmware/product/main/app_main.c"
rg -q 'VOICE_FRAME_BYTES' "$voice_dir/include/voice_protocol.h"
rg -q 'VOICE_TXQ_FRAMES 100' "$voice_dir/include/voice_protocol.h"
rg -q 'VOICE_RXQ_FRAMES 400' "$voice_dir/include/voice_protocol.h"
rg -q 'voice_rxq_push_pcm' "$voice_dir/voice_protocol.c"
rg -q 'playback_start' "$voice_dir/voice_runtime.c"
rg -q 'PHASE2C_C2' "$voice_dir/voice_runtime.c"
rg -q 'PHASE2C_C3' "$voice_dir/voice_runtime.c"
rg -q 'interrupt' "$voice_dir/voice_runtime.c"
rg -q 'voice_vad_feed' "$voice_dir/voice_runtime.c"
rg -q 'local_stop_playback' "$voice_dir/voice_runtime.c"
rg -q '_commit_turn' "$ROOT_DIR/bridge/session.py"
rg -q 'suppress_downlink' "$ROOT_DIR/bridge/session.py"
rg -q 'dropped_after_interrupt' "$ROOT_DIR/bridge/session.py"
rg -q 'commit_silence_ms' "$ROOT_DIR/bridge/session.py"
rg -q 'playback_starts' "$ROOT_DIR/bridge/session.py"

if rg -n 'talk\.session|openai\.com|OPENAI_API_KEY|api\.tenclass\.net|xiaozhi\.me' \
  "$voice_dir/voice_runtime.c" "$voice_dir/voice_protocol.c" \
  "$voice_dir/include/voice_runtime.h" "$voice_dir/include/voice_protocol.h"; then
  echo "Firmware voice transport must not contain OpenClaw/OpenAI/Xiaozhi APIs" >&2
  exit 1
fi

if rg -n 'audio_hw_read|audio_hw_write' "$voice_dir/voice_runtime.c" >/dev/null && \
   rg -n 'audio_owner_acquire\(AUDIO_OWNER_VOICE' "$voice_dir/voice_runtime.c" >/dev/null; then
  :
else
  echo "Voice runtime must own audio before RX/TX" >&2
  exit 1
fi

if rg -n '192\.168\.|10\.0\.[0-9]+\.|172\.(1[6-9]|2[0-9]|3[01])\.' \
  "$ROOT_DIR/firmware/product/sdkconfig.defaults" \
  "$ROOT_DIR/firmware/product/components/voice/Kconfig"; then
  echo "Tracked firmware config must not embed site-specific LAN addresses" >&2
  exit 1
fi

PYTHONPYCACHEPREFIX="$PYTHON_CACHE" "$PYTHON_BIN" -m unittest \
  tests.test_bridge_protocol tests.test_bridge_audio tests.test_bridge_c0 \
  tests.test_bridge_config   tests.test_bridge_c1 tests.test_c1_live_watcher \
  tests.test_c2_live_watcher tests.test_bridge_c3 tests.test_c3_live_watcher -v
PYTHONPYCACHEPREFIX="$PYTHON_CACHE" "$PYTHON_BIN" -m py_compile \
  bridge/__init__.py bridge/protocol.py bridge/audio.py bridge/config.py \
  bridge/talk.py bridge/session.py bridge/app.py bridge/__main__.py \
  scripts/phase-02c-c0-live.py scripts/phase-02c-c1-live.py \
  scripts/phase-02c-c2-live.py scripts/phase-02c-c3-live.py

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
cc -std=c99 -Wall -Werror -Wextra -I"$voice_dir/include" \
  "$voice_dir/test/test_voice_protocol.c" "$voice_dir/voice_protocol.c" \
  "$voice_dir/voice_vad.c" \
  -o "$work_dir/test_voice_protocol"
"$work_dir/test_voice_protocol"

git diff --check
echo "phase-2c C3 host verification: OK"
