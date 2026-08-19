"""EVA Voice Bridge HTTP/WebSocket surface."""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .config import BridgeConfig, load_gateway_token
from .protocol import ProtocolError, hello_error
from .session import DeviceSession
from .talk import FakeTalkClient, GatewayTalkClient

LOGGER = logging.getLogger("eva.bridge")


def create_app(
    config: Optional[BridgeConfig] = None,
    talk=None,
) -> FastAPI:
    runtime = config or BridgeConfig.from_env()
    state: dict[str, Any] = {
        "config": runtime,
        "talk": talk,
        "conversations": 0,
    }

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if state["talk"] is None:
            if not runtime.talk_enabled:
                state["talk"] = FakeTalkClient()
            else:
                token = load_gateway_token()
                if not token:
                    LOGGER.warning("no gateway token; Talk disabled, FakeTalk active")
                    state["talk"] = FakeTalkClient()
                else:
                    client = GatewayTalkClient(runtime.talk_url, token)
                    try:
                        await client.connect()
                        state["talk"] = client
                    except Exception:
                        LOGGER.exception("Talk connect failed; FakeTalk fallback")
                        state["talk"] = FakeTalkClient()
        try:
            yield
        finally:
            client = state.get("talk")
            closer = getattr(client, "close", None)
            if closer is not None:
                result = closer()
                if hasattr(result, "__await__"):
                    await result

    app = FastAPI(title="EVA Voice Bridge", version="0.1.0-c0", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        client = state.get("talk")
        return JSONResponse(
            {
                "ok": True,
                "service": "eva-voice-bridge",
                "talk_connected": bool(getattr(client, "connected", False)),
                "talk_kind": type(client).__name__ if client else None,
                "conversations": state["conversations"],
            }
        )

    @app.websocket("/voice/v0")
    async def voice(websocket: WebSocket) -> None:
        await websocket.accept()
        client = state["talk"]
        if client is None:
            await websocket.close()
            return
        session = DeviceSession(
            talk=client,
            send_text=websocket.send_json,
            send_bytes=websocket.send_bytes,
            keepalive_ms=runtime.keepalive_ms,
            conversation_id=state["conversations"] + 1,
            commit_silence_ms=runtime.commit_silence_ms,
        )
        state["conversations"] += 1
        state["current_session"] = session
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("text") is not None:
                    try:
                        payload = json.loads(message["text"])
                    except json.JSONDecodeError:
                        await websocket.send_json(hello_error("invalid_message", "json"))
                        break
                    try:
                        await session.handle_text(payload)
                    except ProtocolError as exc:
                        await websocket.send_json(
                            {"type": "error", "code": exc.code, "message": exc.message}
                        )
                        if not session.helloed:
                            break
                elif message.get("bytes") is not None:
                    try:
                        await session.handle_binary(message["bytes"])
                    except ProtocolError:
                        session.metrics["dropped_old"] += 1
        except WebSocketDisconnect:
            pass
        finally:
            state["last_metrics"] = dict(session.metrics)
            state["last_device_id"] = session.device_id
            if state.get("current_session") is session:
                state["current_session"] = None
            await session.close()

    @app.get("/metrics")
    async def metrics() -> JSONResponse:
        client = state.get("talk")
        current = state.get("current_session")
        return JSONResponse(
            {
                "ok": True,
                "talk_kind": type(client).__name__ if client else None,
                "talk_connected": bool(getattr(client, "connected", False)),
                "talk_stats": dict(getattr(client, "stats", {}) or {}),
                "device_id": getattr(current, "device_id", None) or state.get("last_device_id"),
                "helloed": bool(getattr(current, "helloed", False)),
                "conversation_id": getattr(current, "conversation_id", None),
                "metrics": dict(getattr(current, "metrics", None) or state.get("last_metrics") or {}),
                "conversations": state["conversations"],
                "commit_silence_ms": runtime.commit_silence_ms,
            }
        )

    app.state.bridge = state
    return app
