#!/usr/bin/env python3
"""Run the bounded Phase 1D.0 provider bake-off.

The command intentionally records failures as evidence and exits zero after
writing the audit. It is not a health check and it never selects or routes a
production provider.
"""

import argparse
from dataclasses import asdict, is_dataclass
from datetime import datetime
import importlib.metadata
import json
import platform
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from gateway.stock_provider.adapters import build_provider
from gateway.stock_provider.protocol import ProviderCapabilityError


PACKAGE_NAMES = ("akshare", "adata", "easyquotation")
RATE_LIMIT_MARKERS = (
    "429",
    "too many",
    "rate limit",
    "throttle",
    "blocked",
    "频繁",
    "限流",
)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _error(exc: BaseException) -> Dict[str, Any]:
    message = re.sub(
        r"(?i)(token|api[_-]?key|secret|password)=\S+",
        r"\1=<redacted>",
        str(exc).replace("\n", " "),
    )[:500]
    lower = message.lower()
    return {
        "type": type(exc).__name__,
        "message": message,
        "rate_limit_marker": any(marker in lower for marker in RATE_LIMIT_MARKERS),
    }


def _package_versions() -> Dict[str, Optional[str]]:
    versions: Dict[str, Optional[str]] = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _quote_summary(quotes: Sequence[Any], symbols: Sequence[str]) -> Dict[str, Any]:
    rows = [_jsonable(quote) for quote in quotes]
    by_code = {row.get("code"): row for row in rows}
    return {
        "count": len(rows),
        "requested_count": len(symbols),
        "codes": [row.get("code") for row in rows],
        "coverage_complete": set(by_code) == set(symbols),
        "names_present": sum(1 for row in rows if row.get("name")),
        "previous_close_present": sum(
            1 for row in rows if row.get("previous_close") is not None
        ),
        "limit_up_present": sum(1 for row in rows if row.get("limit_up") is not None),
        "limit_down_present": sum(1 for row in rows if row.get("limit_down") is not None),
        "timestamps_present": sum(1 for row in rows if row.get("timestamp")),
        "statuses": sorted({row.get("status") for row in rows}),
        "quotes": rows,
    }


def _quote_stability(runs: Sequence[Mapping[str, Any]], symbols: Sequence[str]) -> Dict[str, Any]:
    successful = [run for run in runs if run.get("ok")]
    value_fields = (
        "name",
        "price",
        "previous_close",
        "change",
        "change_percent",
        "status",
        "limit_up",
        "limit_down",
    )
    snapshots = []
    for run in successful:
        rows = {
            row.get("code"): tuple(row.get(field) for field in value_fields)
            for row in run.get("summary", {}).get("quotes", [])
        }
        snapshots.append(rows)
    same_values = bool(snapshots) and all(snapshot == snapshots[0] for snapshot in snapshots[1:])
    return {
        "successful_runs": len(successful),
        "coverage_complete_runs": sum(
            1
            for run in successful
            if run.get("summary", {}).get("coverage_complete")
        ),
        "same_canonical_values_across_successful_runs": same_values,
        "requested_symbols": list(symbols),
    }


def _intraday_summary(bars: Sequence[Any], requested_date: str) -> Dict[str, Any]:
    rows = [_jsonable(bar) for bar in bars]
    dates = sorted(
        {
            str(row.get("timestamp", ""))[:10]
            for row in rows
            if row.get("timestamp")
        }
    )
    return {
        "count": len(rows),
        "observed_dates": dates,
        "requested_date": requested_date,
        "date_consistent": dates == [requested_date],
        "contains_requested_date": requested_date in dates,
        "stale_date_observed": bool(dates) and requested_date not in dates,
        "first_timestamp": rows[0].get("timestamp") if rows else None,
        "last_timestamp": rows[-1].get("timestamp") if rows else None,
        "first": rows[0] if rows else None,
        "last": rows[-1] if rows else None,
    }


