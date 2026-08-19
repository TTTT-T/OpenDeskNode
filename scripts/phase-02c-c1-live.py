#!/usr/bin/env python3
"""Watch a live C1 ESP32 uplink through EVA Voice Bridge.

PASS is granted only from evidence produced AFTER this run started:
  - new ESP32 uplink frames counted by the bridge for the CURRENT device
    session (same session must grow past the baseline; a session opened after
    baseline only needs frames > 0), and
  - a new Realtime user transcript recorded by that same device session.
Historical uplink_frames, historical transcripts/texts or a historical
"transcript.done" event-type list can never pass: everything is compared
against the baseline captured at start. Requires a live Gateway Talk
connection; FakeTalk aborts the run.

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
        "user_transcripts": len(metrics.get("user_transcripts") or []),
        "talk_event_seq": _int(talk_stats.get("event_seq")),
        "conversations": _int(snapshot.get("conversations")),
    }


def evaluate(baseline: dict, snapshot: dict) -> dict:
    metrics = snapshot.get("metrics") or {}
    frames = _int(metrics.get("uplink_frames"))
    transcripts = metrics.get("user_transcripts") or []
    conv = snapshot.get("conversation_id")
    same_conv = conv is not None and conv == baseline["conversation_id"]
    if conv is None:
        new_uplink = False
        new_transcripts = []
    elif same_conv:
        new_uplink = frames > baseline["uplink_frames"]
        new_transcripts = transcripts[baseline["user_transcripts"] :]
    else:
        new_uplink = frames > 0
        new_transcripts = list(transcripts)
    # Only a committed final transcript (transcript.done) counts as evidence;
    # streaming transcript.delta partials are explicitly insufficient.
    transcript = None
    for entry in reversed(new_transcripts):
        if str(entry.get("talkType") or "").endswith("done"):
            transcript = entry
            break
    return {
        "same_conversation": same_conv,
        "new_uplink": bool(new_uplink),
        "uplink_frames": frames,
        "new_transcripts": new_transcripts,
        "transcript": transcript,
    }


def _device_evidence(snapshot: dict) -> dict:
    metrics = snapshot.get("metrics") or {}
    keys = (
        "uplink_frames",
        "uplink_bytes",
        "uplink_peak",
        "seq_gap",
        "seq_dup",
        "seq_reorder",
        "dropped_old",
        "commit_silence_bytes",
        "downlink_frames",
    )
    return {key: metrics.get(key) for key in keys}


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
        "baseline": None,
        "health": {},
        "samples": [],
        "final": {},
        "transcript": None,
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

    last_frames = baseline["uplink_frames"]
    last_transcripts = baseline["user_transcripts"]
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
            "user_transcript_count": len(
                (body.get("metrics") or {}).get("user_transcripts") or []
            ),
        }
        verdict = evaluate(baseline, body)
        if (
            snapshot["metrics"]["uplink_frames"] != last_frames
            or snapshot["user_transcript_count"] != last_transcripts
        ):
            if len(metrics["samples"]) < MAX_SAMPLES:
                metrics["samples"].append(snapshot)
            last_frames = snapshot["metrics"]["uplink_frames"]
            last_transcripts = snapshot["user_transcript_count"]
        if verdict["new_uplink"] and verdict["transcript"] is not None:
            metrics["final"] = snapshot
            metrics["final"]["talk_stats"] = {
                key: body.get("talk_stats", {}).get(key)
                for key in ("events", "event_seq", "talk_event_types", "append_ok")
            }
            metrics["transcript"] = verdict["transcript"]
            metrics["new_transcripts"] = verdict["new_transcripts"]
            metrics["device_evidence"] = _device_evidence(body)
            metrics["ok"] = True
            break
        time.sleep(0.5)
    if not metrics["final"] and metrics["error"] is None:
        try:
            metrics["final"] = _get(args.bridge + "/metrics")
        except Exception:
            pass
    if not metrics["ok"] and metrics["error"] is None:
        metrics["error"] = "no new ESP32 uplink + Realtime transcript after baseline"
    metrics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(metrics, ensure_ascii=False))
    return 0 if metrics["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
