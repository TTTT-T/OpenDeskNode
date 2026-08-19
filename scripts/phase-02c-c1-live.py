#!/usr/bin/env python3
"""Watch a live C1 ESP32 uplink through EVA Voice Bridge.

Does not print tokens. Writes metrics JSON only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="http://127.0.0.1:8090")
    parser.add_argument("--out", default="artifacts/phase-02c/c1-live.json")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    started = time.monotonic()
    metrics = {
        "ok": False,
        "error": None,
        "health": {},
        "samples": [],
        "final": {},
    }
    try:
        metrics["health"] = _get(args.bridge + "/healthz")
    except Exception as exc:
        metrics["error"] = "bridge unreachable: %s" % exc
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(metrics, indent=2) + "\n")
        print(json.dumps(metrics, ensure_ascii=False))
        return 1
    last_frames = 0
    saw_uplink = False
    while time.monotonic() - started < args.timeout:
        try:
            body = _get(args.bridge + "/metrics")
        except Exception as exc:
            metrics["error"] = str(exc)
            break
        snapshot = {
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "device_id": body.get("device_id"),
            "helloed": body.get("helloed"),
            "conversation_id": body.get("conversation_id"),
            "metrics": body.get("metrics") or {},
            "talk_stats": body.get("talk_stats") or {},
        }
        frames = int((snapshot["metrics"] or {}).get("uplink_frames") or 0)
        if frames > last_frames:
            metrics["samples"].append(snapshot)
            last_frames = frames
            saw_uplink = True
        transcripts = (snapshot["talk_stats"] or {}).get("transcripts") or []
        texts = (snapshot["talk_stats"] or {}).get("texts") or []
        talk_types = (snapshot["talk_stats"] or {}).get("talk_event_types") or []
        if saw_uplink and frames > 0 and (
            transcripts or texts or "transcript.done" in talk_types
        ):
            metrics["final"] = snapshot
            metrics["ok"] = True
            break
        time.sleep(0.5)
    if not metrics["final"]:
        try:
            metrics["final"] = _get(args.bridge + "/metrics")
        except Exception:
            pass
    if not metrics["ok"] and metrics["error"] is None:
        metrics["error"] = "no Realtime transcript after ESP32 uplink"
    metrics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(metrics, ensure_ascii=False))
    return 0 if metrics["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