def _run_provider(
    provider_name: str,
    symbols: Sequence[str],
    observation_date: str,
    repeats: int,
    delay_seconds: float,
    intraday_repeats: int,
    intraday_delay_seconds: float,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "name": provider_name,
        "resolve": [],
        "quote_runs": [],
        "intraday": [],
        "notes": [],
    }
    try:
        provider = build_provider(provider_name)
    except Exception as exc:
        result["initialization_error"] = _error(exc)
        return result

    result["source"] = provider.source

    for symbol in symbols:
        started = time.monotonic()
        try:
            resolved = provider.resolve_symbol(symbol)
            result["resolve"].append(
                {
                    "symbol": symbol,
                    "ok": True,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "value": _jsonable(resolved),
                }
            )
        except Exception as exc:
            result["resolve"].append(
                {
                    "symbol": symbol,
                    "ok": False,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "error": _error(exc),
                }
            )
            result["notes"].append(
                "resolve stopped after the first provider resolution failure"
            )
            break
        if delay_seconds:
            time.sleep(delay_seconds)

    consecutive_failures = 0
    for run_number in range(1, repeats + 1):
        started = time.monotonic()
        try:
            quotes = list(provider.get_quotes(symbols))
            summary = _quote_summary(quotes, symbols)
            if not summary["count"]:
                raise RuntimeError("empty canonical quote response")
            run = {
                "run": run_number,
                "ok": True,
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "raw_columns": list(getattr(provider, "last_quote_columns", [])),
                "summary": summary,
            }
            consecutive_failures = 0
        except ProviderCapabilityError as exc:
            run = {
                "run": run_number,
                "ok": False,
                "capability": False,
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "error": _error(exc),
            }
            result["quote_runs"].append(run)
            result["notes"].append(
                "quote stopped because the candidate lacks this capability"
            )
            break
        except Exception as exc:
            consecutive_failures += 1
            run = {
                "run": run_number,
                "ok": False,
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "raw_columns": list(getattr(provider, "last_quote_columns", [])),
                "error": _error(exc),
            }
        result["quote_runs"].append(run)
        if consecutive_failures >= 2:
            result["notes"].append(
                "quote polling stopped after two consecutive failures"
            )
            break
        if delay_seconds and run_number < repeats:
            time.sleep(delay_seconds)

    result["quote_stability"] = _quote_stability(
        result["quote_runs"], symbols
    )

    intraday_runs = intraday_repeats
    intraday_delay = intraday_delay_seconds
    stop_intraday = False
    for symbol in symbols:
        symbol_result: Dict[str, Any] = {
            "symbol": symbol,
            "requested_date": observation_date,
            "runs": [],
        }
        consecutive_failures = 0
        for run_number in range(1, intraday_runs + 1):
            started = time.monotonic()
            try:
                bars = list(provider.get_intraday(symbol, observation_date))
                summary = _intraday_summary(bars, observation_date)
                if not summary["count"]:
                    raise RuntimeError("empty canonical one-minute response")
                run = {
                    "run": run_number,
                    "ok": True,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "raw_columns": list(
                        getattr(provider, "last_intraday_columns", [])
                    ),
                    "summary": summary,
                }
                consecutive_failures = 0
            except ProviderCapabilityError as exc:
                run = {
                    "run": run_number,
                    "ok": False,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "capability": False,
                    "error": _error(exc),
                }
                symbol_result["runs"].append(run)
                result["notes"].append(
                    "intraday stopped because the candidate lacks this capability"
                )
                stop_intraday = True
                break
            except Exception as exc:
                consecutive_failures += 1
                run = {
                    "run": run_number,
                    "ok": False,
                    "latency_ms": round((time.monotonic() - started) * 1000, 1),
                    "raw_columns": list(
                        getattr(provider, "last_intraday_columns", [])
                    ),
                    "error": _error(exc),
                }
                if consecutive_failures >= 2:
                    result["notes"].append(
                        "intraday polling stopped after two consecutive failures"
                    )
                    stop_intraday = True
            symbol_result["runs"].append(run)
            if stop_intraday or (
                intraday_delay and run_number < intraday_runs
            ):
                if stop_intraday:
                    break
                time.sleep(intraday_delay)
        symbol_result["successful_runs"] = sum(
            1 for run in symbol_result["runs"] if run.get("ok")
        )
        result["intraday"].append(symbol_result)
        if stop_intraday:
            break

    all_intraday_runs = [
        run
        for symbol_result in result["intraday"]
        for run in symbol_result.get("runs", [])
    ]
    result["capabilities"] = {
        "resolve_symbol": any(item.get("ok") for item in result["resolve"]),
        "get_quotes": any(item.get("ok") for item in result["quote_runs"]),
        "get_intraday": any(item.get("ok") for item in all_intraday_runs),
    }
    result["rate_limit_marker_observed"] = any(
        item.get("error", {}).get("rate_limit_marker")
        for item in result["quote_runs"] + all_intraday_runs
        if not item.get("ok")
    )
    return result


