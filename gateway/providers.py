"""The fixed Phase 1D provider composition and bounded call policy."""

from dataclasses import dataclass
from datetime import datetime
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from gateway.stock_provider.adapters import build_provider, normalize_code
from gateway.stock_provider.models import IntradayBar, Quote, SymbolRef
from gateway.stock_provider.protocol import ProviderError


LOGGER = logging.getLogger(__name__)
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class ProviderTimeout(ProviderError):
    """A bounded provider call did not return before its deadline."""


def call_with_timeout(function: Callable[[], Any], timeout_seconds: float) -> Any:
    """Run one blocking provider call with a daemon timeout guard.

    The 1D.0 third-party adapters do not all expose a transport timeout. A
    daemon worker gives the gateway an explicit upper bound without allowing a
    stuck provider request to block the refresh loop or process shutdown.
    """

    result: List[Any] = []
    failure: List[BaseException] = []

    def worker() -> None:
        try:
            result.append(function())
        except Exception as exc:  # propagate provider/library failures
            failure.append(exc)

    thread = threading.Thread(target=worker, name="stock-provider-call", daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise ProviderTimeout(
            "provider call exceeded timeout of %.2fs" % timeout_seconds
        )
    if failure:
        exc = failure[0]
        if isinstance(exc, ProviderError):
            raise exc
        raise ProviderError("provider call failed: %s" % exc) from exc
    return result[0] if result else None


@dataclass
class ProviderState:
    name: str
    status: str = "UNKNOWN"
    last_attempt_at: Optional[str] = None
    last_success_at: Optional[str] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "name": self.name,
            "status": self.status,
            "last_attempt_at": self.last_attempt_at,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
        }


