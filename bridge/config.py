"""Runtime knobs for EVA Voice Bridge. Tokens stay in env / OpenClaw files."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Optional


def _env_text(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or not value.strip() else value.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def load_gateway_token() -> str:
    explicit = os.getenv("EVA_VOICE_BRIDGE_GATEWAY_TOKEN") or os.getenv(
        "OPENCLAW_GATEWAY_TOKEN"
    )
    if explicit and explicit.strip():
        return explicit.strip()
    config_path = Path(
        _env_text("OPENCLAW_CONFIG", str(Path.home() / ".openclaw" / "openclaw.json"))
    )
    if not config_path.is_file():
        return ""
    try:
        payload = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    auth = (payload.get("gateway") or {}).get("auth") or {}
    token = auth.get("token")
    return token.strip() if isinstance(token, str) else ""


@dataclass(frozen=True)
class BridgeConfig:
    host: str = "127.0.0.1"
    port: int = 8090
    keepalive_ms: int = 10000
    talk_url: str = "ws://127.0.0.1:18789"
    talk_enabled: bool = True
    log_path: str = ":memory:"

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        talk_enabled = _env_text("EVA_VOICE_BRIDGE_TALK", "1") not in {"0", "false", "no"}
        return cls(
            host=_env_text("EVA_VOICE_BRIDGE_HOST", "127.0.0.1"),
            port=_env_int("EVA_VOICE_BRIDGE_PORT", 8090),
            keepalive_ms=_env_int("EVA_VOICE_BRIDGE_KEEPALIVE_MS", 10000),
            talk_url=_env_text("EVA_VOICE_BRIDGE_TALK_URL", "ws://127.0.0.1:18789"),
            talk_enabled=talk_enabled,
            log_path=_env_text("EVA_VOICE_BRIDGE_LOG", ":memory:"),
        )
