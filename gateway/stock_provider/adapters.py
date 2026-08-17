"""Small candidate adapters used by the Phase 1D.0 bake-off.

These adapters are deliberately thin. Each one owns the provider-specific
imports, field names, symbol prefixes, and conversion into the canonical
models. There is no cache, watchlist, HTTP API, routing, or secret handling in
this module.
"""

from datetime import datetime, time as clock_time, timedelta, timezone
import json
import math
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import IntradayBar, Quote, SymbolRef
from .protocol import ProviderCapabilityError, ProviderError


CHINA_TZ = timezone(timedelta(hours=8))
BAIDU_DIRECT_ENDPOINT = "https://finance.pae.baidu.com/selfselect/getstockquotation"
BAIDU_DIRECT_SOURCE = "Baidu direct quotation_minute_ab"


def normalize_code(symbol: str) -> str:
    """Return a six-digit A-share code or reject an ambiguous symbol."""

    value = str(symbol).strip().lower()
    if re.fullmatch(r"(?:sh|sz)?\d{6}", value) is None:
        raise ValueError("expected one six-digit A-share code: %r" % symbol)
    return value[-6:]


def exchange_for(code: str) -> str:
    return "SSE" if code.startswith(("6", "9")) else "SZSE"


def provider_prefix(code: str) -> str:
    return ("sh" if exchange_for(code) == "SSE" else "sz") + code


