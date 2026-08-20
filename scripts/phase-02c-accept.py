#!/usr/bin/env python3
"""Unified Phase 2C hardware acceptance evaluator.

Machine-checkable verdicts live here so tests can lock PASS/FAIL rules.
The shell runner prints prompts and collects live evidence.
Does not print tokens or credentials.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

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

PROMPTS = {
    "C4_MULTI_TURN": (
        "第一次按 BOOT，说第一句话，等 EVA 回答；不要再按任何键，直接说第二句，"
        "最好再说第三句。"
    ),
    "C3_LOCAL_STOP": "EVA 播放时按 BOOT。听扬声器是否立即停止。",
    "C5_BRIDGE_RECOVERY": "停止并重新启动 Voice Bridge。不要重启 ESP32。然后再按一次 BOOT 说话。",
    "C5_GATEWAY_RECOVERY": "暂时停止 OpenClaw Gateway :18789，再启动。不要重启 ESP32。然后再说话。",
    "C5_WIFI_RECOVERY": "临时断开 ESP32 Wi-Fi（或 AP），再恢复网络。不要重启 ESP32。",
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

    root = Path(__file__).resolve().parents[1]
    spec = spec_from_file_location("phase_02c_c4_live", root / "scripts" / "phase-02c-c4-live.py")
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
        status = "PASS" if auto_ok else "FAIL"
        if auto_ok:
            status = "HW-ACCEPTANCE-PENDING"
        reason = "need user confirmation that speaker stopped" if auto_ok else "missing interrupt/cancel evidence"
    else:
        status = "PASS" if auto_ok and speaker_stopped else "FAIL"
        reason = "BOOT local-stop evidenced" if status == "PASS" else "speaker did not stop or missing interrupt"
    return {
        "status": status,
        "reason": reason,
        "detail": {"same_conversation": same, "new_interrupts": new_int, "new_cancel_ok": new_cancel},
    }


def evaluate_c5(case: str, baseline: dict, snapshot: dict) -> dict:
    from importlib.util import module_from_spec, spec_from_file_location

    root = Path(__file__).resolve().parents[1]
    spec = spec_from_file_location("phase_02c_c5_live", root / "scripts" / "phase-02c-c5-live.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    mapped = {"C5_BRIDGE_RECOVERY": "bridge", "C5_GATEWAY_RECOVERY": "gateway", "C5_WIFI_RECOVERY": "wifi"}[case]
    verdict = module.evaluate(baseline, snapshot, mapped)
    return {
        "status": "PASS" if verdict.get("ok") else "FAIL",
        "reason": "%s recovery evidenced" % mapped if verdict.get("ok") else "%s recovery not evidenced" % mapped,
        "detail": verdict,
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
    for name, item in (payload.get("results") or {}).items():
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="http://127.0.0.1:8090")
    parser.add_argument("--out", default="artifacts/phase-02c/hw-acceptance.json")
    parser.add_argument("--head", default="")
    parser.add_argument("--print-prompts", action="store_true")
    args = parser.parse_args()
    if args.print_prompts:
        for name in CASES:
            print("%s\t%s" % (name, PROMPTS[name]))
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
    }
    write_report(Path(args.out), payload)
    print(render_summary(payload["results"]))
    return 0 if payload["preflight"]["error"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
