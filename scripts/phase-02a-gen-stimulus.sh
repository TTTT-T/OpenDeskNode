#!/usr/bin/env bash
# Regenerates firmware/product/components/audio/audio_stimulus.c using the
# macOS `say` TTS voice so the Phase 2A playback stimulus stays reproducible.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

TEXT="现在开始回声消除测试。第一句，今天天气晴朗，适合出行。第二句，上证指数上涨百分之零点五。第三句，请对着设备说话，测试近端语音。回声消除测试即将结束。"

say -v Tingting -o "$work/stimulus.aiff" "$TEXT"
afconvert -f WAVE -d LEI16@16000 -c 1 "$work/stimulus.aiff" "$work/stimulus_16k.wav"

python3 - "$work/stimulus_16k.wav" "$repo_root/firmware/product/components/audio" <<'PY'
import struct
import sys
import wave

src_path, out_dir = sys.argv[1], sys.argv[2]
src = wave.open(src_path, "rb")
assert src.getframerate() == 16000 and src.getnchannels() == 1 and src.getsampwidth() == 2
pcm = src.readframes(src.getnframes())
src.close()

data = b"\x00\x00" * 16000 + pcm + b"\x00\x00" * 16000
samples = struct.unpack("<%dh" % (len(data) // 2), data)
peak = max(abs(s) for s in samples)
scaled = [round(s * (26000 / peak)) for s in samples]

with open(f"{out_dir}/audio_stimulus.c", "w") as f:
    f.write('#include "audio_stimulus.h"\n\n')
    f.write("/* macOS `say -v Tingting` synthesized Mandarin sentence, resampled\n")
    f.write(" * to 16 kHz mono PCM16 and peak-normalized to 26000. Regenerate via\n")
    f.write(" * scripts/phase-02a-gen-stimulus.sh. */\n")
    f.write("const int16_t audio_stimulus_pcm[AUDIO_STIMULUS_SAMPLE_COUNT] = {\n")
    for i in range(0, len(scaled), 16):
        f.write("    " + ",".join(str(v) for v in scaled[i:i + 16]) + ",\n")
    f.write("};\n")

with open(f"{out_dir}/include/audio_stimulus.h", "w") as f:
    f.write("#pragma once\n\n#include <stdint.h>\n\n")
    f.write("#define AUDIO_STIMULUS_SAMPLE_COUNT %d\n" % len(scaled))
    f.write("extern const int16_t audio_stimulus_pcm[AUDIO_STIMULUS_SAMPLE_COUNT];\n")

print(f"stimulus: {len(scaled)} samples ({len(scaled) / 16000:.2f} s)")
PY
