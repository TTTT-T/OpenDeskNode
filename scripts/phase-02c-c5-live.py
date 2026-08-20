#!/usr/bin/env python3
"""Watch live C5 recovery through EVA Voice Bridge.

PASS is granted only from evidence produced AFTER this run started.
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
    recovery = snapshot.get("recovery") or {}
    return {
        "started_unix": time.time(),
        "conversation_id": snapshot.get("conversation_id"),
        "talk_session_id": snapshot.get("talk_session_id"),
        "helloed": bool(snapshot.get("helloed")),
        "conversations": _int(snapshot.get("conversations")),
        "create_ok": _int(talk_stats.get("create_ok")),
        "reconnects": _int(talk_stats.get("reconnects") or recovery.get("talk_reconnects")),
        "disconnects": _int(talk_stats.get("disconnects") or recovery.get("talk_disconnects")),
        "invalidations": _int(metrics.get("session_invalidations") or recovery.get("session_invalidations")),
        "talk_connected": bool(snapshot.get("talk_connected")),
    }


def evaluate(baseline: dict, snapshot: dict, case: str) -> dict:
    metrics = snapshot.get("metrics") or {}
    talk_stats = snapshot.get("talk_stats") or {}
    recovery = snapshot.get("recovery") or {}
    conv = snapshot.get("conversation_id")
    sess = snapshot.get("talk_session_id")
    helloed = bool(snapshot.get("helloed"))
    talk_connected = bool(snapshot.get("talk_connected"))
    new_reconnects = max(
        0,
        _int(talk_stats.get("reconnects") or recovery.get("talk_reconnects")) - baseline["reconnects"],
    )
    new_disconnects = max(
        0,
        _int(talk_stats.get("disconnects") or recovery.get("talk_disconnects"))
        - baseline["disconnects"],
    )
    new_invalid = max(
        0,
        _int(metrics.get("session_invalidations") or recovery.get("session_invalidations"))
        - baseline["invalidations"],
    )
    new_creates = max(0, _int(talk_stats.get("create_ok")) - baseline["create_ok"])
    new_ws = max(0, _int(snapshot.get("conversations")) - baseline["conversations"])
    stale_session = (
        baseline.get("talk_session_id") is not None
        and sess is not None
        and sess == baseline["talk_session_id"]
        and new_creates > 0
    )
    recovered_hello = helloed and (not baseline["helloed"] or new_ws > 0 or new_reconnects > 0 or new_invalid > 0)
    talk_recovered = talk_connected and (not baseline["talk_connected"] or new_reconnects > 0)
    verdict = {
        "case": case,
        "helloed": helloed,
        "talk_connected": talk_connected,
        "new_reconnects": int(new_reconnects),
        "new_disconnects": int(new_disconnects),
        "new_invalidations": int(new_invalid),
        "new_create_ok": int(new_creates),
        "new_ws_sessions": int(new_ws),
        "stale_session": bool(stale_session),
        "recovered_hello": bool(recovered_hello),
        "talk_recovered": bool(talk_recovered),
        "same_old_session": bool(sess is not None and sess == baseline.get("talk_session_id")),
    }
    if case == "bridge":
        verdict["ok"] = bool(helloed and new_ws >= 1 and not stale_session)
    elif case == "gateway":
        verdict["ok"] = bool(
            talk_connected
            and new_invalid >= 1
            and not stale_session
            and (new_reconnects >= 1 or talk_recovered)
        )
    elif case == "wifi":
        verdict["ok"] = bool(helloed and recovered_hello and not stale_session)
    else:
        verdict["ok"] = bool(helloed and not stale_session)
    return verdict


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
    }
    try:
        metrics["health"] = _get(args.bridge + "/healthz")
        if metrics["health"].get("talk_kind") != "GatewayTalkClient":
            metrics["error"] = "Talk is not live: talk_kind=%s" % metrics["health"].get("talk_kind")
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

    while time.monotonic() - started < args.timeout:
        try:
            body = _get(args.bridge + "/metrics")
        except Exception as exc:
            metrics["error"] = str(exc)
            break
        verdict = evaluate(baseline, body, args.case)
        if len(metrics["samples"]) < MAX_SAMPLES:
            metrics["samples"].append(
                {
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                    "helloed": body.get("helloed"),
                    "conversation_id": body.get("conversation_id"),
                    "talk_session_id": body.get("talk_session_id"),
                    "talk_connected": body.get("talk_connected"),
                    "conversations": body.get("conversations"),
                }
            )
        if verdict["ok"]:
            metrics["final"] = body
            metrics["verdict"] = verdict
            metrics["ok"] = True
            break
        time.sleep(0.5)
    if not metrics["ok"] and metrics["error"] is None:
        metrics["error"] = "C5 %s recovery not evidenced" % args.case
        try:
            metrics["final"] = _get(args.bridge + "/metrics")
            metrics["verdict"] = evaluate(baseline, metrics["final"], args.case)
        except Exception:
            pass
    metrics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(metrics, ensure_ascii=False))
    return 0 if metrics["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
