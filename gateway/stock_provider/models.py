"""Canonical stock data used between a provider adapter and Stock Service.

The model intentionally stays small for Phase 1D.0. Provider-specific fields
remain inside adapters and the bake-off audit; they are not leaked through
the boundary.
"""

from dataclasses import dataclass
from typing import Optional


MARKET_STATUSES = (
    "NORMAL",
    "LIMIT_UP",
    "LIMIT_DOWN",
    "SUSPENDED",
    "UNKNOWN",
)


@dataclass(frozen=True)
class SymbolRef:
    """A normalized six-digit A-share code and its provider-facing symbol."""

    code: str
    exchange: str
    provider_symbol: str
    name: Optional[str] = None


@dataclass(frozen=True)
class Quote:
    """Provider-neutral latest quote.

    UNKNOWN is intentionally available during the bake-off when a source does
    not expose enough information to prove a limit or suspension state. A
    later production adapter may only emit the product-visible statuses after
    it has a reliable limit-price/master-data source.
    """

    code: str
    name: Optional[str]
    price: Optional[float]
    previous_close: Optional[float]
    change: Optional[float]
    change_percent: Optional[float]
    status: str
    timestamp: Optional[str]
    source: str
    limit_up: Optional[float] = None
    limit_down: Optional[float] = None


@dataclass(frozen=True)
class IntradayBar:
    """One canonical one-minute observation."""

    code: str
    timestamp: str
    price: Optional[float]
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[float]
    amount: Optional[float]
    source: str
