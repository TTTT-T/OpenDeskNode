"""Runtime configuration for the LAN-only Stock Gateway.

Configuration is intentionally small and environment driven so the same
application can run in a local test database or in the NAS data volume.
Provider credentials are not part of this module; the Phase 1D provider
combination uses public endpoints only.
"""

from dataclasses import dataclass
import os
from pathlib import Path


def _env_text(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or not value.strip() else value.strip()


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("%s must be a number" % name) from exc
    if value < minimum:
        raise ValueError("%s must be >= %s" % (name, minimum))
    return value


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("%s must be an integer" % name) from exc
    if value < minimum:
        raise ValueError("%s must be >= %s" % (name, minimum))
    return value


@dataclass(frozen=True)
class GatewayConfig:
    """Bounded runtime knobs for one gateway process."""

    database_path: str = "data/stock-gateway.sqlite3"
    log_path: str = "data/logs/stock-gateway.log"
    host: str = "0.0.0.0"
    port: int = 8000
    public_hostname: str = "stock-gateway.local"
    quote_ttl_seconds: float = 5.0
    intraday_ttl_seconds: float = 30.0
    off_market_refresh_seconds: float = 300.0
    stale_seconds: float = 300.0
    provider_timeout_seconds: float = 10.0
    provider_retries: int = 1
    provider_backoff_seconds: float = 0.25
    max_intraday_bars: int = 600

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.quote_ttl_seconds < 0 or self.intraday_ttl_seconds < 0:
            raise ValueError("cache TTLs must be non-negative")
        if self.off_market_refresh_seconds <= 0:
            raise ValueError("off_market_refresh_seconds must be positive")
        if self.stale_seconds <= 0:
            raise ValueError("stale_seconds must be positive")
        if self.provider_timeout_seconds <= 0:
            raise ValueError("provider_timeout_seconds must be positive")
        if self.provider_retries < 0 or self.provider_retries > 3:
            raise ValueError("provider_retries must be between 0 and 3")
        if self.provider_backoff_seconds < 0:
            raise ValueError("provider_backoff_seconds must be non-negative")
        if self.max_intraday_bars < 240 or self.max_intraday_bars > 2000:
            raise ValueError("max_intraday_bars must be between 240 and 2000")

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        return cls(
            database_path=_env_text(
                "STOCK_GATEWAY_DB_PATH", "data/stock-gateway.sqlite3"
            ),
            log_path=_env_text(
                "STOCK_GATEWAY_LOG_PATH", "data/logs/stock-gateway.log"
            ),
            host=_env_text("STOCK_GATEWAY_HOST", "0.0.0.0"),
            port=_env_int("STOCK_GATEWAY_PORT", 8000, minimum=1),
            public_hostname=_env_text(
                "STOCK_GATEWAY_PUBLIC_HOSTNAME", "stock-gateway.local"
            ),
            quote_ttl_seconds=_env_float(
                "STOCK_GATEWAY_QUOTE_TTL_SECONDS", 5.0
            ),
            intraday_ttl_seconds=_env_float(
                "STOCK_GATEWAY_INTRADAY_TTL_SECONDS", 30.0
            ),
            off_market_refresh_seconds=_env_float(
                "STOCK_GATEWAY_OFF_MARKET_REFRESH_SECONDS", 300.0, minimum=1.0
            ),
            stale_seconds=_env_float(
                "STOCK_GATEWAY_STALE_SECONDS", 300.0, minimum=1.0
            ),
            provider_timeout_seconds=_env_float(
                "STOCK_GATEWAY_PROVIDER_TIMEOUT_SECONDS", 10.0, minimum=0.1
            ),
            provider_retries=_env_int(
                "STOCK_GATEWAY_PROVIDER_RETRIES", 1, minimum=0
            ),
            provider_backoff_seconds=_env_float(
                "STOCK_GATEWAY_PROVIDER_BACKOFF_SECONDS", 0.25
            ),
            max_intraday_bars=_env_int(
                "STOCK_GATEWAY_MAX_INTRADAY_BARS", 600, minimum=240
            ),
        )

    def ensure_local_directories(self) -> None:
        """Create only application-owned parent directories."""

        for value in (self.database_path, self.log_path):
            if value == ":memory:":
                continue
            Path(value).expanduser().parent.mkdir(parents=True, exist_ok=True)
