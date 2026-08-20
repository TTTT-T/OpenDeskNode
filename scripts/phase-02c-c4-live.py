#!/usr/bin/env python3
"""Watch a live C4 ESP32 multi-turn conversation through EVA Voice Bridge.

PASS is granted only from evidence produced AFTER this run started:
  - one conversation_id + one Talk sessionId stay locked,
  - at least two new speech_start turns,
  - at least two new transcript.done entries,
  - Talk session is not recreated after lock.
Historical transcripts / speech_starts can never pass. Requires a live
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


def _done_transcripts(entries) -> list:
    out = []
    for entry in entries or []:
        if str(entry.get("talkType") or "").endswith("done"):
            out.append(entry)
    return out


def capture_baseline(snapshot: dict) -> dict:
    metrics = snapshot.get("metrics") or {}
    talk_stats = snapshot.get("talk_stats") or {}
    return {
        "started_unix": time.time(),
        "conversation_id": snapshot.get("conversation_id"),
        "talk_session_id": snapshot.get("talk_session_id"),
        "speech_starts": _int(metrics.get("speech_starts")),
        "uplink_frames": _int(metrics.get("uplink_frames")),
        "playback_starts": _int(metrics.get("playback_starts")),
        "playback_ends": _int(metrics.get("playback_ends")),
        "user_transcripts": len(metrics.get("user_transcripts") or []),
        "create_ok": _int(talk_stats.get("create_ok")),
        "conversations": _int(snapshot.get("conversations")),
    }


def evaluate(baseline: dict, snapshot: dict) -> dict:
    metrics = snapshot.get("metrics") or {}
    talk_stats = snapshot.get("talk_stats") or {}
    conv = snapshot.get("conversation_id")
    sess = snapshot.get("talk_session_id")
    locked_cid = baseline.get("conversation_id") or conv
    locked_sid = baseline.get("talk_session_id") or sess
    same_conv = conv is not None and locked_cid is not None and conv == locked_cid
    same_session = sess is not None and locked_sid is not None and sess == locked_sid
    cid_changed = (
        baseline.get("conversation_id") is not None
        and conv is not None
        and conv != baseline["conversation_id"]
    )
    sid_changed = (
        baseline.get("talk_session_id") is not None
        and sess is not None
        and sess != baseline["talk_session_id"]
    )
    starts = _int(metrics.get("speech_starts"))
    frames = _int(metrics.get("uplink_frames"))
    transcripts = metrics.get("user_transcripts") or []
    if conv is None or not same_conv or not same_session or cid_changed or sid_changed:
        new_starts = 0
        new_uplink = False
        new_transcripts = []
        new_play = 0
        new_creates = 0
    else:
        if baseline.get("conversation_id") is None:
            new_starts = starts
            new_uplink = frames > 0
            new_transcripts = transcripts
            new_play = _int(metrics.get("playback_starts"))
            new_creates = max(0, _int(talk_stats.get("create_ok")) - baseline["create_ok"])
        else:
            new_starts = max(0, starts - baseline["speech_starts"])
            new_uplink = frames > baseline["uplink_frames"]
            new_transcripts = transcripts[baseline["user_transcripts"] :]
            new_play = max(0, _int(metrics.get("playback_starts")) - baseline["playback_starts"])
            new_creates = max(0, _int(talk_stats.get("create_ok")) - baseline["create_ok"])
    done = _done_transcripts(new_transcripts)
    session_reused = bool(same_session and not sid_changed and new_creates == 0)
    if baseline.get("talk_session_id") is None and same_session:
        session_reused = bool(not sid_changed and new_creates <= 1)
    return {
        "same_conversation": bool(same_conv and not cid_changed),
        "same_talk_session": bool(same_session and not sid_changed),
        "session_reused": session_reused,
        "new_speech_starts": int(new_starts),
        "new_uplink": bool(new_uplink),
        "new_playback_starts": int(new_play),
        "new_create_ok": int(new_creates),
        "turns": done,
        "multi_turn_complete": bool(
            same_conv
            and not cid_changed
            and same_session
            and not sid_changed
            and session_reused
            and new_starts >= 2
            and new_uplink
            and len(done) >= 2
        ),
    }


def _device_evidence(snapshot: dict) -> dict:
    metrics = snapshot.get("metrics") or {}
    keys = (
        "speech_starts",
        "uplink_frames",
        "downlink_frames",
        "playback_starts",
        "playback_ends",
        "interrupts",
        "seq_gap",
        "dropped_old",
        "last_user_transcript",
        "user_transcripts",
    )
    return {key: metrics.get(key) for key in keys}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="http://127.0.0.1:8090")
    parser.add_argument("--out", default="artifacts/phase-02c/c4-live.json")
    parser.add_argument("--timeout", type=float, default=180)
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

    last_starts = baseline["speech_starts"]
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
            _int(snapshot["metrics"]["speech_starts"]) != last_starts
            or _int(snapshot["metrics"]["uplink_frames"]) != last_frames
        ):
            if len(metrics["samples"]) < MAX_SAMPLES:
                metrics["samples"].append(snapshot)
            last_starts = _int(snapshot["metrics"]["speech_starts"])
            last_frames = _int(snapshot["metrics"]["uplink_frames"])
        if verdict["multi_turn_complete"]:
            metrics["final"] = snapshot
            metrics["final"]["talk_stats"] = {
                key: body.get("talk_stats", {}).get(key)
                for key in ("events", "event_seq", "create_ok", "create_fail", "append_ok")
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
        metrics["error"] = (
            "need same cid/session, 2+ speech_start, 2+ transcript.done, no session recreate"
        )
    metrics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(metrics, ensure_ascii=False))
    return 0 if metrics["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
