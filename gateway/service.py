"""Refresh, cache, freshness and dashboard assembly for Stock Gateway."""

import asyncio
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from gateway.stock_provider.models import IntradayBar, Quote, SymbolRef
from gateway.stock_provider.protocol import ProviderError

from .calendar import MarketSession, MarketSessionClock, SHANGHAI_TZ
from .config import GatewayConfig
from .models import (
    GatewayBar,
    GatewaySnapshot,
    MARKET_STATUSES,
    WatchlistSlot,
)
from .providers import ProviderCoordinator
from .repository import SQLiteRepository, validate_symbol


LOGGER = logging.getLogger(__name__)


def gateway_now() -> datetime:
    return datetime.now(SHANGHAI_TZ)


def iso_timestamp(value: Optional[datetime] = None) -> str:
    current = value or gateway_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=SHANGHAI_TZ)
    else:
        current = current.astimezone(SHANGHAI_TZ)
    return current.isoformat()


def parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(SHANGHAI_TZ)


def _age_seconds(value: Optional[str], now: datetime) -> Optional[float]:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    return max(0.0, (now.astimezone(SHANGHAI_TZ) - parsed).total_seconds())


def canonicalize_quote(quote: Quote) -> Tuple[Optional[str], Optional[float], Optional[float]]:
    """Return a real source timestamp and recomputed change values.

    The provider's change and change-percent fields are deliberately ignored.
    If a source did not provide a timestamp, ``None`` is retained instead of
    pretending the local fetch time was the source data time.
    """

    current = quote.price
    previous = quote.previous_close
    if current is None or previous is None:
        change_amount = None
        change_percent = None
    else:
        change_amount = round(float(current) - float(previous), 10)
        change_percent = (
            round(change_amount / float(previous) * 100.0, 10)
            if float(previous) != 0
            else None
        )
    timestamp = quote.timestamp if parse_timestamp(quote.timestamp) is not None else None
    return timestamp, change_amount, change_percent


