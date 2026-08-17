"""Provider-neutral models owned by the Stock Gateway.

The existing ``gateway.stock_provider`` models describe the adapter boundary.
These models add only cache and gateway concerns; provider-specific rows never
cross into the API or SQLite snapshot.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


MARKET_STATUSES = (
    "NORMAL",
    "LIMIT_UP",
    "LIMIT_DOWN",
    "SUSPENDED",
    "UNKNOWN",
)


@dataclass(frozen=True)
class DeviceRecord:
    device_id: str
    name: str
    created_at: str
    last_accessed_at: Optional[str]

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
        }


@dataclass(frozen=True)
class WatchlistSlot:
    slot: int
    symbol: str
    name: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"slot": self.slot, "symbol": self.symbol, "name": self.name}


@dataclass(frozen=True)
class GatewayBar:
    timestamp: str
    price: Optional[float]
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[float]
    amount: Optional[float]
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "price": self.price,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "GatewayBar":
        return cls(
            timestamp=str(value["timestamp"]),
            price=value.get("price"),
            open=value.get("open"),
            high=value.get("high"),
            low=value.get("low"),
            close=value.get("close"),
            volume=value.get("volume"),
            amount=value.get("amount"),
            source=str(value.get("source") or "unknown"),
        )


@dataclass
class GatewaySnapshot:
    """The latest successful-or-partial snapshot for one symbol.

    ``last_success_at`` is a local gateway timestamp for the most recent
    successful quote or intraday update. ``quote_data_timestamp`` and
    ``intraday_data_timestamp`` are timestamps supplied by the source data;
    they are never replaced with a local clock when the source omitted them.
    """

    symbol: str
    name: Optional[str] = None
    current_price: Optional[float] = None
    previous_close: Optional[float] = None
    change_amount: Optional[float] = None
    change_percent: Optional[float] = None
    status: str = "UNKNOWN"
    intraday: Tuple[GatewayBar, ...] = field(default_factory=tuple)
    intraday_session_date: Optional[str] = None
    quote_data_timestamp: Optional[str] = None
    intraday_data_timestamp: Optional[str] = None
    last_success_at: Optional[str] = None
    quote_fetched_at: Optional[str] = None
    intraday_fetched_at: Optional[str] = None
    quote_source: Optional[str] = None
    intraday_source: Optional[str] = None
    last_error: Optional[str] = None

    @classmethod
    def empty(cls, symbol: str) -> "GatewaySnapshot":
        return cls(symbol=symbol)

    @property
    def data_timestamp(self) -> Optional[str]:
        values = [
            value
            for value in (
                self.quote_data_timestamp,
                self.intraday_data_timestamp,
            )
            if value
        ]
        return max(values) if values else None

    def to_api_dict(self, freshness: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "current_price": self.current_price,
            "previous_close": self.previous_close,
            "change_amount": self.change_amount,
            "change_percent": self.change_percent,
            "status": self.status if self.status in MARKET_STATUSES else "UNKNOWN",
            "intraday": [bar.to_dict() for bar in self.intraday],
            "data_timestamp": self.data_timestamp,
            "quote_data_timestamp": self.quote_data_timestamp,
            "intraday_data_timestamp": self.intraday_data_timestamp,
            "intraday_session_date": self.intraday_session_date,
            "last_success_at": self.last_success_at,
            "quote_source": self.quote_source,
            "intraday_source": self.intraday_source,
            "freshness": freshness,
            "stale": bool(freshness.get("stale")),
            "last_error": self.last_error,
        }
