"""Runtime knobs for EVA Voice Bridge. Tokens stay in env / OpenClaw files."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping, Optional


def _env_text(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or not value.strip() else value.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _openclaw_config_path() -> Path:
    return Path(
        _env_text("OPENCLAW_CONFIG", str(Path.home() / ".openclaw" / "openclaw.json"))
    )


def _load_openclaw_config() -> dict[str, Any]:
    path = _openclaw_config_path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_exec_secret(payload: Mapping[str, Any], ref: Mapping[str, Any]) -> str:
    secret_id = ref.get("id")
    provider_name = ref.get("provider")
    if not isinstance(secret_id, str) or not isinstance(provider_name, str):
        return ""
    provider = ((payload.get("secrets") or {}).get("providers") or {}).get(
        provider_name
    ) or {}
    command = provider.get("command")
    if not isinstance(command, str) or not command:
        return ""
    args = provider.get("args") or []
    if not isinstance(args, list):
        return ""
    request = json.dumps(
        {
            "protocolVersion": 1,
            "provider": provider_name,
            "ids": [secret_id],
        }
    ).encode("utf-8")
    try:
        completed = subprocess.run(
            [command, *[str(item) for item in args]],
            input=request,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    try:
        body = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    value = (body.get("values") or {}).get(secret_id)
    return value.strip() if isinstance(value, str) else ""


def load_gateway_token() -> str:
    explicit = os.getenv("EVA_VOICE_BRIDGE_GATEWAY_TOKEN") or os.getenv(
        "OPENCLAW_GATEWAY_TOKEN"
    )
    if explicit and explicit.strip():
        return explicit.strip()
    payload = _load_openclaw_config()
    token = ((payload.get("gateway") or {}).get("auth") or {}).get("token")
    if isinstance(token, str):
        return token.strip()
    if isinstance(token, dict) and token.get("source") == "exec":
        return _resolve_exec_secret(payload, token)
    return ""


@dataclass(frozen=True)
class BridgeConfig:
    host: str = "127.0.0.1"
    port: int = 8090
    keepalive_ms: int = 10000
    talk_url: str = "ws://127.0.0.1:18789"
    talk_enabled: bool = True
    commit_silence_ms: int = 1000
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
            commit_silence_ms=_env_int("EVA_VOICE_BRIDGE_COMMIT_SILENCE_MS", 1000),
            log_path=_env_text("EVA_VOICE_BRIDGE_LOG", ":memory:"),
        )
