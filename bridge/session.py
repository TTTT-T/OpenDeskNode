"""One device connection: protocol translation + audio path. No agent logic."""

from __future__ import annotations

import base64
import logging
import time
from typing import Any, Awaitable, Callable, Optional

from .audio import FrameSplitter, TALK_HZ, downsample_24k_to_16k, upsample_16k_to_24k
from .protocol import (
    FLAG_UTTERANCE_END,
    FLAG_UTTERANCE_START,
    FRAME_BYTES,
    ProtocolError,
    control,
    conversation_opened,
    hello_error,
    hello_ok,
    pack_audio_frame,
    unpack_audio_frame,
    validate_hello,
)

LOGGER = logging.getLogger("eva.bridge.session")

SendText = Callable[[dict[str, Any]], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]


class DeviceSession:
    def __init__(
        self,
        talk,
        send_text: SendText,
        send_bytes: SendBytes,
        keepalive_ms: int = 10000,
        conversation_id: int = 1,
        commit_silence_ms: int = 1000,
    ):
        self.talk = talk
        self._send_text = send_text
        self._send_bytes = send_bytes
        self.keepalive_ms = keepalive_ms
        self.commit_silence_ms = commit_silence_ms
        self.device_id = ""
        self.helloed = False
        self.conversation_id = conversation_id
        self.talk_session_id: Optional[str] = None
        self.playing = False
        self.uplink_seq_seen = -1
        self.down_seq = 0
        self.metrics = {
            "uplink_bytes": 0,
            "downlink_bytes": 0,
            "uplink_frames": 0,
            "downlink_frames": 0,
            "playback_starts": 0,
            "playback_ends": 0,
            "downlink_peak": 0,
            "dropped_old": 0,
            "seq_dup": 0,
            "seq_gap": 0,
            "seq_reorder": 0,
            "commit_silence_bytes": 0,
            "uplink_peak": 0,
            # Session-scoped Realtime user transcripts (talk transcript.* events
            # that passed the sessionId filter); each entry is
            # {"text", "talkType", "ts"}.
            "user_transcripts": [],
            "last_user_transcript": None,
        }
        self._uplink_pcm = bytearray()
        self._downlink_pcm = bytearray()
        self._up = upsample_16k_to_24k()
        self._down = downsample_24k_to_16k()
        self._down_frames = FrameSplitter()
        talk.set_listener(self.on_talk_event)

    async def close(self) -> None:
        talk_id = self.talk_session_id
        self.talk_session_id = None
        if talk_id:
            try:
                await self.talk.close_session(talk_id)
            except Exception:
                LOGGER.warning("Talk close failed for %s", talk_id)

    async def handle_text(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if not self.helloed:
            if kind != "hello":
                await self._send_text(hello_error("invalid_message", "hello required"))
                raise ProtocolError("invalid_message", "hello required")
            info = validate_hello(message)
            self.device_id = info["device_id"]
            self.helloed = True
            await self._send_text(hello_ok(self.keepalive_ms))
            return
        if kind == "ping":
            await self._send_text(control("pong", ts_ms=message.get("ts_ms")))
            return
        if kind == "pong":
            return
        if kind in {"wake", "conversation_open"}:
            await self._open_conversation()
            return
        if kind == "speech_start":
            self._require_conversation(message)
            self.uplink_seq_seen = -1
            return
        if kind == "speech_end":
            self._require_conversation(message)
            await self._commit_turn()
            try:
                self.dump_uplink_wav("artifacts/phase-02c/c1-uplink.wav")
            except OSError:
                LOGGER.warning("could not dump uplink wav")
            if hasattr(self.talk, "maybe_auto_reply") and self.talk_session_id:
                await self.talk.maybe_auto_reply(self.talk_session_id)
            return
        if kind == "interrupt":
            self._require_conversation(message)
            await self._interrupt()
            return
        if kind in {"cancel", "conversation_end"}:
            self._require_conversation(message)
            await self._end_conversation(message.get("reason") or "user", notify_device=False)
            return
        if kind == "error":
            LOGGER.info("device error %s", message.get("code"))
            return

    async def handle_binary(self, frame: bytes) -> None:
        if not self.helloed or not self.talk_session_id:
            self.metrics["dropped_old"] += 1
            return
        try:
            parsed = unpack_audio_frame(frame)
        except ProtocolError:
            self.metrics["dropped_old"] += 1
            return
        if parsed["conversation_id"] != self.conversation_id:
            self.metrics["dropped_old"] += 1
            return
        seq = parsed["seq"]
        if self.uplink_seq_seen >= 0:
            if seq == self.uplink_seq_seen:
                self.metrics["seq_dup"] += 1
                return
            if seq < self.uplink_seq_seen:
                self.metrics["seq_reorder"] += 1
                return
            if seq > self.uplink_seq_seen + 1:
                self.metrics["seq_gap"] += seq - self.uplink_seq_seen - 1
        self.uplink_seq_seen = seq
        pcm16 = parsed["pcm"]
        self.metrics["uplink_frames"] += 1
        self.metrics["uplink_bytes"] += len(pcm16)
        peak = max(
            abs(int.from_bytes(pcm16[i : i + 2], "little", signed=True))
            for i in range(0, len(pcm16), 2)
        )
        self.metrics["uplink_peak"] = max(int(self.metrics.get("uplink_peak") or 0), peak)
        self._uplink_pcm.extend(pcm16)
        pcm24 = self._up.process(pcm16)
        if pcm24:
            await self.talk.append_audio(
                self.talk_session_id,
                pcm24,
                timestamp=parsed["ts_ms"] / 1000.0,
            )

    @staticmethod
    def _text_of(event: dict[str, Any], talk_event: dict[str, Any]) -> Optional[str]:
        for candidate in (
            event.get("text"),
            event.get("transcript"),
            talk_event.get("text"),
            talk_event.get("transcript"),
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    async def on_talk_event(self, event: dict[str, Any]) -> None:
        if not self.talk_session_id:
            return
        event_session = event.get("sessionId") or event.get("relaySessionId")
        if event_session and event_session != self.talk_session_id:
            return
        kind = event.get("type")
        talk_event = event.get("talkEvent") or {}
        talk_type = talk_event.get("type")
        if isinstance(talk_type, str) and "transcript" in talk_type:
            text = self._text_of(event, talk_event)
            if text:
                entry = {"text": text, "talkType": talk_type, "ts": time.time()}
                self.metrics["user_transcripts"].append(entry)
                if talk_type.endswith("done"):
                    self.metrics["last_user_transcript"] = entry
        if kind in {"audio", "audioDelta"} or talk_type == "output.audio.delta":
            raw = event.get("audioBase64")
            if not raw:
                return
            pcm24 = base64.b64decode(raw)
            pcm16 = self._down.process(pcm24)
            await self._send_downlink(pcm16)
            return
        if kind in {"audio_done", "audioDone"} or talk_type == "output.audio.done":
            leftover = self._down_frames.flush()
            if leftover:
                padded = leftover + b"\x00" * (FRAME_BYTES - len(leftover))
                await self._emit_down_frame(padded, FLAG_UTTERANCE_END)
            if self.playing:
                self.playing = False
                self.metrics["playback_ends"] += 1
                try:
                    self.dump_downlink_wav("artifacts/phase-02c/c2-downlink.wav")
                except OSError:
                    LOGGER.warning("could not dump downlink wav")
                await self._send_text(
                    control("playback_end", conversation_id=self.conversation_id)
                )
            return
        if kind == "clear" or talk_type == "turn.cancelled":
            self._down.reset()
            self._down_frames.reset()
            if self.playing:
                self.playing = False
                self.metrics["playback_ends"] += 1
                await self._send_text(
                    control("playback_end", conversation_id=self.conversation_id)
                )
            return
        if kind == "close" or talk_type == "session.closed":
            if self.talk_session_id:
                self.talk_session_id = None
                await self._send_text(
                    control(
                        "conversation_end",
                        conversation_id=self.conversation_id,
                        reason="completed",
                    )
                )

    async def _open_conversation(self) -> None:
        if self.talk_session_id:
            await self._send_text(
                control(
                    "conversation_reject",
                    code="busy",
                    message="conversation already open",
                )
            )
            return
        try:
            created = await self.talk.create_session()
        except Exception:
            LOGGER.exception("Talk session create failed")
            await self._send_text(
                control(
                    "conversation_reject",
                    code="backend_unavailable",
                    message="talk unavailable",
                )
            )
            return
        self.talk_session_id = created.get("sessionId")
        self._up.reset()
        self._down.reset()
        self._down_frames.reset()
        self.down_seq = 0
        self.playing = False
        self._downlink_pcm = bytearray()
        await self._send_text(conversation_opened(self.conversation_id))

    def dump_uplink_wav(self, path: str) -> None:
        import wave
        from pathlib import Path

        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dest), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(bytes(self._uplink_pcm))

    def dump_downlink_wav(self, path: str) -> None:
        import wave
        from pathlib import Path

        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dest), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(bytes(self._downlink_pcm))

    async def _commit_turn(self) -> None:
        if not self.talk_session_id or self.commit_silence_ms <= 0:
            return
        samples = TALK_HZ * self.commit_silence_ms // 1000
        silence = b"\x00" * (samples * 2)
        chunk = 960
        for offset in range(0, len(silence), chunk):
            await self.talk.append_audio(
                self.talk_session_id,
                silence[offset : offset + chunk],
            )
        self.metrics["commit_silence_bytes"] += len(silence)

    async def _interrupt(self) -> None:
        self._down.reset()
        self._down_frames.reset()
        if self.playing:
            self.playing = False
            self.metrics["playback_ends"] += 1
            await self._send_text(
                control("playback_end", conversation_id=self.conversation_id)
            )
        if self.talk_session_id:
            await self.talk.cancel_output(self.talk_session_id, "barge-in")

    async def _end_conversation(self, reason: str, notify_device: bool) -> None:
        talk_id = self.talk_session_id
        self.talk_session_id = None
        self.playing = False
        self._up.reset()
        self._down.reset()
        self._down_frames.reset()
        if talk_id:
            await self.talk.close_session(talk_id)
        if notify_device:
            await self._send_text(
                control(
                    "conversation_end",
                    conversation_id=self.conversation_id,
                    reason=reason,
                )
            )

    def _require_conversation(self, message: dict[str, Any]) -> None:
        if not self.talk_session_id:
            raise ProtocolError("unknown_conversation", "no active conversation")
        cid = message.get("conversation_id")
        if cid is not None and int(cid) != self.conversation_id:
            raise ProtocolError("unknown_conversation", "conversation mismatch")

    async def _send_downlink(self, pcm16: bytes) -> None:
        if not pcm16:
            return
        self.metrics["downlink_bytes"] += len(pcm16)
        frames = self._down_frames.push(pcm16)
        for index, frame in enumerate(frames):
            flags = 0
            if not self.playing:
                self.playing = True
                self.metrics["playback_starts"] += 1
                self._downlink_pcm = bytearray()
                await self._send_text(
                    control("playback_start", conversation_id=self.conversation_id)
                )
                flags |= FLAG_UTTERANCE_START
            peak = max(
                abs(int.from_bytes(frame[i : i + 2], "little", signed=True))
                for i in range(0, len(frame), 2)
            )
            self.metrics["downlink_peak"] = max(
                int(self.metrics.get("downlink_peak") or 0), peak
            )
            await self._emit_down_frame(frame, flags)

    async def _emit_down_frame(self, pcm: bytes, flags: int) -> None:
        frame = pack_audio_frame(
            self.conversation_id,
            self.down_seq,
            int(time.monotonic() * 1000) & 0xFFFFFFFF,
            pcm,
            flags,
        )
        self.down_seq += 1
        self.metrics["downlink_frames"] += 1
        self._downlink_pcm.extend(pcm)
        await self._send_bytes(frame)
