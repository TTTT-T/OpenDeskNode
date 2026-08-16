#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
audio_dir="$repo_root/firmware/product/components/audio"
python_bin="${PYTHON_BIN:-python3}"

required_files=(
  "$audio_dir/CMakeLists.txt"
  "$audio_dir/audio_hw.c"
  "$audio_dir/audio_selftest.c"
  "$audio_dir/audio_stimulus.c"
  "$audio_dir/include/audio_hw.h"
  "$audio_dir/include/audio_selftest.h"
  "$audio_dir/include/audio_stimulus.h"
  "$repo_root/scripts/phase-02a-capture.py"
  "$repo_root/scripts/phase-02a-analyze.py"
  "$repo_root/scripts/phase-02a-gen-stimulus.sh"
  "$repo_root/tests/test_phase2a_analyze.py"
)
for file in "${required_files[@]}"; do
  [[ -f "$file" ]] || { echo "Missing Phase 2A file: $file" >&2; exit 1; }
done

# Board pins must stay pinned to the frozen v2.4.2 reference configuration.
rg -q 'BOARD_I2C_SDA_GPIO        13' "$repo_root/firmware/product/components/board/include/board.h"
rg -q 'BOARD_I2C_SCL_GPIO        14' "$repo_root/firmware/product/components/board/include/board.h"
rg -q 'BOARD_I2S_MCLK_GPIO       16' "$repo_root/firmware/product/components/board/include/board.h"
rg -q 'BOARD_I2S_WS_GPIO         45' "$repo_root/firmware/product/components/board/include/board.h"
rg -q 'BOARD_I2S_BCLK_GPIO       9' "$repo_root/firmware/product/components/board/include/board.h"
rg -q 'BOARD_I2S_DOUT_GPIO       8' "$repo_root/firmware/product/components/board/include/board.h"
rg -q 'BOARD_I2S_DIN_GPIO        10' "$repo_root/firmware/product/components/board/include/board.h"
rg -q 'BOARD_AUDIO_PA_GPIO       46' "$repo_root/firmware/product/components/board/include/board.h"

# Full-duplex audio path: ES7210 TDM RX with 3 slots, ES8311 std TX, esp-sr AEC.
rg -q 'ES7210_SEL_MIC1 \| ES7210_SEL_MIC2 \| ES7210_SEL_MIC3' "$audio_dir/audio_hw.c"
rg -q 'I2S_TDM_SLOT0 \| I2S_TDM_SLOT1 \| I2S_TDM_SLOT2' "$audio_dir/audio_hw.c"
rg -q 'AUDIO_HW_SAMPLE_RATE 16000' "$audio_dir/include/audio_hw.h"
rg -q 'aec_create\(AUDIO_HW_SAMPLE_RATE' "$audio_dir/audio_selftest.c"
rg -q 'AEC_MODE_VOIP_HIGH_PERF' "$audio_dir/audio_selftest.c"
rg -q 'aec_process' "$audio_dir/audio_selftest.c"
rg -q 'PHASE2A_WAV_BEGIN' "$audio_dir/audio_selftest.c"
rg -q 'esp_rom_crc32_le' "$audio_dir/audio_selftest.c"

# The evidence WAVs must all be produced by the serial dump protocol.
for name in mic0_mic1 playback_reference aec_off aec_on; do
  rg -q "dump_wav..$name" "$audio_dir/audio_selftest.c" || {
    echo "selftest no longer dumps $name" >&2
    exit 1
  }
done

if rg -n 'finance\.pae\.baidu\.com|qt\.gtimg\.cn|api\.tenclass\.net|xiaozhi\.me' \
  "$repo_root/firmware/product" --glob '*.[ch]' --glob Kconfig; then
  echo "Firmware must not contain provider or Xiaozhi cloud endpoints" >&2
  exit 1
fi

# Dependencies must stay pinned to the accepted versions.
rg -q 'espressif/esp_codec_dev: "~1.5.6"' "$repo_root/firmware/product/main/idf_component.yml"
rg -q 'espressif/esp-sr: "~2.4.7"' "$repo_root/firmware/product/main/idf_component.yml"

"$python_bin" - <<'PY' || { echo "numpy is required for Phase 2A analyzer tests (requirements.txt)" >&2; exit 1; }
import numpy  # noqa: F401
PY

PYTHONPYCACHEPREFIX=/tmp/esp32-phase-2a-pycache "$python_bin" -m py_compile \
  "$repo_root/scripts/phase-02a-capture.py" \
  "$repo_root/scripts/phase-02a-analyze.py"

"$python_bin" -m unittest tests.test_phase2a_analyze -v

git -C "$repo_root" diff --check
echo "PHASE_2A_OFFLINE_CHECKS_OK"
