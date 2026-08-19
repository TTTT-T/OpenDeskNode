#!/usr/bin/env python3
"""Watch a live C2 ESP32 downlink through EVA Voice Bridge.

PASS is granted only from evidence produced AFTER this run started:
  - new Bridge downlink frames on the CURRENT device session, and
  - a new complete playback cycle (playback_ends grew).
Historical downlink_frames / playback_ends can never pass. Requires a live
Gateway Talk connection; FakeTalk aborts the run.

Does not print tokens. Writes metrics JSON only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

MAX_SAMPLES = 200


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def capture_baseline(snapshot: dict) -> dict:
    metrics = snapshot.get("metrics") or {}
    talk_stats = snapshot.get("talk_stats") or {}
    return {
        "started_unix": time.time(),
        "conversation_id": snapshot.get("conversation_id"),
        "talk_session_id": snapshot.get("talk_session_id"),
        "downlink_frames": _int(metrics.get("downlink_frames")),
        "playback_starts": _int(metrics.get("playback_starts")),
        "playback_ends": _int(metrics.get("playback_ends")),
        "downlink_peak": _int(metrics.get("downlink_peak")),
        "talk_event_seq": _int(talk_stats.get("event_seq")),
        "conversations": _int(snapshot.get("conversations")),
    }


def evaluate(baseline: dict, snapshot: dict) -> dict:
    metrics = snapshot.get("metrics") or {}
    frames = _int(metrics.get("downlink_frames"))
    starts = _int(metrics.get("playback_starts"))
    ends = _int(metrics.get("playback_ends"))
    peak = _int(metrics.get("downlink_peak"))
    conv = snapshot.get("conversation_id")
    same_conv = conv is not None and conv == baseline["conversation_id"]
    if conv is None:
        new_downlink = False
        new_ends = 0
        new_starts = 0
    elif same_conv:
        new_downlink = frames > baseline["downlink_frames"]
        new_ends = max(0, ends - baseline["playback_ends"])
        new_starts = max(0, starts - baseline["playback_starts"])
    else:
        new_downlink = frames > 0
        new_ends = ends
        new_starts = starts
    return {
        "same_conversation": same_conv,
        "new_downlink": bool(new_downlink),
        "new_playback_ends": int(new_ends),
        "new_playback_starts": int(new_starts),
        "downlink_frames": frames,
        "downlink_peak": peak,
        "playback_complete": bool(new_downlink and new_ends > 0 and peak > 0),
    }


def _device_evidence(snapshot: dict) -> dict:
    metrics = snapshot.get("metrics") or {}
    keys = (
        "uplink_frames",
        "downlink_frames",
        "downlink_bytes",
        "downlink_peak",
        "playback_starts",
        "playback_ends",
        "seq_gap",
        "seq_dup",
        "seq_reorder",
        "dropped_old",
    )
    return {key: metrics.get(key) for key in keys}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="http://127.0.0.1:8090")
    parser.add_argument("--out", default="artifacts/phase-02c/c2-live.json")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    started = time.monotonic()
    metrics = {
        "ok": False,
        "error": None,
        "baseline": None,
        "health": {},
        "samples": [],
        "final": {},
        "device_evidence": {},
    }
    try:
        metrics["health"] = _get(args.bridge + "/healthz")
        if metrics["health"].get("talk_kind") != "GatewayTalkClient":
            metrics["error"] = "Talk is not live: talk_kind=%s" % metrics["health"].get(
                "talk_kind"
            )
        elif not metrics["health"].get("talk_connected"):
            metrics["error"] = "Gateway Talk connection is down"
    except Exception as exc:
        metrics["error"] = "bridge unreachable: %s" % exc
    if metrics["error"] is None:
        try:
            baseline_snapshot = _get(args.bridge + "/metrics")
            baseline = capture_baseline(baseline_snapshot)
            metrics["baseline"] = baseline
        except Exception as exc:
            metrics["error"] = "baseline capture failed: %s" % exc
    if metrics["error"] is not None:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps(metrics, ensure_ascii=False))
        return 1

    last_frames = baseline["downlink_frames"]
    last_ends = baseline["playback_ends"]
    while time.monotonic() - started < args.timeout:
        try:
            body = _get(args.bridge + "/metrics")
        except Exception as exc:
            metrics["error"] = str(exc)
            break
        if _int(body.get("conversations")) < baseline["conversations"]:
            metrics["error"] = "bridge restarted during run; baseline invalid"
            break
        snapshot = {
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "device_id": body.get("device_id"),
            "helloed": body.get("helloed"),
            "conversation_id": body.get("conversation_id"),
            "talk_session_id": body.get("talk_session_id"),
            "metrics": _device_evidence(body),
        }
        verdict = evaluate(baseline, body)
        if (
            snapshot["metrics"]["downlink_frames"] != last_frames
            or snapshot["metrics"]["playback_ends"] != last_ends
        ):
            if len(metrics["samples"]) < MAX_SAMPLES:
                metrics["samples"].append(snapshot)
            last_frames = snapshot["metrics"]["downlink_frames"]
            last_ends = snapshot["metrics"]["playback_ends"]
        if verdict["playback_complete"]:
            metrics["final"] = snapshot
            metrics["final"]["talk_stats"] = {
                key: body.get("talk_stats", {}).get(key)
                for key in ("events", "event_seq", "talk_event_types", "append_ok")
            }
            metrics["device_evidence"] = _device_evidence(body)
            metrics["verdict"] = verdict
            metrics["ok"] = True
            break
        time.sleep(0.5)
    if not metrics["final"] and metrics["error"] is None:
        try:
            metrics["final"] = _get(args.bridge + "/metrics")
        except Exception:
            pass
    if not metrics["ok"] and metrics["error"] is None:
        metrics["error"] = "no new Bridge downlink + playback_end after baseline"
    metrics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(metrics, ensure_ascii=False))
    return 0 if metrics["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
