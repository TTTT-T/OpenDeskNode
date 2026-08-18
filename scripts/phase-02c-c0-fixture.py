#!/usr/bin/env python3
"""Host device fixture for C0. Talks EVA Voice Bridge protocol, not OpenClaw."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request

import numpy as np
from websocket import create_connection

from bridge.protocol import (
    CODEC_ID,
    DEVICE_HZ,
    FRAME_BYTES,
    PROTOCOL_VERSION,
    pack_audio_frame,
)


def sine_pcm(seconds: float) -> bytes:
    samples = np.arange(int(DEVICE_HZ * seconds), dtype=np.float64) / DEVICE_HZ
    wave = 10000 * np.sin(2 * np.pi * 400 * samples)
    return np.clip(np.rint(wave), -32768, 32767).astype("<i2").tobytes()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8090/voice/v0")
    parser.add_argument("--health", default="http://127.0.0.1:8090/healthz")
    parser.add_argument("--seconds", type=float, default=0.4)
    args = parser.parse_args()
    with urllib.request.urlopen(args.health, timeout=3) as response:
        health = json.loads(response.read().decode())
    print("health", {k: health[k] for k in health if k != "token"})
    ws = create_connection(args.url, timeout=10)
    ws.send(
        json.dumps(
            {
                "type": "hello",
                "protocol": PROTOCOL_VERSION,
                "device_id": "host-c0",
                "fw_version": "fixture",
                "audio": {
                    "sample_rate": DEVICE_HZ,
                    "channels": 1,
                    "bits": 16,
                    "frame_ms": 20,
                    "codec": CODEC_ID,
                },
            }
        )
    )
    print("<-", json.loads(ws.recv()))
    ws.send(json.dumps({"type": "conversation_open", "reason": "manual"}))
    opened = json.loads(ws.recv())
    print("<-", opened)
    if opened.get("type") != "conversation_opened":
        return 1
    cid = opened["conversation_id"]
    pcm = sine_pcm(args.seconds)
    ws.send(json.dumps({"type": "speech_start", "conversation_id": cid}))
    for seq, offset in enumerate(range(0, len(pcm), FRAME_BYTES)):
        chunk = pcm[offset : offset + FRAME_BYTES]
        if len(chunk) < FRAME_BYTES:
            chunk = chunk + b"\x00" * (FRAME_BYTES - len(chunk))
        ws.send_binary(pack_audio_frame(cid, seq, int(time.monotonic() * 1000), chunk))
    ws.send(json.dumps({"type": "speech_end", "conversation_id": cid}))
    deadline = time.time() + 20
    downlink = 0
    while time.time() < deadline:
        ws.settimeout(5)
        raw = ws.recv()
        if isinstance(raw, bytes):
            downlink += len(raw) - 16
            continue
        event = json.loads(raw)
        print("<-", event.get("type"), event.get("code") or event.get("reason") or "")
        if event.get("type") in {"playback_end", "conversation_end", "conversation_reject"}:
            break
    print("downlink_pcm_bytes", downlink)
    ws.close()
    return 0 if downlink > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