def _field(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def _records(frame: Any) -> List[Mapping[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return list(frame.to_dict(orient="records"))
    if isinstance(frame, Mapping):
        return [frame]
    return [item for item in frame if isinstance(item, Mapping)]


def _columns(frame: Any) -> List[str]:
    columns = getattr(frame, "columns", None)
    return [str(column) for column in columns] if columns is not None else []


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return None if result != result else result


def _timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=CHINA_TZ)
        return parsed.isoformat()
    text = str(value).strip()
    if not text or text.lower() in ("nan", "nat", "none"):
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y%m%d %H:%M:%S",
        "%Y%m%d %H:%M",
        "%Y%m%d%H%M%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=CHINA_TZ).isoformat()
        except ValueError:
            continue
    return text.replace(" ", "T")


def _status(
    price: Optional[float],
    limit_up: Optional[float],
    limit_down: Optional[float],
    source_status: Any = None,
) -> str:
    status_text = str(source_status or "").lower()
    if "停牌" in status_text or "suspend" in status_text:
        return "SUSPENDED"
    if price is None:
        return "UNKNOWN"
    if limit_up is not None and abs(price - limit_up) <= max(0.01, abs(limit_up) * 1e-6):
        return "LIMIT_UP"
    if limit_down is not None and abs(price - limit_down) <= max(0.01, abs(limit_down) * 1e-6):
        return "LIMIT_DOWN"
    return "NORMAL" if limit_up is not None or limit_down is not None else "UNKNOWN"


def quote_from_mapping(
    code: str,
    row: Mapping[str, Any],
    source: str,
) -> Quote:
    """Convert one provider row without exposing the provider row itself."""

    price = _number(_field(row, "最新价", "price", "now", "current", "现价"))
    previous_close = _number(
        _field(row, "昨收", "previous_close", "close", "pre_close", "昨收价")
    )
    change = _number(_field(row, "涨跌额", "change", "涨跌"))
    change_percent = _number(
        _field(row, "涨跌幅", "change_pct", "涨跌(%)", "change_percent")
    )
    if previous_close is None and price is not None and change is not None:
        previous_close = price - change
    if change is None and price is not None and previous_close is not None:
        change = price - previous_close
    if (
        change_percent is None
        and change is not None
        and previous_close not in (None, 0)
    ):
        change_percent = change / previous_close * 100

    date_value = _field(row, "date", "日期", "交易日期")
    time_value = _field(row, "time", "时间", "更新时间", "交易时间")
    raw_timestamp = _field(row, "datetime", "timestamp", "时间戳")
    if raw_timestamp is None and date_value is not None and time_value is not None:
        raw_timestamp = "%s %s" % (date_value, time_value)

    limit_up = _number(_field(row, "涨停价", "涨停", "limit_up", "up_limit"))
    limit_down = _number(_field(row, "跌停价", "跌停", "limit_down", "down_limit"))
    return Quote(
        code=code,
        name=_field(row, "名称", "name", "short_name", "股票名称"),
        price=price,
        previous_close=previous_close,
        change=change,
        change_percent=change_percent,
        status=_status(price, limit_up, limit_down, _field(row, "状态", "status")),
        timestamp=_timestamp(raw_timestamp),
        source=source,
        limit_up=limit_up,
        limit_down=limit_down,
    )


def intraday_from_mapping(
    code: str,
    row: Mapping[str, Any],
    source: str,
) -> Optional[IntradayBar]:
    raw_timestamp = _field(
        row,
        "时间",
        "日期",
        "datetime",
        "timestamp",
        "trade_time",
        "time",
    )
    timestamp = _timestamp(raw_timestamp)
    if timestamp is None:
        return None
    close = _number(_field(row, "收盘", "close", "price", "最新价"))
    price = _number(_field(row, "价格", "price", "最新价"))
    return IntradayBar(
        code=code,
        timestamp=timestamp,
        price=price if price is not None else close,
        open=_number(_field(row, "开盘", "open")),
        high=_number(_field(row, "最高", "high")),
        low=_number(_field(row, "最低", "low")),
        close=close,
        volume=_number(_field(row, "成交量", "volume")),
        amount=_number(_field(row, "成交额", "amount")),
        source=source,
    )


def _strict_trading_date(value: str) -> str:
    text = str(value).strip()
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("expected trading_date as YYYY-MM-DD: %r" % value) from exc
    if parsed.strftime("%Y-%m-%d") != text:
        raise ValueError("expected trading_date as YYYY-MM-DD: %r" % value)
    return text


def _baidu_epoch_timestamp(value: Any) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text or text in ("--", "-"):
        return None
    try:
        epoch = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(epoch) or epoch <= 0:
        return None
    if epoch >= 100000000000:
        epoch /= 1000
    try:
        parsed = datetime.fromtimestamp(epoch, tz=CHINA_TZ)
    except (OverflowError, OSError, ValueError):
        return None
    return parsed.isoformat()


def _baidu_explicit_timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=CHINA_TZ)
        else:
            parsed = parsed.astimezone(CHINA_TZ)
        return parsed.isoformat()
    return None


def _baidu_timestamp(row: Mapping[str, Any], index: int) -> str:
    timestamp = _baidu_epoch_timestamp(row.get("time"))
    if timestamp is None:
        timestamp = _baidu_explicit_timestamp(row.get("datetime"))
    if timestamp is None:
        raise ProviderError(
            "baidu-direct priceinfo row %d has no valid epoch or full date/time" % index
        )
    return timestamp


def _clock_bound(value: Optional[str], field_name: str) -> Optional[clock_time]:
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError("expected %s as HH:MM[:SS]: %r" % (field_name, value))


def parse_baidu_priceinfo(
    code: str,
    priceinfo: Sequence[Mapping[str, Any]],
    requested_date: str,
    source: str = BAIDU_DIRECT_SOURCE,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> List[IntradayBar]:
    """Convert Baidu's raw priceinfo while proving the returned date.

    Baidu includes closed-session filler rows whose volume and oriAmount are
    zero or ``--``. Those rows are intentionally excluded. The display
    ``amount`` field is not parsed because it may contain Chinese units;
    ``oriAmount`` is the only amount value admitted to the canonical model.
    """

    normalized_code = normalize_code(code)
    expected_date = _strict_trading_date(requested_date)
    start_clock = _clock_bound(start_time, "start_time")
    end_clock = _clock_bound(end_time, "end_time")
    if start_clock is not None and end_clock is not None and start_clock > end_clock:
        raise ValueError("start_time must not be after end_time")

    bars: List[IntradayBar] = []
    for index, row in enumerate(priceinfo):
        if not isinstance(row, Mapping):
            raise ProviderError("baidu-direct priceinfo row %d is not an object" % index)
        timestamp = _baidu_timestamp(row, index)
        observed_date = timestamp[:10]
        if observed_date != expected_date:
            raise ProviderError(
                "baidu-direct observed date %s does not match requested date %s"
                % (observed_date, expected_date)
            )

        local_time = datetime.fromisoformat(timestamp).timetz().replace(tzinfo=None)
        if start_clock is not None and local_time < start_clock:
            continue
        if end_clock is not None and local_time > end_clock:
            continue

        price = _number(row.get("price"))
        volume = _number(row.get("volume"))
        amount = _number(row.get("oriAmount"))
        has_activity = (volume is not None and volume > 0) or (
            amount is not None and amount > 0
        )
        if not has_activity:
            continue
        if price is None:
            raise ProviderError(
                "baidu-direct active priceinfo row %d has no numeric price" % index
            )
        bars.append(
            IntradayBar(
                code=normalized_code,
                timestamp=timestamp,
                price=price,
                open=None,
                high=None,
                low=None,
                close=price,
                volume=volume,
                amount=amount,
                source=source,
            )
        )

    bars.sort(key=lambda bar: bar.timestamp)
    return bars


class AkshareEastmoneyAdapter:
    """AKShare functions backed by Eastmoney public endpoints."""

    name = "akshare-eastmoney"
    source = "Eastmoney via AKShare"

    def __init__(self) -> None:
        self.last_quote_columns: List[str] = []
        self.last_intraday_columns: List[str] = []
        self._akshare = None
        self._symbol_rows: Optional[List[Mapping[str, Any]]] = None

    def _module(self) -> Any:
        if self._akshare is None:
            try:
                import akshare
            except ImportError as exc:
                raise ProviderError("akshare is not installed") from exc
            self._akshare = akshare
        return self._akshare

    def resolve_symbol(self, symbol: str) -> SymbolRef:
        code = normalize_code(symbol)
        if self._symbol_rows is None:
            try:
                table = self._module().stock_info_a_code_name()
                self._symbol_rows = _records(table)
            except Exception as exc:
                raise ProviderError("AKShare symbol resolution failed: %s" % exc) from exc
        for row in self._symbol_rows:
            row_code = str(_field(row, "code", "代码") or "").zfill(6)
            if row_code == code:
                return SymbolRef(
                    code=code,
                    exchange=exchange_for(code),
                    provider_symbol=code,
                    name=_field(row, "name", "名称"),
                )
        raise ProviderError("AKShare symbol not found: %s" % code)

    def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
        codes = [normalize_code(symbol) for symbol in symbols]
        try:
            frame = self._module().stock_zh_a_spot_em()
        except Exception as exc:
            raise ProviderError("AKShare/Eastmoney quote request failed: %s" % exc) from exc
        self.last_quote_columns = _columns(frame)
        rows = {
            str(_field(row, "代码", "code") or "").zfill(6): row
            for row in _records(frame)
        }
        return [
            quote_from_mapping(code, rows[code], self.source)
            for code in codes
            if code in rows
        ]

    def get_intraday(
        self,
        symbol: str,
        trading_date: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Sequence[IntradayBar]:
        code = normalize_code(symbol)
        start = "%s %s" % (trading_date, start_time or "00:00:00")
        end = "%s %s" % (trading_date, end_time or "23:59:59")
        try:
            frame = self._module().stock_zh_a_hist_min_em(
                symbol=code,
                start_date=start,
                end_date=end,
                period="1",
                adjust="",
            )
        except Exception as exc:
            raise ProviderError("AKShare/Eastmoney intraday request failed: %s" % exc) from exc
        self.last_intraday_columns = _columns(frame)
        return [
            bar
            for row in _records(frame)
            for bar in [intraday_from_mapping(code, row, self.source)]
            if bar is not None
        ]


class AdataAdapter:
    """adata's direct Sina or Tencent market object."""

    def __init__(self, market: str) -> None:
        if market not in ("sina", "tencent"):
            raise ValueError("unsupported adata market: %s" % market)
        self.market_name = market
        self.name = "adata-%s" % market
        self.source = "%s via adata" % ("Sina" if market == "sina" else "Tencent")
        self.last_quote_columns: List[str] = []
        self.last_intraday_columns: List[str] = []
        self._market = None

    def _object(self) -> Any:
        if self._market is None:
            try:
                import adata
            except ImportError as exc:
                raise ProviderError("adata is not installed") from exc
            self._market = (
                adata.stock.market.sina_market
                if self.market_name == "sina"
                else adata.stock.market.qq_market
            )
        return self._market

    def resolve_symbol(self, symbol: str) -> SymbolRef:
        code = normalize_code(symbol)
        return SymbolRef(
            code=code,
            exchange=exchange_for(code),
            provider_symbol=code,
        )

    def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
        codes = [normalize_code(symbol) for symbol in symbols]
        try:
            frame = self._object().list_market_current(code_list=codes)
        except Exception as exc:
            raise ProviderError("adata/%s quote request failed: %s" % (self.market_name, exc)) from exc
        self.last_quote_columns = _columns(frame)
        rows = {
            str(_field(row, "stock_code", "代码") or "").zfill(6): row
            for row in _records(frame)
        }
        return [
            quote_from_mapping(code, rows[code], self.source)
            for code in codes
            if code in rows
        ]

    def get_intraday(
        self,
        symbol: str,
        trading_date: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Sequence[IntradayBar]:
        del trading_date, start_time, end_time
        code = normalize_code(symbol)
        try:
            frame = self._object().get_market_min(stock_code=code)
        except Exception as exc:
            raise ProviderError("adata/%s intraday request failed: %s" % (self.market_name, exc)) from exc
        if frame is None:
            raise ProviderError(
                "adata/%s intraday returned None (library handler hid the upstream error)"
                % self.market_name
            )
        self.last_intraday_columns = _columns(frame)
        return [
            bar
            for row in _records(frame)
            for bar in [intraday_from_mapping(code, row, self.source)]
            if bar is not None
        ]


class EasyQuotationAdapter:
    """easyquotation Sina/Tencent quotes with optional Tencent timekline."""

    def __init__(self, market: str) -> None:
        if market not in ("sina", "tencent"):
            raise ValueError("unsupported easyquotation market: %s" % market)
        self.market_name = market
        self.name = "easyquotation-%s" % market
        self.source = "Sina via easyquotation" if market == "sina" else "Tencent via easyquotation"
        self.last_quote_columns: List[str] = []
        self.last_intraday_columns: List[str] = []

    def _module(self) -> Any:
        try:
            import easyquotation
        except ImportError as exc:
            raise ProviderError("easyquotation is not installed") from exc
        return easyquotation

    def resolve_symbol(self, symbol: str) -> SymbolRef:
        code = normalize_code(symbol)
        return SymbolRef(
            code=code,
            exchange=exchange_for(code),
            provider_symbol=provider_prefix(code),
        )

    def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
        codes = [normalize_code(symbol) for symbol in symbols]
        provider_codes = [provider_prefix(code) for code in codes]
        try:
            payload = self._module().use(self.market_name).stocks(provider_codes)
        except Exception as exc:
            raise ProviderError(
                "easyquotation/%s quote request failed: %s" % (self.market_name, exc)
            ) from exc
        if not isinstance(payload, Mapping):
            raise ProviderError("easyquotation/%s returned a non-mapping response" % self.market_name)
        self.last_quote_columns = sorted(
            {str(field) for row in payload.values() if isinstance(row, Mapping) for field in row}
        )
        rows: Dict[str, Mapping[str, Any]] = {}
        for key, row in payload.items():
            if not isinstance(row, Mapping):
                continue
            match = re.findall(r"\d{6}", str(key))
            if match:
                rows[match[-1]] = row
        return [
            quote_from_mapping(code, rows[code], self.source)
            for code in codes
            if code in rows
        ]

    def get_intraday(
        self,
        symbol: str,
        trading_date: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Sequence[IntradayBar]:
        del start_time, end_time
        code = normalize_code(symbol)
        if self.market_name == "sina":
            raise ProviderCapabilityError(
                "easyquotation/sina exposes quote fields only; no current one-minute adapter"
            )
        try:
            payload = self._module().use("timekline").stocks([provider_prefix(code)])
        except Exception as exc:
            raise ProviderError(
                "easyquotation/timekline request failed: %s" % exc
            ) from exc
        self.last_intraday_columns = ["date", "time_data"]
        bars: List[IntradayBar] = []
        for row in payload.values() if isinstance(payload, Mapping) else []:
            if not isinstance(row, Mapping):
                continue
            response_date = str(row.get("date") or "")
            for point in row.get("time_data") or []:
                if len(point) < 3:
                    continue
                hhmm = str(point[0]).zfill(4)
                raw_timestamp = "%s %s:%s:00" % (
                    response_date,
                    hhmm[:2],
                    hhmm[2:],
                )
                timestamp = _timestamp(raw_timestamp)
                if timestamp is None:
                    continue
                price = _number(point[1])
                bars.append(
                    IntradayBar(
                        code=code,
                        timestamp=timestamp,
                        price=price,
                        open=None,
                        high=None,
                        low=None,
                        close=price,
                        volume=_number(point[2]),
                        amount=None,
                        source="Tencent timekline via easyquotation",
                    )
                )
        if not bars:
            raise ProviderError("easyquotation/timekline returned no one-minute rows")
        return bars


class BaiduDirectAdapter:
    """Direct Baidu one-minute supplement, independent of adata's parser."""

    name = "baidu-direct"
    source = BAIDU_DIRECT_SOURCE

    def __init__(
        self,
        timeout: float = 15.0,
        opener: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.timeout = timeout
        self._opener = opener or urlopen
        self.last_quote_columns: List[str] = []
        self.last_intraday_columns: List[str] = [
            "time",
            "price",
            "volume",
            "oriAmount",
            "datetime",
            "timeKey",
        ]

    def resolve_symbol(self, symbol: str) -> SymbolRef:
        code = normalize_code(symbol)
        return SymbolRef(
            code=code,
            exchange=exchange_for(code),
            provider_symbol=code,
        )

    def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
        del symbols
        raise ProviderCapabilityError(
            "baidu-direct is an intraday-only supplement; quote is unsupported"
        )

    def _request_json(self, code: str) -> Mapping[str, Any]:
        query = {
            "all": "1",
            "isIndex": "false",
            "isBk": "false",
            "isBlock": "false",
            "isFutures": "false",
            "isStock": "true",
            "newFormat": "1",
            "group": "quotation_minute_ab",
            "finClientType": "pc",
            "code": code,
        }
        request = Request(
            "%s?%s" % (BAIDU_DIRECT_ENDPOINT, urlencode(query)),
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; Phase-1D0-provider-bakeoff)",
            },
        )
        try:
            response = self._opener(request, timeout=self.timeout)
            try:
                raw = response.read()
            finally:
                close = getattr(response, "close", None)
                if close is not None:
                    close()
        except Exception as exc:
            raise ProviderError("baidu-direct request failed: %s" % exc) from exc
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            raise ProviderError("baidu-direct returned malformed JSON") from exc
        if not isinstance(payload, Mapping):
            raise ProviderError("baidu-direct returned a non-object JSON response")
        return payload

    def get_intraday(
        self,
        symbol: str,
        trading_date: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Sequence[IntradayBar]:
        code = normalize_code(symbol)
        expected_date = _strict_trading_date(trading_date)
        payload = self._request_json(code)
        if str(payload.get("ResultCode")) != "0":
            raise ProviderError(
                "baidu-direct ResultCode=%s" % payload.get("ResultCode")
            )
        result = payload.get("Result")
        if not isinstance(result, Mapping):
            raise ProviderError("baidu-direct response has no Result object")
        priceinfo = result.get("priceinfo")
        if not isinstance(priceinfo, list) or not priceinfo:
            raise ProviderError("baidu-direct response has no priceinfo rows")
        return parse_baidu_priceinfo(
            code,
            priceinfo,
            expected_date,
            source=self.source,
            start_time=start_time,
            end_time=end_time,
        )


def build_provider(name: str) -> Any:
    builders = {
        "akshare-eastmoney": AkshareEastmoneyAdapter,
        "adata-sina": lambda: AdataAdapter("sina"),
        "adata-tencent": lambda: AdataAdapter("tencent"),
        "easyquotation-sina": lambda: EasyQuotationAdapter("sina"),
        "easyquotation-tencent": lambda: EasyQuotationAdapter("tencent"),
        "baidu-direct": BaiduDirectAdapter,
    }
    try:
        return builders[name]()
    except KeyError as exc:
        raise ValueError("unknown provider: %s" % name) from exc
