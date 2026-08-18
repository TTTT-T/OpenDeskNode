"""16 kHz ↔ 24 kHz s16le mono resampling. Talk side is pcm16/24 kHz."""

from __future__ import annotations

import numpy as np

from .protocol import DEVICE_HZ, FRAME_BYTES

TALK_HZ = 24000


class LinearResampler:
    def __init__(self, src_hz: int, dst_hz: int):
        if src_hz <= 0 or dst_hz <= 0:
            raise ValueError("sample rates must be positive")
        self.src_hz = src_hz
        self.dst_hz = dst_hz
        self._step = src_hz / dst_hz
        self.reset()

    def reset(self) -> None:
        self._pos = 0.0
        self._buf = np.zeros(0, dtype=np.float64)

    def process(self, pcm: bytes) -> bytes:
        if not pcm:
            return b""
        incoming = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
        data = np.concatenate([self._buf, incoming])
        if data.size < 2:
            self._buf = data
            return b""
        out = []
        pos = self._pos
        last = data.size - 1
        while pos < last:
            index = int(pos)
            frac = pos - index
            sample = data[index] * (1.0 - frac) + data[index + 1] * frac
            out.append(sample)
            pos += self._step
        keep_from = int(pos)
        self._buf = data[keep_from:]
        self._pos = pos - keep_from
        if not out:
            return b""
        clipped = np.clip(np.rint(out), -32768, 32767).astype("<i2")
        return clipped.tobytes()


class FrameSplitter:
    def __init__(self, frame_bytes: int = FRAME_BYTES):
        self.frame_bytes = frame_bytes
        self._buf = bytearray()

    def reset(self) -> None:
        self._buf.clear()

    def push(self, pcm: bytes) -> list[bytes]:
        self._buf.extend(pcm)
        frames = []
        while len(self._buf) >= self.frame_bytes:
            frames.append(bytes(self._buf[: self.frame_bytes]))
            del self._buf[: self.frame_bytes]
        return frames

    def flush(self) -> bytes:
        leftover = bytes(self._buf)
        self._buf.clear()
        return leftover


def upsample_16k_to_24k() -> LinearResampler:
    return LinearResampler(DEVICE_HZ, TALK_HZ)


def downsample_24k_to_16k() -> LinearResampler:
    return LinearResampler(TALK_HZ, DEVICE_HZ)
