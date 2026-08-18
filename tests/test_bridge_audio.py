import unittest

import numpy as np

from bridge.audio import TALK_HZ, downsample_24k_to_16k, upsample_16k_to_24k
from bridge.protocol import DEVICE_HZ


def sine_pcm(rate: int, freq: float, seconds: float, amplitude: int = 12000) -> bytes:
    samples = np.arange(int(rate * seconds), dtype=np.float64) / rate
    wave = amplitude * np.sin(2 * np.pi * freq * samples)
    return np.clip(np.rint(wave), -32768, 32767).astype("<i2").tobytes()


class ResamplerTests(unittest.TestCase):
    def test_16k_to_24k_length_ratio(self):
        pcm16 = sine_pcm(DEVICE_HZ, 400, 0.2)
        up = upsample_16k_to_24k()
        pcm24 = up.process(pcm16)
        expected = int(len(pcm16) * TALK_HZ / DEVICE_HZ)
        self.assertAlmostEqual(len(pcm24), expected, delta=8)

    def test_roundtrip_keeps_tone(self):
        pcm16 = sine_pcm(DEVICE_HZ, 400, 0.25)
        up = upsample_16k_to_24k()
        down = downsample_24k_to_16k()
        back = down.process(up.process(pcm16))
        src = np.frombuffer(pcm16, dtype="<i2").astype(np.float64)
        dst = np.frombuffer(back, dtype="<i2").astype(np.float64)
        n = min(len(src), len(dst))
        src = src[:n] - src[:n].mean()
        dst = dst[:n] - dst[:n].mean()
        corr = float(np.dot(src, dst) / (np.linalg.norm(src) * np.linalg.norm(dst)))
        self.assertGreater(corr, 0.95)

    def test_streaming_chunks_match_batch_length(self):
        pcm16 = sine_pcm(DEVICE_HZ, 250, 0.3)
        streaming = upsample_16k_to_24k()
        parts = []
        step = 640
        for offset in range(0, len(pcm16), step):
            parts.append(streaming.process(pcm16[offset : offset + step]))
        streamed = b"".join(parts)
        batched = upsample_16k_to_24k().process(pcm16)
        self.assertAlmostEqual(len(streamed), len(batched), delta=8)
