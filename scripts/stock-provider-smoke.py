#!/usr/bin/env python3
"""Gentle real-provider smoke for the fixed Phase 1D four-stock set.

This is intentionally separate from offline verification. It makes one quote
request per symbol through the fixed primary/fallback composition and one
Baidu intraday request per symbol, with a configurable delay between symbols.
It writes only canonical summaries and never prints credentials.
"""

import argparse
from datetime import date
import json
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from gateway.calendar import MarketSessionClock
from gateway.config import GatewayConfig
from gateway.providers import ProviderCoordinator


SYMBOLS = ("600519", "000001", "300750", "688981")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intraday-date", help="YYYY-MM-DD; defaults to latest weekday session")
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args()
    if args.delay_seconds < 0 or args.delay_seconds > 30:
        parser.error("--delay-seconds must be between 0 and 30")
    if args.timeout_seconds <= 0 or args.timeout_seconds > 60:
        parser.error("--timeout-seconds must be between 0 and 60")

    clock = MarketSessionClock()
    observation_date = date.fromisoformat(args.intraday_date) if args.intraday_date else None
    requested_date = observation_date or clock.latest_session_on_or_before(date.today())
    if requested_date is None:
        parser.error("could not determine an XSHG session date")
    coordinator = ProviderCoordinator(
        timeout_seconds=args.timeout_seconds,
        retries=1,
        backoff_seconds=0.25,
    )
    result = {
        "symbols": list(SYMBOLS),
        "intraday_date": requested_date.isoformat(),
        "quote": [],
        "intraday": [],
        "provider_status": {},
    }
    for symbol in SYMBOLS:
        try:
            quote = coordinator.quote(symbol)
            result["quote"].append(
                {
                    "symbol": symbol,
                    "ok": True,
                    "name": quote.name,
                    "price": quote.price,
                    "previous_close": quote.previous_close,
                    "timestamp": quote.timestamp,
                    "source": quote.source,
                }
            )
        except Exception as exc:
            result["quote"].append(
                {"symbol": symbol, "ok": False, "error": str(exc)[:300]}
            )
        if args.delay_seconds:
            time.sleep(args.delay_seconds)

        try:
            bars = coordinator.intraday(symbol, requested_date.isoformat())
            result["intraday"].append(
                {
                    "symbol": symbol,
                    "ok": True,
                    "count": len(bars),
                    "first_timestamp": bars[0].timestamp if bars else None,
                    "last_timestamp": bars[-1].timestamp if bars else None,
                    "source": bars[0].source if bars else None,
                }
            )
        except Exception as exc:
            result["intraday"].append(
                {"symbol": symbol, "ok": False, "error": str(exc)[:300]}
            )
        if args.delay_seconds and symbol != SYMBOLS[-1]:
            time.sleep(args.delay_seconds)

    result["provider_status"] = coordinator.status()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in result["quote"] + result["intraday"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
