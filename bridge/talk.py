"""OpenClaw Talk client. FakeTalk is the C0 test double; live WS is optional."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Awaitable, Callable, Optional, Protocol

LOGGER = logging.getLogger("eva.bridge.talk")

TalkListener = Callable[[dict[str, Any]], Optional[Awaitable[None]]]


class TalkClient(Protocol):
    async def create_session(self) -> dict[str, Any]:
        ...

    async def append_audio(
        self, session_id: str, pcm24: bytes, timestamp: Optional[float] = None
    ) -> None:
        ...

    async def cancel_output(self, session_id: str, reason: str = "barge-in") -> None:
        ...

    async def close_session(self, session_id: str) -> None:
        ...

    def set_listener(self, listener: Optional[TalkListener]) -> None:
        ...

    @property
    def connected(self) -> bool:
        ...


class FakeTalkClient:
    """Deterministic Talk stand-in for host tests. No STT/TTS/LLM."""

    def __init__(self, auto_reply_pcm24: bytes = b""):
        self.auto_reply_pcm24 = auto_reply_pcm24
        self.created: list[str] = []
        self.appended: list[tuple[str, bytes]] = []
        self.cancelled: list[tuple[str, str]] = []
        self.closed: list[str] = []
        self._listener: Optional[TalkListener] = None
        self._n = 0

    @property
    def connected(self) -> bool:
        return True

    def set_listener(self, listener: Optional[TalkListener]) -> None:
        self._listener = listener

    async def _emit(self, event: dict[str, Any]) -> None:
        if self._listener is None:
            return
        result = self._listener(event)
        if asyncio.iscoroutine(result):
            await result

    async def create_session(self) -> dict[str, Any]:
        self._n += 1
        session_id = "talk-fake-%d" % self._n
        self.created.append(session_id)
        await self._emit(
            {
                "type": "ready",
                "sessionId": session_id,
                "talkEvent": {"type": "session.ready"},
            }
        )
        return {
            "sessionId": session_id,
            "mode": "realtime",
            "transport": "gateway-relay",
            "brain": "agent-consult",
        }

    async def append_audio(
        self, session_id: str, pcm24: bytes, timestamp: Optional[float] = None
    ) -> None:
        self.appended.append((session_id, pcm24))
        await self._emit(
            {
                "type": "inputAudio",
                "sessionId": session_id,
                "byteLength": len(pcm24),
                "timestamp": timestamp,
                "talkEvent": {"type": "input.audio.delta"},
            }
        )

    async def emit_output(self, session_id: str, pcm24: bytes) -> None:
        await self._emit(
            {
                "type": "audio",
                "sessionId": session_id,
                "audioBase64": __import__("base64").b64encode(pcm24).decode("ascii"),
                "talkEvent": {"type": "output.audio.delta"},
            }
        )
        await self._emit(
            {
                "type": "audio_done",
                "sessionId": session_id,
                "talkEvent": {"type": "output.audio.done"},
            }
        )

    async def cancel_output(self, session_id: str, reason: str = "barge-in") -> None:
        self.cancelled.append((session_id, reason))
        await self._emit(
            {
                "type": "clear",
                "sessionId": session_id,
                "reason": reason,
                "talkEvent": {"type": "turn.cancelled"},
            }
        )

    async def close_session(self, session_id: str) -> None:
        self.closed.append(session_id)
        await self._emit(
            {
                "type": "close",
                "sessionId": session_id,
                "reason": "completed",
                "talkEvent": {"type": "session.closed"},
            }
        )

    async def maybe_auto_reply(self, session_id: str) -> None:
        if self.auto_reply_pcm24:
            await self.emit_output(session_id, self.auto_reply_pcm24)


class GatewayTalkClient:
    def __init__(self, url: str, token: str):
        self.url = url
        self._token = token
        self._listener: Optional[TalkListener] = None
        self._ws = None
        self._pending: dict[str, asyncio.Future] = {}
        self._reader: Optional[asyncio.Task] = None
        self._connected = False
        self.stats = {
            "events": 0,
            "event_names": [],
            "payload_types": [],
            "talk_event_types": [],
            "append_ok": 0,
            "append_fail": 0,
        }
        self._ready_sessions: set[str] = set()
        self._ready_waiters: dict[str, asyncio.Event] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    def set_listener(self, listener: Optional[TalkListener]) -> None:
        self._listener = listener

    async def connect(self) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("websockets is required for live Talk") from exc
        self._ws = await websockets.connect(self.url, max_size=8 * 1024 * 1024)
        challenge = json.loads(await self._ws.recv())
        if challenge.get("event") != "connect.challenge":
            raise RuntimeError("expected connect.challenge")
        req_id = str(uuid.uuid4())
        await self._ws.send(
            json.dumps(
                {
                    "type": "req",
                    "id": req_id,
                    "method": "connect",
                    "params": {
                        "minProtocol": 3,
                        "maxProtocol": 4,
                        "client": {
                            "id": "gateway-client",
                            "version": "0.1.0-c0",
                            "platform": "macos",
                            "mode": "backend",
                        },
                        "role": "operator",
                        "scopes": ["operator.read", "operator.write"],
                        "caps": [],
                        "commands": [],
                        "permissions": {},
                        "auth": {"token": self._token},
                        "userAgent": "eva-voice-bridge/0.1.0-c0",
                    },
                }
            )
        )
        while True:
            hello = json.loads(await self._ws.recv())
            if hello.get("type") == "res" and hello.get("id") == req_id:
                break
        if not hello.get("ok"):
            error = hello.get("error") or {}
            raise RuntimeError(
                "Talk connect failed: %s" % (error.get("message") or error.get("code") or "unknown")
            )
        self._connected = True
        self._reader = asyncio.create_task(self._read_loop())

    def _mark_ready(self, session_id: str) -> None:
        if session_id:
            self._ready_sessions.add(session_id)
            waiter = self._ready_waiters.get(session_id)
            if waiter is not None:
                waiter.set()
            return
        for waiter in self._ready_waiters.values():
            waiter.set()

    async def _wait_ready(self, session_id: str, timeout: float) -> None:
        if session_id in self._ready_sessions:
            return
        waiter = self._ready_waiters.setdefault(session_id, asyncio.Event())
        try:
            await asyncio.wait_for(waiter.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            LOGGER.warning("Talk session ready timed out")
        finally:
            self._ready_waiters.pop(session_id, None)

    async def close(self) -> None:
        self._connected = False
        if self._reader is not None:
            self._reader.cancel()
        if self._ws is not None:
            await self._ws.close()

    async def create_session(self) -> dict[str, Any]:
        response = await self._request(
            "talk.session.create",
            {
                "mode": "realtime",
                "transport": "gateway-relay",
                "brain": "agent-consult",
            },
        )
        if not response.get("ok"):
            error = response.get("error") or {}
            raise RuntimeError(
                "talk.session.create failed: %s"
                % (error.get("message") or error.get("code") or "unknown")
            )
        payload = response.get("payload") or {}
        session_id = payload.get("sessionId")
        if isinstance(session_id, str) and session_id:
            await self._wait_ready(session_id, timeout=12)
        return payload

    async def append_audio(
        self, session_id: str, pcm24: bytes, timestamp: Optional[float] = None
    ) -> None:
        import base64

        params: dict[str, Any] = {
            "sessionId": session_id,
            "audioBase64": base64.b64encode(pcm24).decode("ascii"),
        }
        if timestamp is not None:
            params["timestamp"] = timestamp
        response = await self._request("talk.session.appendAudio", params)
        if not response.get("ok"):
            self.stats["append_fail"] += 1
            error = response.get("error") or {}
            raise RuntimeError(
                "talk.session.appendAudio failed: %s"
                % (error.get("message") or error.get("code") or "unknown")
            )
        self.stats["append_ok"] += 1

    async def cancel_output(self, session_id: str, reason: str = "barge-in") -> None:
        response = await self._request(
            "talk.session.cancelOutput",
            {"sessionId": session_id, "reason": reason},
        )
        if not response.get("ok"):
            LOGGER.warning("cancelOutput rejected")

    async def close_session(self, session_id: str) -> None:
        await self._request("talk.session.close", {"sessionId": session_id})

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("Talk client not connected")
        req_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        await self._ws.send(
            json.dumps({"type": "req", "id": req_id, "method": method, "params": params})
        )
        return await asyncio.wait_for(future, timeout=20)

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                message = json.loads(raw)
                kind = message.get("type")
                if kind == "res":
                    future = self._pending.pop(message.get("id"), None)
                    if future is not None and not future.done():
                        future.set_result(message)
                    continue
                if kind == "event":
                    name = str(message.get("event") or "")
                    self.stats["events"] += 1
                    if name and name not in self.stats["event_names"]:
                        self.stats["event_names"].append(name)
                    payload = message.get("payload") or {}
                    payload_type = payload.get("type") if isinstance(payload, dict) else None
                    if payload_type and payload_type not in self.stats["payload_types"]:
                        self.stats["payload_types"].append(payload_type)
                    talk_type = None
                    if isinstance(payload, dict):
                        talk_event = payload.get("talkEvent") or {}
                        if isinstance(talk_event, dict):
                            talk_type = talk_event.get("type")
                    if talk_type and talk_type not in self.stats["talk_event_types"]:
                        self.stats["talk_event_types"].append(talk_type)
                    session_id = ""
                    if isinstance(payload, dict):
                        session_id = str(
                            payload.get("sessionId")
                            or payload.get("relaySessionId")
                            or ""
                        )
                    if payload_type == "ready" or talk_type == "session.ready":
                        self._mark_ready(session_id)
                    if name == "talk.event" and self._listener is not None:
                        result = self._listener(payload)
                        if asyncio.iscoroutine(result):
                            await result
        except asyncio.CancelledError:
            return
        except Exception:
            LOGGER.exception("Talk read loop failed")
            self._connected = False