class ProviderCoordinator:
    """Explicit primary/fallback/supplement composition, not a routing engine."""

    PRIMARY_QUOTE = "easyquotation-tencent"
    FALLBACK_QUOTE = "adata-sina"
    INTRADAY = "baidu-direct"

    def __init__(
        self,
        provider_factory: Callable[[str], Any] = build_provider,
        timeout_seconds: float = 10.0,
        retries: int = 1,
        backoff_seconds: float = 0.25,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.provider_factory = provider_factory
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self.sleep = sleep
        self.clock = clock
        self._providers: Dict[str, Any] = {}
        self._provider_errors: Dict[str, str] = {}
        self._state: Dict[str, ProviderState] = {
            name: ProviderState(name)
            for name in (self.PRIMARY_QUOTE, self.FALLBACK_QUOTE, self.INTRADAY)
        }

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(SHANGHAI_TZ).isoformat()

    def _get_provider(self, name: str) -> Any:
        if name not in self._providers:
            state = self._state[name]
            state.last_attempt_at = self._timestamp()
            try:
                self._providers[name] = self.provider_factory(name)
            except Exception as exc:
                self._provider_errors[name] = str(exc)
                state.status = "ERROR"
                state.last_error = "initialization: %s" % str(exc)[:500]
                raise ProviderError("%s initialization failed: %s" % (name, exc)) from exc
        return self._providers[name]

    def _call(self, provider_name: str, operation: str, function: Callable[[], Any]) -> Any:
        state = self._state[provider_name]
        last_error: Optional[BaseException] = None
        for attempt in range(self.retries + 1):
            state.last_attempt_at = self._timestamp()
            try:
                value = call_with_timeout(function, self.timeout_seconds)
                state.status = "OK"
                state.last_success_at = self._timestamp()
                state.last_error = None
                return value
            except Exception as exc:
                last_error = exc
                state.status = "ERROR"
                state.last_error = "%s: %s" % (type(exc).__name__, str(exc))[:500]
                if attempt < self.retries and self.backoff_seconds:
                    self.sleep(self.backoff_seconds * (2 ** attempt))
        assert last_error is not None
        if isinstance(last_error, ProviderError):
            raise last_error
        raise ProviderError(
            "%s %s failed after %d attempt(s): %s"
            % (provider_name, operation, self.retries + 1, last_error)
        ) from last_error

    def quotes(
        self, symbols: Sequence[str]
    ) -> Tuple[Dict[str, Quote], Dict[str, List[str]]]:
        """Fetch due quotes in one primary batch with per-symbol fallback.

        The fixed Phase 1D composition is intentionally kept explicit: one
        primary ``get_quotes`` call covers all normalized unique symbols, and a
        single fallback batch is limited to symbols whose primary row is
        missing or unusable. The returned error mapping preserves degraded
        primary failures even when fallback recovers that symbol.
        """

        codes = list(dict.fromkeys(normalize_code(symbol) for symbol in symbols))
        if not codes:
            return {}, {}

        quotes: Dict[str, Quote] = {}
        errors: Dict[str, List[str]] = {}
        primary_failures: List[str] = []

        try:
            provider = self._get_provider(self.PRIMARY_QUOTE)
            rows = self._call(
                self.PRIMARY_QUOTE,
                "get_quotes",
                lambda: provider.get_quotes(codes),
            )
        except Exception as exc:
            primary_error = "primary: %s" % str(exc)[:400]
            LOGGER.warning("primary quote batch failed: %s", exc)
            primary_failures = list(codes)
            for code in primary_failures:
                errors[code] = [primary_error]
        else:
            for code in codes:
                quote = self._find_quote(rows, code)
                if quote is not None and quote.price is not None and quote.previous_close is not None:
                    quotes[code] = quote
                    continue
                primary_failures.append(code)
                errors[code] = [
                    "primary: no usable quote row for %s" % code
                ]

        if primary_failures:
            try:
                provider = self._get_provider(self.FALLBACK_QUOTE)
                rows = self._call(
                    self.FALLBACK_QUOTE,
                    "get_quotes",
                    lambda: provider.get_quotes(primary_failures),
                )
            except Exception as exc:
                fallback_error = "fallback: %s" % str(exc)[:400]
                LOGGER.warning("fallback quote batch failed: %s", exc)
                for code in primary_failures:
                    errors.setdefault(code, []).append(fallback_error)
            else:
                for code in primary_failures:
                    quote = self._find_quote(rows, code)
                    if quote is not None and quote.price is not None and quote.previous_close is not None:
                        quotes[code] = quote
                    else:
                        errors.setdefault(code, []).append(
                            "fallback: no usable quote row for %s" % code
                        )

        return quotes, {code: messages for code, messages in errors.items() if messages}

    def quote(self, symbol: str) -> Quote:
        """Compatibility wrapper for callers that still request one symbol."""

        code = normalize_code(symbol)
        quotes, errors = self.quotes([code])
        quote = quotes.get(code)
        if quote is not None:
            return quote
        details = "; ".join(errors.get(code, ["quote unavailable"]))
        raise ProviderError("quote failed for %s: %s" % (code, details))

    def intraday(
        self,
        symbol: str,
        trading_date: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Sequence[IntradayBar]:
        code = normalize_code(symbol)
        provider = self._get_provider(self.INTRADAY)
        value = self._call(
            self.INTRADAY,
            "get_intraday",
            lambda: provider.get_intraday(code, trading_date, start_time, end_time),
        )
        if value is None:
            raise ProviderError("intraday returned None for %s" % code)
        return list(value)

    def resolve_symbol(self, symbol: str) -> SymbolRef:
        code = normalize_code(symbol)
        # The 1D.0 adapters normalize code locally. A quote is intentionally
        # requested as well because the Web confirmation flow needs a Chinese
        # name, while resolve_symbol alone may not provide one.
        primary_error: Optional[Exception] = None
        for provider_name in (self.PRIMARY_QUOTE, self.FALLBACK_QUOTE):
            try:
                provider = self._get_provider(provider_name)
                ref = self._call(
                    provider_name,
                    "resolve_symbol",
                    lambda provider=provider: provider.resolve_symbol(code),
                )
                if not isinstance(ref, SymbolRef):
                    raise ProviderError("provider returned a non-canonical SymbolRef")
                try:
                    quote = self._call(
                        provider_name,
                        "get_quotes",
                        lambda provider=provider: provider.get_quotes([code]),
                    )
                    quote_row = self._find_quote(quote, code)
                    if quote_row is not None and quote_row.name:
                        return SymbolRef(
                            code=ref.code,
                            exchange=ref.exchange,
                            provider_symbol=ref.provider_symbol,
                            name=quote_row.name,
                        )
                except Exception as quote_error:
                    LOGGER.info("name lookup failed for %s via %s: %s", code, provider_name, quote_error)
                if ref.name:
                    return ref
                raise ProviderError("provider returned no Chinese name for %s" % code)
            except Exception as exc:
                primary_error = exc
                LOGGER.warning("symbol resolve failed for %s via %s: %s", code, provider_name, exc)
        raise ProviderError(
            "symbol resolve failed for %s: %s" % (code, str(primary_error)[:300])
        ) from primary_error

    @staticmethod
    def _find_quote(rows: Any, code: str) -> Optional[Quote]:
        if rows is None:
            return None
        for row in rows:
            if isinstance(row, Quote) and normalize_code(row.code) == code:
                return row
        return None

    def status(self) -> Dict[str, Dict[str, Optional[str]]]:
        return {name: state.to_dict() for name, state in self._state.items()}

    def restore_status(self, value: Any) -> None:
        if not isinstance(value, Mapping):
            return
        for name, raw in value.items():
            if name not in self._state or not isinstance(raw, Mapping):
                continue
            state = self._state[name]
            for field in ("status", "last_attempt_at", "last_success_at", "last_error"):
                if field in raw and (raw[field] is None or isinstance(raw[field], str)):
                    setattr(state, field, raw[field])
