#!/usr/bin/env python3
"""Watch a live C3 ESP32 barge-in through EVA Voice Bridge.

PASS is granted only from evidence produced AFTER this run started:
  - same conversation (barge-in must not open a new cid),
  - a new interrupt / cancelOutput cycle, and
  - a new Realtime user transcript.done after that interrupt.
Historical interrupts / transcripts can never pass. Requires a live
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
        "uplink_frames": _int(metrics.get("uplink_frames")),
        "interrupts": _int(metrics.get("interrupts")),
        "playback_ends": _int(metrics.get("playback_ends")),
        "dropped_after_interrupt": _int(metrics.get("dropped_after_interrupt")),
        "user_transcripts": len(metrics.get("user_transcripts") or []),
        "cancel_ok": _int(talk_stats.get("cancel_ok")),
        "talk_event_seq": _int(talk_stats.get("event_seq")),
        "conversations": _int(snapshot.get("conversations")),
    }


def evaluate(baseline: dict, snapshot: dict) -> dict:
    metrics = snapshot.get("metrics") or {}
    talk_stats = snapshot.get("talk_stats") or {}
    frames = _int(metrics.get("uplink_frames"))
    interrupts = _int(metrics.get("interrupts"))
    transcripts = metrics.get("user_transcripts") or []
    conv = snapshot.get("conversation_id")
    same_conv = conv is not None and conv == baseline["conversation_id"]
    if conv is None:
        new_uplink = False
        new_interrupts = 0
        new_transcripts = []
        new_cancel = 0
    elif same_conv:
        new_uplink = frames > baseline["uplink_frames"]
        new_interrupts = max(0, interrupts - baseline["interrupts"])
        new_transcripts = transcripts[baseline["user_transcripts"] :]
        new_cancel = max(0, _int(talk_stats.get("cancel_ok")) - baseline["cancel_ok"])
    else:
        new_uplink = False
        new_interrupts = 0
        new_transcripts = []
        new_cancel = 0
    transcript = None
    for entry in reversed(new_transcripts):
        if str(entry.get("talkType") or "").endswith("done"):
            transcript = entry
            break
    cancelled = new_interrupts > 0 or new_cancel > 0
    return {
        "same_conversation": same_conv,
        "new_uplink": bool(new_uplink),
        "new_interrupts": int(new_interrupts),
        "new_cancel_ok": int(new_cancel),
        "uplink_frames": frames,
        "interrupts": interrupts,
        "dropped_after_interrupt": _int(metrics.get("dropped_after_interrupt")),
        "transcript": transcript,
        "barge_in_complete": bool(same_conv and cancelled and new_uplink and transcript),
    }


def _device_evidence(snapshot: dict) -> dict:
    metrics = snapshot.get("metrics") or {}
    keys = (
        "uplink_frames",
        "downlink_frames",
        "playback_starts",
        "playback_ends",
        "interrupts",
        "dropped_after_interrupt",
        "seq_gap",
        "dropped_old",
        "last_user_transcript",
    )
    return {key: metrics.get(key) for key in keys}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="http://127.0.0.1:8090")
    parser.add_argument("--out", default="artifacts/phase-02c/c3-live.json")
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
            if baseline["conversation_id"] is None:
                metrics["error"] = "no active conversation; start C2 playback first"
        except Exception as exc:
            metrics["error"] = "baseline capture failed: %s" % exc
    if metrics["error"] is not None:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps(metrics, ensure_ascii=False))
        return 1

    last_interrupts = baseline["interrupts"]
    last_frames = baseline["uplink_frames"]
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
            _int(snapshot["metrics"]["interrupts"]) != last_interrupts
            or _int(snapshot["metrics"]["uplink_frames"]) != last_frames
        ):
            if len(metrics["samples"]) < MAX_SAMPLES:
                metrics["samples"].append(snapshot)
            last_interrupts = _int(snapshot["metrics"]["interrupts"])
            last_frames = _int(snapshot["metrics"]["uplink_frames"])
        if verdict["barge_in_complete"]:
            metrics["final"] = snapshot
            metrics["final"]["talk_stats"] = {
                key: body.get("talk_stats", {}).get(key)
                for key in ("events", "event_seq", "cancel_ok", "cancel_fail", "append_ok")
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
        metrics["error"] = "no same-cid interrupt + new uplink + transcript.done after baseline"
    metrics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(metrics, ensure_ascii=False))
    return 0 if metrics["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
