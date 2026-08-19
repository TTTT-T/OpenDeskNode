"""EVA Voice Bridge Protocol draft 0 codec."""

from __future__ import annotations

import struct
from typing import Any, Mapping, Optional

PROTOCOL_VERSION = 0
MAGIC = 0xA5
HEADER_SIZE = 16
CODEC_ID = "pcm_s16le_16k_mono"
DEVICE_HZ = 16000
DEVICE_CHANNELS = 1
DEVICE_BITS = 16
FRAME_MS = 20
SAMPLES_PER_FRAME = DEVICE_HZ * FRAME_MS // 1000
FRAME_BYTES = SAMPLES_PER_FRAME * 2
FLAG_UTTERANCE_START = 0x01
FLAG_UTTERANCE_END = 0x02

DEVICE_TYPES = frozenset(
    {
        "hello",
        "ping",
        "pong",
        "wake",
        "conversation_open",
        "speech_start",
        "speech_end",
        "interrupt",
        "cancel",
        "conversation_end",
        "error",
    }
)


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def pack_audio_frame(
    conversation_id: int,
    seq: int,
    ts_ms: int,
    pcm: bytes,
    flags: int = 0,
) -> bytes:
    if len(pcm) != FRAME_BYTES:
        raise ProtocolError("invalid_message", "PCM payload must be %d bytes" % FRAME_BYTES)
    header = struct.pack(
        "<BBBBIII",
        MAGIC,
        PROTOCOL_VERSION,
        flags & 0xFF,
        0,
        conversation_id & 0xFFFFFFFF,
        seq & 0xFFFFFFFF,
        ts_ms & 0xFFFFFFFF,
    )
    return header + pcm


def unpack_audio_frame(frame: bytes) -> dict[str, Any]:
    if len(frame) < HEADER_SIZE:
        raise ProtocolError("invalid_message", "audio frame shorter than header")
    magic, version, flags, _reserved, conversation_id, seq, ts_ms = struct.unpack(
        "<BBBBIII", frame[:HEADER_SIZE]
    )
    if magic != MAGIC:
        raise ProtocolError("invalid_message", "bad audio magic")
    if version != PROTOCOL_VERSION:
        raise ProtocolError("unsupported_version", "audio version %s" % version)
    payload = frame[HEADER_SIZE:]
    if len(payload) != FRAME_BYTES:
        raise ProtocolError("invalid_message", "PCM payload must be %d bytes" % FRAME_BYTES)
    return {
        "conversation_id": conversation_id,
        "seq": seq,
        "ts_ms": ts_ms,
        "flags": flags,
        "pcm": payload,
        "start": bool(flags & FLAG_UTTERANCE_START),
        "end": bool(flags & FLAG_UTTERANCE_END),
    }


def validate_hello(message: Mapping[str, Any]) -> dict[str, Any]:
    if message.get("type") != "hello":
        raise ProtocolError("invalid_message", "first message must be hello")
    protocol = message.get("protocol")
    if protocol != PROTOCOL_VERSION:
        raise ProtocolError("unsupported_version", "protocol %s" % protocol)
    audio = message.get("audio") or {}
    if (
        audio.get("sample_rate") != DEVICE_HZ
        or audio.get("channels") != DEVICE_CHANNELS
        or audio.get("bits") != DEVICE_BITS
        or audio.get("frame_ms") != FRAME_MS
        or audio.get("codec") != CODEC_ID
    ):
        raise ProtocolError("invalid_message", "unsupported audio contract")
    device_id = message.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        raise ProtocolError("invalid_message", "device_id required")
    return {
        "device_id": device_id.strip(),
        "fw_version": str(message.get("fw_version") or ""),
        "audio": dict(audio),
    }


def control(type_name: str, **fields: Any) -> dict[str, Any]:
    body = {"type": type_name}
    body.update({key: value for key, value in fields.items() if value is not None})
    return body


def hello_ok(keepalive_ms: int = 10000) -> dict[str, Any]:
    return control(
        "hello_ok",
        protocol=PROTOCOL_VERSION,
        bridge="eva-voice-bridge",
        keepalive_ms=keepalive_ms,
    )


def hello_error(code: str, message: Optional[str] = None) -> dict[str, Any]:
    return control("hello_error", code=code, message=message)


def conversation_opened(conversation_id: int) -> dict[str, Any]:
    return control(
        "conversation_opened",
        conversation_id=conversation_id,
        codec=CODEC_ID,
        frame_ms=FRAME_MS,
    )
