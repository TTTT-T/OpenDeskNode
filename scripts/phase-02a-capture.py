#!/usr/bin/env python3
"""Phase 2A serial capture: reads the ESP32-S3 USB serial console, stores the
full log, and reassembles PHASE2A WAV dumps (base64 rows + CRC32) into .wav
files. Also mirrors PHASE2A_* summary lines into a digest file.

Usage: python3 scripts/phase-02a-capture.py --port /dev/cu.usbmodem3101 \
           --out artifacts/phase-02a/<date> [--minutes 90] [--expect-wavs 4]
"""
import argparse
import base64
import json
import re
import sys
import time
import zlib
from pathlib import Path

import serial  # pyserial

WAV_BEGIN_RE = re.compile(r"PHASE2A_WAV_BEGIN name=(\S+) bytes=(\d+) channels=(\d+) rate=(\d+)")
WAV_END_RE = re.compile(r"PHASE2A_WAV_END name=(\S+) emitted=(\d+) crc32=0x([0-9a-fA-F]+)")
WAVD_RE = re.compile(r"WAVD ([A-Za-z0-9+/=]+)\s*$")
DIGEST_RE = re.compile(r"PHASE2A_(STAT|ERLE|AEC|SEQ|STAB)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/cu.usbmodem3101")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--minutes", type=float, default=10.0)
    parser.add_argument("--expect-wavs", type=int, default=4)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    log_path = args.out / "serial.log"
    digest_path = args.out / "digest.log"
    manifest_path = args.out / "wavs.json"

    ser = serial.Serial(args.port, 115200, timeout=1.0)
    deadline = time.time() + args.minutes * 60

    current = None  # {name, bytes, channels, rate, chunks}
    wavs = {}
    line_buf = bytearray()
    captured = []

    with open(log_path, "wb") as log, open(digest_path, "w") as digest:
        print(f"capturing {args.port} for {args.minutes} min -> {args.out}", flush=True)
        while time.time() < deadline:
            data = ser.read(4096)
            if not data:
                continue
            log.write(data)
            log.flush()
            line_buf.extend(data)
            while b"\n" in line_buf:
                raw, _, rest = line_buf.partition(b"\n")
                line_buf = bytearray(rest)
                try:
                    line = raw.decode("utf-8", errors="replace").rstrip("\r")
                except Exception:
                    continue
                if not line:
                    continue

                m = WAV_BEGIN_RE.search(line)
                if m:
                    current = {
                        "name": m.group(1),
                        "bytes": int(m.group(2)),
                        "channels": int(m.group(3)),
                        "rate": int(m.group(4)),
                        "chunks": [],
                        "emitted": 0,
                    }
                    digest.write(line + "\n")
                    continue
                m = WAV_END_RE.search(line)
                if m and current is not None:
                    name, emitted, crc = m.group(1), int(m.group(2)), int(m.group(3), 16)
                    payload = b"".join(current["chunks"])
                    if emitted != current["emitted"]:
                        print(f"WARN {name}: emitted mismatch {current['emitted']} != {emitted}", flush=True)
                    actual_crc = zlib.crc32(payload) & 0xFFFFFFFF
                    ok = actual_crc == crc and len(payload) == current["bytes"]
                    out_file = args.out / f"{name}.wav"
                    out_file.write_bytes(payload)
                    sha = zlib.crc32(payload) & 0xFFFFFFFF
                    wavs[name] = {
                        "bytes": len(payload),
                        "channels": current["channels"],
                        "rate": current["rate"],
                        "crc32_expected": crc,
                        "crc32_actual": actual_crc,
                        "crc_ok": actual_crc == crc,
                        "size_ok": len(payload) == current["bytes"],
                        "file": str(out_file),
                        "payload_crc32": sha,
                    }
                    captured.append(name)
                    print(f"WAV {name}: {len(payload)} bytes crc_ok={ok}", flush=True)
                    digest.write(line + "\n")
                    current = None
                    continue
                m = WAVD_RE.search(line)
                if m and current is not None:
                    try:
                        chunk = base64.b64decode(m.group(1), validate=True)
                    except Exception:
                        print(f"WARN bad base64 row in {current['name']}", flush=True)
                        continue
                    current["chunks"].append(chunk)
                    current["emitted"] += len(m.group(1))
                    continue
                if DIGEST_RE.search(line):
                    digest.write(line + "\n")
                    digest.flush()
                    if "selftest_end" in line or "PHASE2A_STAB" in line:
                        print(line, flush=True)

    manifest = {"captured": wavs, "count": len(wavs), "expect": args.expect_wavs}
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"done: {len(wavs)}/{args.expect_wavs} wavs -> {manifest_path}")
    return 0 if len(wavs) >= args.expect_wavs else 1


if __name__ == "__main__":
    sys.exit(main())