def _phase_assessment(
    providers: Sequence[Mapping[str, Any]],
    symbols: Sequence[str],
    intraday_repeats: int,
    intraday_request_date: str,
) -> Dict[str, Any]:
    """Record the bounded bake-off conclusion without creating routing."""

    direct = next(
        (provider for provider in providers if provider.get("name") == "baidu-direct"),
        None,
    )
    direct_symbols = {
        item.get("symbol"): item for item in (direct or {}).get("intraday", [])
    }
    direct_gate_passed = len(direct_symbols) == len(symbols) and all(
        len(direct_symbols.get(symbol, {}).get("runs", [])) >= intraday_repeats
        and all(
            run.get("ok")
            and run.get("summary", {}).get("date_consistent")
            and run.get("summary", {}).get("count", 0) > 0
            for run in direct_symbols[symbol].get("runs", [])[:intraday_repeats]
        )
        for symbol in symbols
    )
    return {
        "non_trading_day_intraday_gate": (
            "passed" if direct_gate_passed else "not_passed"
        ),
        "intraday_request_date": intraday_request_date,
        "recommended_combination": {
            "quote_primary": "easyquotation-tencent",
            "intraday_supplementary": "baidu-direct",
            "quote_fallback": "adata-sina",
        },
        "trade_session_realtime_validated": False,
        "limit_or_suspended_hit_validated": False,
        "linux_nas_docker_validated": False,
    }


def run(config: Mapping[str, Any]) -> Dict[str, Any]:
    symbols = list(config["symbols"])
    observation_date = str(config["observation_date"])
    intraday_request_date = str(
        config.get("intraday_request_date", observation_date)
    )
    repeats = int(config.get("quote_repeats", 3))
    delay_seconds = float(config.get("delay_seconds", 1.0))
    intraday_repeats = int(config.get("intraday_repeats", 3))
    intraday_delay_seconds = float(
        config.get("intraday_delay_seconds", delay_seconds)
    )
    run_time = datetime.now().astimezone()
    docker_path = shutil.which("docker")
    providers = [
        _run_provider(
            provider_name,
            symbols,
            intraday_request_date,
            repeats,
            delay_seconds,
            intraday_repeats,
            intraday_delay_seconds,
        )
        for provider_name in config["providers"]
    ]
    return {
        "schema": 1,
        "run": {
            "observed_at": run_time.isoformat(),
            "host_date": run_time.date().isoformat(),
            "observation_date": observation_date,
            "intraday_request_date": intraday_request_date,
            "observation_weekday": datetime.strptime(
                observation_date, "%Y-%m-%d"
            ).strftime("%A"),
            "non_trading_day_expected": datetime.strptime(
                observation_date, "%Y-%m-%d"
            ).weekday() >= 5,
        },
        "test_config": _jsonable(config),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "system": platform.system(),
            "machine": platform.machine(),
            "docker_command": docker_path,
            "docker_available": docker_path is not None,
            "linux_tested": platform.system() == "Linux",
            "nas_docker_tested": False,
            "package_versions": _package_versions(),
        },
        "providers": providers,
        "assessment": _phase_assessment(
            providers,
            symbols,
            intraday_repeats,
            intraday_request_date,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default=str(ROOT_DIR / "config/phase-01d0-provider-bakeoff.json"),
    )
    parser.add_argument(
        "--output",
        default=str(
            ROOT_DIR
            / "docs/phase-reports/phase-01d0-provider-bakeoff-results.json"
        ),
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    output_path = Path(args.output)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    audit = run(config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("audit:", output_path)
    for provider in audit["providers"]:
        quote_ok = sum(
            1 for run_result in provider.get("quote_runs", []) if run_result.get("ok")
        )
        intraday_ok = sum(
            1
            for symbol_result in provider.get("intraday", [])
            for run_result in symbol_result.get("runs", [])
            if run_result.get("ok")
        )
        print(
            "%s: resolve=%d quote_runs=%d intraday_symbols=%d"
            % (
                provider["name"],
                sum(1 for item in provider.get("resolve", []) if item.get("ok")),
                quote_ok,
                intraday_ok,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
