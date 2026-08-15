"""The smallest reusable Provider boundary for Phase 1D.0."""

from typing import Optional, Protocol, Sequence

from .models import IntradayBar, Quote, SymbolRef


class ProviderError(RuntimeError):
    """A provider request or response could not be used."""


class ProviderCapabilityError(ProviderError):
    """The candidate does not expose a required capability."""


class StockProvider(Protocol):
    """The only interface Stock Service should depend on at this stage."""

    name: str
    source: str

    def resolve_symbol(self, symbol: str) -> SymbolRef:
        ...

    def get_quotes(self, symbols: Sequence[str]) -> Sequence[Quote]:
        ...

    def get_intraday(
        self,
        symbol: str,
        trading_date: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Sequence[IntradayBar]:
        ...
