#!/usr/bin/env python3
"""Watch live C5 recovery through EVA Voice Bridge.

PASS requires post-recovery usability, not reconnect/hello alone:
  new Talk sessionId != saved stale sessionId, new speech_start, new uplink,
  and a new transcript.done. Bridge HTTP outages are waited out; the
  conversations counter is never used as evidence (it resets on process restart).
Does not print tokens. Writes metrics JSON only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
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
        "helloed": bool(snapshot.get("helloed")),
        "talk_connected": bool(snapshot.get("talk_connected")),
        "speech_starts": _int(metrics.get("speech_starts")),
        "uplink_frames": _int(metrics.get("uplink_frames")),
        "user_transcripts": len(metrics.get("user_transcripts") or []),
        "create_ok": _int(talk_stats.get("create_ok")),
    }


def init_state(pre_snapshot: dict | None = None) -> dict:
    stale = None
    if pre_snapshot:
        stale = pre_snapshot.get("talk_session_id")
    return {
        "stale_session_id": stale,
        "saw_outage": False,
        "recovered": False,
        "recovery_baseline": None,
    }


def note_unreachable(state: dict) -> None:
    state["saw_outage"] = True


def _disrupted(snapshot: dict, state: dict) -> bool:
    if snapshot.get("talk_connected") is False:
        return True
    if snapshot.get("helloed") is False:
        return True
    return False


def note_reachable(state: dict, snapshot: dict) -> None:
    if state.get("stale_session_id") is None:
        sid = snapshot.get("talk_session_id")
        if sid:
            state["stale_session_id"] = sid
    if not state.get("saw_outage") and _disrupted(snapshot, state):
        state["saw_outage"] = True
        return
    if state.get("saw_outage") and not state.get("recovered"):
        if _disrupted(snapshot, state):
            return
        state["recovered"] = True
        state["recovery_baseline"] = capture_baseline(snapshot)


def evaluate(state: dict, snapshot: dict, case: str) -> dict:
    recovered = bool(state.get("recovered"))
    stale = state.get("stale_session_id")
    sess = snapshot.get("talk_session_id") if snapshot else None
    base = state.get("recovery_baseline") or {}
    metrics = (snapshot or {}).get("metrics") or {}
    talk_stats = (snapshot or {}).get("talk_stats") or {}
    transcripts = metrics.get("user_transcripts") or []
    starts = _int(metrics.get("speech_starts"))
    frames = _int(metrics.get("uplink_frames"))
    creates = _int(talk_stats.get("create_ok"))
    if recovered and base:
        new_starts = max(0, starts - _int(base.get("speech_starts")))
        new_uplink = frames > _int(base.get("uplink_frames"))
        new_transcripts = transcripts[_int(base.get("user_transcripts")) :]
        new_creates = max(0, creates - _int(base.get("create_ok")))
    else:
        new_starts = 0
        new_uplink = False
        new_transcripts = []
        new_creates = 0
    done = _done_transcripts(new_transcripts)
    stale_hit = bool(sess is not None and stale is not None and sess == stale)
    new_session = bool(sess) and not stale_hit
    hello_only = bool(
        recovered and (snapshot or {}).get("helloed") and new_starts == 0 and not new_uplink
    )
    usable = bool(
        recovered
        and new_session
        and new_creates >= 1
        and new_starts >= 1
        and new_uplink
        and len(done) >= 1
    )
    return {
        "ok": usable,
        "case": case,
        "recovered": recovered,
        "saw_outage": bool(state.get("saw_outage")),
        "stale_session": stale_hit,
        "stale_session_id": stale,
        "new_session_id": sess,
        "new_speech_starts": int(new_starts),
        "new_uplink": bool(new_uplink),
        "new_create_ok": int(new_creates),
        "new_transcript_done": len(done),
        "hello_only": hello_only,
        "used_conversations_delta": False,
    }


def step(state: dict, snapshot: dict | None, reachable: bool, case: str) -> dict:
    if not reachable:
        note_unreachable(state)
        return evaluate(state, snapshot or {}, case)
    note_reachable(state, snapshot or {})
    return evaluate(state, snapshot or {}, case)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="http://127.0.0.1:8090")
    parser.add_argument("--out", default="artifacts/phase-02c/c5-live.json")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--case", choices=("bridge", "gateway", "wifi"), default="bridge")
    args = parser.parse_args()
    started = time.monotonic()
    metrics = {
        "ok": False,
        "error": None,
        "case": args.case,
        "baseline": None,
        "health": {},
        "samples": [],
        "final": {},
        "verdict": {},
        "state": None,
    }
    state = init_state()
    pre = None
    try:
        pre = _get(args.bridge + "/metrics")
        state = init_state(pre)
        metrics["baseline"] = capture_baseline(pre)
        metrics["health"] = {"talk_kind": pre.get("talk_kind"), "talk_connected": pre.get("talk_connected")}
    except Exception:
        if args.case != "bridge":
            metrics["error"] = "bridge unreachable before %s case" % args.case
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
            print(json.dumps(metrics, ensure_ascii=False))
            return 1
        note_unreachable(state)

    while time.monotonic() - started < args.timeout:
        reachable = True
        body = None
        try:
            body = _get(args.bridge + "/metrics")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            reachable = False
        verdict = step(state, body, reachable, args.case)
        if len(metrics["samples"]) < MAX_SAMPLES:
            metrics["samples"].append(
                {
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                    "reachable": reachable,
                    "helloed": None if body is None else body.get("helloed"),
                    "talk_session_id": None if body is None else body.get("talk_session_id"),
                    "talk_connected": None if body is None else body.get("talk_connected"),
                    "saw_outage": state["saw_outage"],
                    "recovered": state["recovered"],
                }
            )
        if verdict["ok"]:
            metrics["final"] = body or {}
            metrics["verdict"] = verdict
            metrics["state"] = {
                "stale_session_id": state.get("stale_session_id"),
                "saw_outage": state.get("saw_outage"),
                "recovered": state.get("recovered"),
            }
            metrics["ok"] = True
            break
        time.sleep(0.5)
    if not metrics["ok"] and metrics["error"] is None:
        metrics["error"] = "C5 %s recovery not evidenced (need new session + speech + uplink + transcript.done)" % args.case
        metrics["verdict"] = evaluate(state, metrics.get("final") or {}, args.case)
        metrics["state"] = {
            "stale_session_id": state.get("stale_session_id"),
            "saw_outage": state.get("saw_outage"),
            "recovered": state.get("recovered"),
        }
    metrics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(metrics, ensure_ascii=False))
    return 0 if metrics["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
