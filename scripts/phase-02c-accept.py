#!/usr/bin/env python3
"""Unified Phase 2C hardware acceptance runner.

Starts C4/C3/C5 watchers in order, prints the one human action per case,
reads watcher JSON, collects C3 speaker and Stock UI YES/NO, and writes
hw-acceptance.json/.md. Does not print tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]

CASES = (
    "C4_MULTI_TURN",
    "C3_LOCAL_STOP",
    "C5_BRIDGE_RECOVERY",
    "C5_GATEWAY_RECOVERY",
    "C5_WIFI_RECOVERY",
    "STOCK_REGRESSION",
    "VOICE_LONG_RUN",
    "WAKE_WORD",
)

WATCH_ORDER = (
    "C4_MULTI_TURN",
    "C3_LOCAL_STOP",
    "C5_BRIDGE_RECOVERY",
    "C5_GATEWAY_RECOVERY",
    "C5_WIFI_RECOVERY",
)

PROMPTS = {
    "C4_MULTI_TURN": (
        "第一次按 BOOT，说第一句话，等 EVA 回答；不要再按任何键，直接说第二句，"
        "最好再说第三句。"
    ),
    "C3_LOCAL_STOP": "EVA 播放时按 BOOT。听扬声器是否立即停止。",
    "C5_BRIDGE_RECOVERY": (
        "先按 BOOT 说一句话，建立旧 Talk session。等到 watcher 打印 "
        "ARMED stale_session_id=... 之后，再停止并重新启动 Voice Bridge。"
        "不要重启 ESP32。恢复后再按 BOOT 说话。"
    ),
    "C5_GATEWAY_RECOVERY": (
        "先按 BOOT 说一句话，建立旧 Talk session。等到 watcher 打印 "
        "ARMED stale_session_id=... 之后，再暂时停止 OpenClaw Gateway :18789 并启动。"
        "不要重启 ESP32。恢复后再说话。"
    ),
    "C5_WIFI_RECOVERY": (
        "先按 BOOT 说一句话，建立旧 Talk session。等到 watcher 打印 "
        "ARMED stale_session_id=... 之后，再临时断开 ESP32 Wi-Fi 并恢复。"
        "不要重启 ESP32。恢复后再说话。"
    ),
    "STOCK_REGRESSION": "观察看板：stock task / Gateway 轮询仍正常，UI 不崩。",
    "VOICE_LONG_RUN": "本项不在本轮强制执行。",
    "WAKE_WORD": "WAKE MODEL PENDING：不要把未接入的「你好 EVA」写成 PASS。",
}


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def evaluate_c4(baseline: dict, snapshot: dict) -> dict:
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("phase_02c_c4_live", ROOT / "scripts" / "phase-02c-c4-live.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    verdict = module.evaluate(baseline, snapshot)
    return {
        "status": "PASS" if verdict.get("multi_turn_complete") else "FAIL",
        "reason": "same cid/session, 2+ speech_start, 2+ transcript.done"
        if verdict.get("multi_turn_complete")
        else "need same cid/session, 2+ speech_start, 2+ transcript.done, no session recreate",
        "detail": verdict,
    }


def evaluate_c3(baseline: dict, snapshot: dict, speaker_stopped: Optional[bool]) -> dict:
    metrics = snapshot.get("metrics") or {}
    talk_stats = snapshot.get("talk_stats") or {}
    same = snapshot.get("conversation_id") == baseline.get("conversation_id")
    new_int = max(0, _int(metrics.get("interrupts")) - _int(baseline.get("interrupts")))
    new_cancel = max(0, _int(talk_stats.get("cancel_ok")) - _int(baseline.get("cancel_ok")))
    auto_ok = bool(same and new_int >= 1 and new_cancel >= 1)
    if speaker_stopped is None:
        status = "HW-ACCEPTANCE-PENDING" if auto_ok else "FAIL"
        reason = "need user confirmation that speaker stopped" if auto_ok else "missing interrupt/cancel evidence"
    else:
        status = "PASS" if auto_ok and speaker_stopped else "FAIL"
        reason = "BOOT local-stop evidenced" if status == "PASS" else "speaker did not stop or missing interrupt"
    return {
        "status": status,
        "reason": reason,
        "detail": {"same_conversation": same, "new_interrupts": new_int, "new_cancel_ok": new_cancel},
    }


def evaluate_from_watch(name: str, watched: dict) -> dict:
    ok = bool(watched.get("ok"))
    verdict = watched.get("verdict") or {}
    if name == "C4_MULTI_TURN":
        ok = bool(ok or verdict.get("multi_turn_complete"))
    return {
        "status": "PASS" if ok else "FAIL",
        "reason": watched.get("error")
        or watched.get("reason")
        or ("watcher PASS" if ok else "watcher FAIL"),
        "detail": verdict or watched,
    }


def evaluate_c3_from_watch(watched: dict, speaker_stopped: Optional[bool]) -> dict:
    verdict = watched.get("verdict") or {}
    auto_ok = bool(watched.get("ok") or verdict.get("barge_in_complete"))
    if speaker_stopped is None:
        return {
            "status": "HW-ACCEPTANCE-PENDING" if auto_ok else "FAIL",
            "reason": "need speaker YES/NO" if auto_ok else "missing interrupt/cancel evidence",
            "detail": verdict or watched,
        }
    ok = bool(auto_ok and speaker_stopped)
    return {
        "status": "PASS" if ok else "FAIL",
        "reason": "BOOT local-stop evidenced" if ok else "speaker did not stop or missing interrupt",
        "detail": verdict or watched,
    }


def evaluate_stock(stock_ok: Optional[bool], ui_ok: Optional[bool]) -> dict:
    if stock_ok is None or ui_ok is None:
        return {
            "status": "HW-ACCEPTANCE-PENDING",
            "reason": "needs live stock task + UI observation during voice tests",
            "detail": {},
        }
    ok = bool(stock_ok and ui_ok)
    return {
        "status": "PASS" if ok else "FAIL",
        "reason": "stock path survived voice recovery" if ok else "stock path degraded during voice tests",
        "detail": {"stock_ok": stock_ok, "ui_ok": ui_ok},
    }


def evaluate_pending(name: str) -> dict:
    if name == "WAKE_WORD":
        return {
            "status": "WAKE MODEL PENDING",
            "reason": "no confirmed custom WakeNet model for 你好 EVA",
            "detail": {},
        }
    return {
        "status": "PENDING",
        "reason": "not in this hardware acceptance pass",
        "detail": {},
    }


def render_summary(results: dict[str, dict]) -> str:
    lines = []
    for name in CASES:
        item = results.get(name) or {"status": "PENDING"}
        lines.append("%-24s %s" % (name, item.get("status")))
    return "\n".join(lines) + "\n"


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    md = path.with_suffix(".md")
    lines = [
        "# Phase 2C hardware acceptance",
        "",
        "HEAD: `%s`" % payload.get("head"),
        "Generated: %s" % payload.get("generated"),
        "",
        "```",
        render_summary(payload.get("results") or {}).rstrip(),
        "```",
        "",
    ]
    for name in CASES:
        item = (payload.get("results") or {}).get(name) or {}
        lines.append("## %s" % name)
        lines.append("")
        lines.append("- status: `%s`" % item.get("status"))
        lines.append("- reason: %s" % item.get("reason"))
        lines.append("")
    md.write_text("\n".join(lines))


def preflight(bridge: str) -> dict:
    out = {"bridge": None, "error": None}
    try:
        out["bridge"] = _get(bridge + "/healthz")
    except Exception as exc:
        out["error"] = "bridge unreachable: %s" % exc
    return out


def default_ask(prompt: str) -> Optional[bool]:
    if not sys.stdin.isatty():
        print(prompt + "(no TTY; leaving pending)")
        return None
    while True:
        raw = input(prompt).strip().lower()
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False


def watcher_spec(name: str) -> tuple[str, list[str], str]:
    if name == "C4_MULTI_TURN":
        return "phase-02c-c4-live.py", [], "c4-live.json"
    if name == "C3_LOCAL_STOP":
        return "phase-02c-c3-live.py", [], "c3-live.json"
    mapped = {
        "C5_BRIDGE_RECOVERY": "bridge",
        "C5_GATEWAY_RECOVERY": "gateway",
        "C5_WIFI_RECOVERY": "wifi",
    }[name]
    return "phase-02c-c5-live.py", ["--case", mapped], "c5-%s-live.json" % mapped


def run_live_watcher(name: str, bridge: str, timeout: float, out_dir: Path, python_bin: str) -> dict:
    script, extra, filename = watcher_spec(name)
    out = out_dir / filename
    cmd = [
        python_bin,
        str(ROOT / "scripts" / script),
        "--bridge",
        bridge,
        "--timeout",
        str(timeout),
        "--out",
        str(out),
        *extra,
    ]
    print("Starting watcher:", " ".join(cmd))
    subprocess.run(cmd, check=False)
    if not out.is_file():
        return {"ok": False, "error": "watcher produced no JSON", "verdict": {}}
    return json.loads(out.read_text())


def run_acceptance(
    bridge: str = "http://127.0.0.1:8090",
    timeout: float = 180,
    out_dir: Optional[Path] = None,
    python_bin: Optional[str] = None,
    watch_fn: Optional[Callable[[str], dict]] = None,
    ask_fn: Optional[Callable[[str], Optional[bool]]] = None,
    head: str = "",
    out: Optional[Path] = None,
) -> dict:
    out_dir = out_dir or (ROOT / "artifacts" / "phase-02c")
    out_dir.mkdir(parents=True, exist_ok=True)
    python_bin = python_bin or sys.executable
    ask_fn = ask_fn or default_ask
    results: dict[str, dict] = {}
    watch_calls: list[str] = []
    for name in WATCH_ORDER:
        print()
        print("======== %s ========" % name)
        print("ACTION:", PROMPTS[name])
        if watch_fn is not None:
            watched = watch_fn(name)
        else:
            watched = run_live_watcher(name, bridge, timeout, out_dir, python_bin)
        watch_calls.append(name)
        if name == "C3_LOCAL_STOP":
            speaker = ask_fn("扬声器是否立即停止？ [y/n] ")
            results[name] = evaluate_c3_from_watch(watched, speaker)
        else:
            results[name] = evaluate_from_watch(name, watched)
        print("%s -> %s" % (name, results[name]["status"]))
    print()
    print("======== STOCK_REGRESSION ========")
    print("ACTION:", PROMPTS["STOCK_REGRESSION"])
    stock_ok = ask_fn("stock task / Gateway 轮询是否正常？ [y/n] ")
    ui_ok = ask_fn("股票 UI 是否未崩？ [y/n] ")
    results["STOCK_REGRESSION"] = evaluate_stock(stock_ok, ui_ok)
    results["VOICE_LONG_RUN"] = evaluate_pending("VOICE_LONG_RUN")
    results["WAKE_WORD"] = evaluate_pending("WAKE_WORD")
    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "head": head,
        "watch_order": watch_calls,
        "results": results,
        "prompts": PROMPTS,
    }
    if out is not None:
        write_report(out, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="http://127.0.0.1:8090")
    parser.add_argument("--out", default="artifacts/phase-02c/hw-acceptance.json")
    parser.add_argument("--head", default="")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--print-prompts", action="store_true")
    parser.add_argument("--run", action="store_true", help="start watchers and collect YES/NO")
    args = parser.parse_args()
    if args.print_prompts:
        for name in CASES:
            print("%s\t%s" % (name, PROMPTS[name]))
        return 0
    out = Path(args.out)
    if args.run:
        pre = preflight(args.bridge)
        if pre.get("error"):
            print("preflight:", pre["error"])
            print("C4 needs Bridge up. C5 bridge-restart watcher will wait if it later goes down.")
        payload = run_acceptance(
            bridge=args.bridge,
            timeout=args.timeout,
            out_dir=out.parent,
            python_bin=os.environ.get("PYTHON_BIN", sys.executable),
            head=args.head,
            out=out,
        )
        payload["preflight"] = pre
        write_report(out, payload)
        print()
        print(render_summary(payload["results"]))
        print("Wrote", out, "and", out.with_suffix(".md"))
        return 0
    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "head": args.head,
        "preflight": preflight(args.bridge),
        "results": {
            "VOICE_LONG_RUN": evaluate_pending("VOICE_LONG_RUN"),
            "WAKE_WORD": evaluate_pending("WAKE_WORD"),
        },
        "prompts": PROMPTS,
        "error": "pass --run to execute the hardware acceptance runner",
    }
    write_report(out, payload)
    print("This entry must be used as: scripts/accept-hardware.sh (or phase-02c-accept.py --run)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