class StockGatewayService:
    """Owns the single refresh lifecycle and read-only dashboard projection."""

    def __init__(
        self,
        repository: SQLiteRepository,
        config: GatewayConfig,
        providers: Optional[Any] = None,
        market_clock: Optional[MarketSessionClock] = None,
        clock: Any = gateway_now,
    ) -> None:
        self.repository = repository
        self.config = config
        self.providers = providers or ProviderCoordinator(
            timeout_seconds=config.provider_timeout_seconds,
            retries=config.provider_retries,
            backoff_seconds=config.provider_backoff_seconds,
        )
        self.market_clock = market_clock or MarketSessionClock()
        self.clock = clock
        self._refresh_lock: Optional[asyncio.Lock] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._task: Optional[asyncio.Task] = None
        self._started = False
        for key, value in (
            ("quote_ttl_seconds", config.quote_ttl_seconds),
            ("intraday_ttl_seconds", config.intraday_ttl_seconds),
            ("off_market_refresh_seconds", config.off_market_refresh_seconds),
            ("stale_seconds", config.stale_seconds),
            ("provider_timeout_seconds", config.provider_timeout_seconds),
            ("provider_retries", config.provider_retries),
            ("provider_backoff_seconds", config.provider_backoff_seconds),
        ):
            self.repository.set_setting(key, value)
        stored_provider_status = self.repository.get_service_state("provider_status", {})
        restore = getattr(self.providers, "restore_status", None)
        if callable(restore):
            restore(stored_provider_status)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._started = True
        self._task = asyncio.create_task(self._run_loop(), name="stock-gateway-refresh")

    async def stop(self) -> None:
        task = self._task
        if task is None:
            self._started = False
            return
        if self._stop_event is not None:
            self._stop_event.set()
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._started = False

    async def _run_loop(self) -> None:
        first = True
        while True:
            try:
                await self.refresh_once(force=first)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.exception("refresh loop failed: %s", exc)
                self.repository.set_service_state(
                    "last_refresh_result",
                    {"status": "ERROR", "error": str(exc)[:500]},
                )
            first = False
            if self._stop_event is None:
                return
            session = self.market_clock.session_at(self.clock())
            delay = (
                min(self.config.quote_ttl_seconds, 10.0)
                if session.state == "TRADING"
                else self.config.off_market_refresh_seconds
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=max(0.1, delay))
                return
            except asyncio.TimeoutError:
                continue

    async def refresh_once(
        self,
        force: bool = False,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()
        async with self._refresh_lock:
            return await asyncio.to_thread(self._refresh_once_sync, force, now)

    def _refresh_once_sync(
        self,
        force: bool,
        now: Optional[datetime],
    ) -> Dict[str, Any]:
        current = now or self.clock()
        current = self._as_shanghai(current)
        session = self.market_clock.session_at(current)
        symbols = self.repository.unique_symbols()
        result: Dict[str, Any] = {
            "status": "OK",
            "gateway_timestamp": iso_timestamp(current),
            "market_session": session.to_dict(),
            "symbols": list(symbols),
            "attempted": 0,
            "quote_success": 0,
            "intraday_success": 0,
            "partial_failures": [],
        }

        quote_due_by_symbol: Dict[str, bool] = {}
        quote_due_symbols: List[str] = []
        for symbol in symbols:
            snapshot = self.repository.get_snapshot(symbol) or GatewaySnapshot.empty(symbol)
            quote_ttl = (
                self.config.quote_ttl_seconds
                if session.state == "TRADING"
                else self.config.off_market_refresh_seconds
            )
            quote_due = force or self._is_due(snapshot.quote_fetched_at, quote_ttl, current)
            quote_due_by_symbol[symbol] = quote_due
            if quote_due:
                quote_due_symbols.append(symbol)

        quote_results: Dict[str, Quote] = {}
        quote_errors: Dict[str, List[str]] = {}
        if quote_due_symbols:
            try:
                quote_results, quote_errors = self.providers.quotes(quote_due_symbols)
            except Exception as exc:
                error = str(exc)[:400]
                quote_errors = {symbol: [error] for symbol in quote_due_symbols}
                LOGGER.exception("quote batch refresh failed: %s", exc)

        for symbol in symbols:
            result["attempted"] += 1
            try:
                symbol_result = self._refresh_symbol(
                    symbol,
                    session,
                    current,
                    force,
                    quote_due=quote_due_by_symbol[symbol],
                    quote=quote_results.get(symbol),
                    quote_errors=quote_errors.get(symbol),
                )
                result["quote_success"] += int(symbol_result["quote_success"])
                result["intraday_success"] += int(symbol_result["intraday_success"])
                if symbol_result["errors"]:
                    result["partial_failures"].append(
                        {"symbol": symbol, "errors": symbol_result["errors"]}
                    )
            except Exception as exc:
                LOGGER.exception("refresh failed for %s", symbol)
                result["partial_failures"].append(
                    {"symbol": symbol, "errors": [str(exc)[:500]]}
                )
                snapshot = self.repository.get_snapshot(symbol) or GatewaySnapshot.empty(symbol)
                snapshot.last_error = str(exc)[:500]
                self.repository.upsert_snapshot(snapshot)
        if result["partial_failures"]:
            result["status"] = "PARTIAL"
        self.repository.set_service_state("last_refresh_at", result["gateway_timestamp"])
        self.repository.set_service_state("last_refresh_result", result)
        provider_status = getattr(self.providers, "status", lambda: {})()
        self.repository.set_service_state("provider_status", provider_status)
        self.repository.set_service_state(
            "calendar_status",
            {"source": getattr(self.market_clock, "calendar_source", "unknown")},
        )
        return result

    def _refresh_symbol(
        self,
        symbol: str,
        session: MarketSession,
        now: datetime,
        force: bool,
        quote_due: Optional[bool] = None,
        quote: Optional[Quote] = None,
        quote_errors: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        snapshot = self.repository.get_snapshot(symbol) or GatewaySnapshot.empty(symbol)
        errors: List[str] = []
        quote_success = False
        intraday_success = False
        quote_ttl = (
            self.config.quote_ttl_seconds
            if session.state == "TRADING"
            else self.config.off_market_refresh_seconds
        )
        intraday_ttl = (
            self.config.intraday_ttl_seconds
            if session.state in ("TRADING", "MIDDAY_BREAK", "CLOSED")
            else self.config.off_market_refresh_seconds
        )
        if quote_due is None:
            quote_due = force or self._is_due(snapshot.quote_fetched_at, quote_ttl, now)
        intraday_due = force or self._is_due(
            snapshot.intraday_fetched_at, intraday_ttl, now
        )

        if quote_due:
            if quote is not None:
                self._apply_quote(snapshot, quote, now)
                quote_success = True
            else:
                errors.extend(
                    "quote: %s" % str(error)[:400]
                    for error in (quote_errors or ("no usable quote",))
                )

        intraday_date = self._intraday_target_date(session, now)
        if intraday_due and intraday_date is not None:
            try:
                bars = self.providers.intraday(symbol, intraday_date.isoformat())
                normalized = self._normalize_intraday(symbol, bars, intraday_date)
                if not normalized:
                    raise ProviderError("intraday returned no active one-minute bars")
                snapshot.intraday = tuple(normalized)
                snapshot.intraday_session_date = intraday_date.isoformat()
                snapshot.intraday_data_timestamp = normalized[-1].timestamp
                snapshot.intraday_fetched_at = iso_timestamp(now)
                snapshot.intraday_source = normalized[-1].source
                intraday_success = True
            except Exception as exc:
                errors.append("intraday: %s" % str(exc)[:400])

        if quote_success or intraday_success:
            snapshot.last_success_at = iso_timestamp(now)
        snapshot.last_error = "; ".join(errors) if errors else None
        self.repository.upsert_snapshot(snapshot)
        return {
            "quote_success": quote_success,
            "intraday_success": intraday_success,
            "errors": errors,
        }

    @staticmethod
    def _as_shanghai(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=SHANGHAI_TZ)
        return value.astimezone(SHANGHAI_TZ)

    @staticmethod
    def _is_due(fetched_at: Optional[str], ttl: float, now: datetime) -> bool:
        age = _age_seconds(fetched_at, now)
        return age is None or age >= ttl

    def _intraday_target_date(
        self, session: MarketSession, now: datetime
    ) -> Optional[date]:
        if session.state in ("TRADING", "MIDDAY_BREAK", "CLOSED"):
            if not session.session_date:
                return None
            return date.fromisoformat(session.session_date)
        if session.state == "PRE_MARKET":
            reference = now.date() - timedelta(days=1)
        elif session.state == "STANDBY":
            reference = now.date()
        else:
            return None
        return self.market_clock.latest_session_on_or_before(reference)

    @staticmethod
    def _apply_quote(snapshot: GatewaySnapshot, quote: Quote, now: datetime) -> None:
        timestamp, change_amount, change_percent = canonicalize_quote(quote)
        snapshot.name = quote.name or snapshot.name
        snapshot.current_price = quote.price
        snapshot.previous_close = quote.previous_close
        snapshot.change_amount = change_amount
        snapshot.change_percent = change_percent
        snapshot.status = (
            quote.status if quote.status in MARKET_STATUSES else "UNKNOWN"
        )
        if timestamp is not None:
            snapshot.quote_data_timestamp = timestamp
        snapshot.quote_fetched_at = iso_timestamp(now)
        snapshot.quote_source = quote.source

    def _normalize_intraday(
        self,
        symbol: str,
        bars: Sequence[IntradayBar],
        trading_date: date,
    ) -> List[GatewayBar]:
        normalized: Dict[str, GatewayBar] = {}
        expected = trading_date.isoformat()
        for bar in bars:
            if not isinstance(bar, IntradayBar):
                raise ProviderError("provider returned a non-canonical intraday row")
            if validate_symbol(bar.code) != symbol:
                raise ProviderError("intraday row symbol mismatch for %s" % symbol)
            timestamp = parse_timestamp(bar.timestamp)
            if timestamp is None or timestamp.date().isoformat() != expected:
                raise ProviderError(
                    "intraday row timestamp does not match requested date %s" % expected
                )
            normalized[bar.timestamp] = GatewayBar(
                timestamp=bar.timestamp,
                price=bar.price,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                amount=bar.amount,
                source=bar.source,
            )
            if len(normalized) > self.config.max_intraday_bars:
                raise ProviderError("intraday response exceeds bounded bar limit")
        return [normalized[key] for key in sorted(normalized)]

    def resolve_symbol(self, symbol: str) -> SymbolRef:
        return self.providers.resolve_symbol(validate_symbol(symbol))

    def _get_slots_and_snapshots(
        self, device_id: str
    ) -> Tuple[List[WatchlistSlot], Dict[str, GatewaySnapshot]]:
        slots = self.repository.get_watchlist(device_id)
        symbols = [slot.symbol for slot in slots]
        snapshots = self.repository.get_snapshots(symbols)
        return slots, snapshots

    def _freshness(self, snapshot: GatewaySnapshot, now: datetime) -> Dict[str, Any]:
        age = _age_seconds(snapshot.last_success_at, now)
        stale = age is None or age > self.config.stale_seconds
        if stale and snapshot.last_error and snapshot.last_success_at is None:
            status = "ERROR"
        elif stale:
            status = "STALE"
        else:
            status = "FRESH"
        return {
            "status": status,
            "stale": stale,
            "age_seconds": round(age, 3) if age is not None else None,
            "stale_after_seconds": self.config.stale_seconds,
            "last_success_at": snapshot.last_success_at,
            "last_error": snapshot.last_error,
        }

    def dashboard(
        self,
        device_id: str,
        now: Optional[datetime] = None,
        touch_access: bool = False,
    ) -> Dict[str, Any]:
        device = self.repository.get_device(device_id)
        if device is None:
            raise KeyError(device_id)
        current = self._as_shanghai(now or self.clock())
        if touch_access:
            self.repository.touch_device_access(device_id, iso_timestamp(current))
            device = self.repository.get_device(device_id)
            assert device is not None
        slots, snapshots = self._get_slots_and_snapshots(device_id)
        session = self.market_clock.session_at(current)
        quotes: List[Dict[str, Any]] = []
        intraday: List[Dict[str, Any]] = []
        freshness_items: List[Dict[str, Any]] = []
        for slot in slots:
            snapshot = snapshots.get(slot.symbol) or GatewaySnapshot.empty(slot.symbol)
            if slot.name and not snapshot.name:
                snapshot.name = slot.name
            freshness = self._freshness(snapshot, current)
            quote = snapshot.to_api_dict(freshness)
            quote["slot"] = slot.slot
            quotes.append(quote)
            intraday.append(
                {
                    "symbol": slot.symbol,
                    "session_date": snapshot.intraday_session_date,
                    "data_timestamp": snapshot.intraday_data_timestamp,
                    "bars": [bar.to_dict() for bar in snapshot.intraday],
                }
            )
            freshness_items.append(
                {"symbol": slot.symbol, "slot": slot.slot, **freshness}
            )
        last_success_values = [
            item.get("last_success_at")
            for item in freshness_items
            if item.get("last_success_at")
        ]
        data_timestamps = [
            quote.get("data_timestamp") for quote in quotes if quote.get("data_timestamp")
        ]
        overall_last_success = max(last_success_values) if last_success_values else None
        overall_age = _age_seconds(overall_last_success, current)
        overall_stale = overall_age is None or overall_age > self.config.stale_seconds
        overall_status = "STALE" if overall_stale else "FRESH"
        if overall_stale and not overall_last_success:
            overall_status = "ERROR" if any(item.get("last_error") for item in freshness_items) else "STALE"
        return {
            "schema_version": 1,
            "device": device.to_dict() if device is not None else None,
            "watchlist": [slot.to_dict() for slot in slots],
            "quotes": quotes,
            "intraday": intraday,
            "market_session": session.to_dict(),
            "next_open_at": session.next_open_at,
            "gateway_timestamp": iso_timestamp(current),
            "data_timestamp": max(data_timestamps) if data_timestamps else None,
            "freshness": {
                "status": overall_status,
                "stale": overall_stale,
                "age_seconds": round(overall_age, 3) if overall_age is not None else None,
                "stale_after_seconds": self.config.stale_seconds,
                "last_success_at": overall_last_success,
                "by_symbol": freshness_items,
            },
            "stale": overall_stale,
        }

    def status(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        devices = self.repository.list_devices()
        selected = None
        if device_id is not None:
            selected = self.repository.get_device(device_id)
            if selected is None:
                raise KeyError(device_id)
        symbols = self.repository.unique_symbols()
        snapshots = self.repository.get_snapshots(symbols)
        now = self._as_shanghai(self.clock())
        preview = [
            {
                "symbol": symbol,
                "name": snapshots.get(symbol).name if snapshots.get(symbol) else None,
                "current_price": snapshots.get(symbol).current_price if snapshots.get(symbol) else None,
                "status": snapshots.get(symbol).status if snapshots.get(symbol) else "UNKNOWN",
                "last_success_at": snapshots.get(symbol).last_success_at if snapshots.get(symbol) else None,
                "freshness": self._freshness(
                    snapshots.get(symbol) or GatewaySnapshot.empty(symbol), now
                ),
            }
            for symbol in symbols
        ]
        return {
            "schema_version": 1,
            "gateway_timestamp": iso_timestamp(now),
            "calendar": {
                "source": getattr(self.market_clock, "calendar_source", "unknown"),
                "session": self.market_clock.session_at(now).to_dict(),
            },
            "provider": getattr(self.providers, "status", lambda: {})(),
            "devices": [device.to_dict() for device in devices],
            "selected_device": selected.to_dict() if selected else None,
            "watchlist_count": len(symbols),
            "preview": preview,
            "service_state": {
                "started": self._started,
                "last_refresh_at": self.repository.get_service_state("last_refresh_at"),
                "last_refresh_result": self.repository.get_service_state("last_refresh_result"),
            },
        }

    def health(self) -> Dict[str, Any]:
        now = iso_timestamp(self._as_shanghai(self.clock()))
        database_ok = self.repository.ping()
        last_result = self.repository.get_service_state("last_refresh_result", {})
        provider_status = getattr(self.providers, "status", lambda: {})()
        return {
            "status": "ok" if database_ok else "error",
            "service": "stock-gateway",
            "schema_version": 1,
            "database": "ok" if database_ok else "error",
            "refresh_worker": "running" if self._started else "stopped",
            "last_refresh_at": self.repository.get_service_state("last_refresh_at"),
            "last_refresh_status": last_result.get("status") if isinstance(last_result, dict) else None,
            "provider_status": provider_status,
            "gateway_timestamp": now,
        }
