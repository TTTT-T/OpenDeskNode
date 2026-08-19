#!/usr/bin/env python3
"""Live C0: host fixture -> DeviceSession -> real OpenClaw Talk.

Never prints tokens. Writes metrics JSON only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.config import load_gateway_token
from bridge.protocol import DEVICE_HZ, FRAME_BYTES, pack_audio_frame
from bridge.session import DeviceSession
from bridge.talk import GatewayTalkClient


def _read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise RuntimeError("expected mono s16 wav")
        if handle.getframerate() != DEVICE_HZ:
            raise RuntimeError("expected 16 kHz wav")
        return handle.readframes(handle.getnframes())


def _say_pcm(text: str) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "c0.wav"
        subprocess.run(
            ["say", "-v", "Tingting", "-o", str(path), "--data-format=LEI16@16000", text],
            check=True,
        )
        return _read_wav(path)


async def run_live(talk_url: str, text: str, timeout: float) -> dict:
    metrics = {
        "ok": False,
        "connected": False,
        "session": False,
        "uplink_bytes": 0,
        "downlink_bytes": 0,
        "downlink_frames": 0,
        "events": [],
        "talk_stats": {},
        "error": None,
    }
    token = load_gateway_token()
    if not token:
        metrics["error"] = "gateway token unresolved"
        return metrics
    talk = GatewayTalkClient(talk_url, token)
    texts = []
    binaries = []

    async def send_text(message):
        texts.append(message)
        metrics["events"].append(message.get("type"))

    async def send_bytes(frame):
        binaries.append(frame)
        metrics["downlink_frames"] += 1
        metrics["downlink_bytes"] += max(0, len(frame) - 16)

    try:
        await talk.connect()
        metrics["connected"] = True
        session = DeviceSession(talk, send_text, send_bytes)
        await session.handle_text(
            {
                "type": "hello",
                "protocol": 0,
                "device_id": "host-c0-live",
                "fw_version": "live",
                "audio": {
                    "sample_rate": DEVICE_HZ,
                    "channels": 1,
                    "bits": 16,
                    "frame_ms": 20,
                    "codec": "pcm_s16le_16k_mono",
                },
            }
        )
        await session.handle_text({"type": "conversation_open", "reason": "manual"})
        if not any(item.get("type") == "conversation_opened" for item in texts):
            metrics["error"] = next(
                (item for item in texts if item.get("type") == "conversation_reject"),
                {"type": "missing_opened"},
            )
            return metrics
        metrics["session"] = True
        pcm = await asyncio.to_thread(_say_pcm, text)
        await session.handle_text(
            {"type": "speech_start", "conversation_id": session.conversation_id}
        )
        for seq, offset in enumerate(range(0, len(pcm), FRAME_BYTES)):
            chunk = pcm[offset : offset + FRAME_BYTES]
            if len(chunk) < FRAME_BYTES:
                chunk += b"\x00" * (FRAME_BYTES - len(chunk))
            await session.handle_binary(
                pack_audio_frame(session.conversation_id, seq, seq * 20, chunk)
            )
            metrics["uplink_bytes"] += len(chunk)
            await asyncio.sleep(0.02)
        await session.handle_text(
            {"type": "speech_end", "conversation_id": session.conversation_id}
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if metrics["downlink_bytes"] > 0 and any(
                item.get("type") == "playback_end" for item in texts
            ):
                break
            await asyncio.sleep(0.05)
        await session.close()
        metrics["talk_stats"] = dict(talk.stats)
        metrics["ok"] = metrics["session"] and metrics["downlink_bytes"] > 0
        if not metrics["ok"] and metrics["error"] is None:
            metrics["error"] = "no downlink audio before timeout"
    except Exception as exc:
        metrics["error"] = str(exc)
        metrics["talk_stats"] = dict(talk.stats)
    finally:
        await talk.close()
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--talk-url", default="ws://127.0.0.1:18789")
    parser.add_argument("--text", default="你好 EVA，现在几点了")
    parser.add_argument("--out", default="artifacts/phase-02c/c0-live.json")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    started = time.monotonic()
    metrics = asyncio.run(run_live(args.talk_url, args.text, args.timeout))
    metrics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps({key: metrics[key] for key in metrics}, ensure_ascii=False))
    return 0 if metrics["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
