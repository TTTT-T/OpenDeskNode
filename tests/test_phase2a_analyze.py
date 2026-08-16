import importlib.util
import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "phase02a_analyze", REPO / "scripts" / "phase-02a-analyze.py"
)
analyze_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze_mod)

RATE = 16000
RNG = np.random.default_rng(20260816)


def write_wav(path: Path, channels):
    """channels: list of 1-D float arrays; writes interleaved PCM16."""
    n = min(len(c) for c in channels)
    data = np.stack([c[:n] for c in channels], axis=1)
    pcm = np.clip(data, -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(len(channels))
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def speech_like(seconds: float, lead_silence=1.0, tail_silence=1.0):
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    sig = 9000 * np.sin(2 * np.pi * 220 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3.1 * t))
    sig += 4000 * np.sin(2 * np.pi * 850 * t) * (np.sin(2 * np.pi * 1.7 * t) > 0)
    sig += RNG.normal(0, 500, n)
    silence = np.zeros(int(lead_silence * RATE))
    tail = np.zeros(int(tail_silence * RATE))
    return np.concatenate([silence, sig, tail])


class Phase2AAnalyzerTests(unittest.TestCase):
    def setUp(self):
        global RNG
        RNG = np.random.default_rng(20260816)
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _make_case(self, mic1_fn, ref_mic_delay, aec_gain=0.03):
        """Builds the four WAVs. mic0 hears ref after ref_mic_delay samples;
        mic1 is either a copy of mic0 or an independent-but-correlated path."""
        ref = speech_like(6.0)
        n = len(ref)
        room = RNG.normal(0, 60, n)
        d = ref_mic_delay
        mic0 = np.concatenate([np.zeros(d), ref[: n - d]]) * 0.4 + room
        mic1 = mic1_fn(mic0, room, n, d)
        aec_off = mic0
        aec_on = aec_off * aec_gain + RNG.normal(0, 1.0, n)
        write_wav(self.dir / "mic0_mic1.wav", [mic0, mic1])
        write_wav(self.dir / "aec_off.wav", [aec_off])
        write_wav(self.dir / "aec_on.wav", [aec_on])
        write_wav(self.dir / "playback_reference.wav", [ref])
        return ref, mic0, mic1

    def test_copied_channel_is_detected(self):
        self._make_case(
            mic1_fn=lambda mic0, room, n, d: mic0.copy(),
            ref_mic_delay=7,
        )
        result = analyze_mod.analyze(self.dir)
        self.assertFalse(result["mic_independence"]["independent"])
        self.assertGreater(result["mic_independence"]["bit_identity_ratio"], 0.999)
        self.assertGreater(result["mic_independence"]["max_windowed_pearson"], 0.999)

    def test_independent_mics_pass_and_delay_found(self):
        self._make_case(
            mic1_fn=lambda mic0, room, n, d: np.concatenate(
                [np.zeros(d + 5), mic0[: n - d - 5]]) * 0.9 + RNG.normal(0, 90, n),
            ref_mic_delay=11,
        )
        result = analyze_mod.analyze(self.dir)
        self.assertTrue(result["mic_independence"]["independent"], json.dumps(result, indent=1))
        self.assertLess(result["mic_independence"]["bit_identity_ratio"], 0.001)
        delay = result["reference_validity"]["ref_mic_delay_samples"]
        self.assertLess(abs(delay - 11), 3)

    def test_reference_validity_and_erle(self):
        self._make_case(
            mic1_fn=lambda mic0, room, n, d: mic0 * 0.8 + RNG.normal(0, 80, n),
            ref_mic_delay=9,
            aec_gain=0.01,
        )
        result = analyze_mod.analyze(self.dir)
        self.assertTrue(result["reference_validity"]["valid"], json.dumps(result, indent=1))
        self.assertTrue(result["aec"]["passed"], json.dumps(result["aec"], indent=1))
        self.assertGreater(result["aec"]["erle_mean_db"], 10.0)
        self.assertTrue(result["passed"])

    def test_no_cancellation_fails_erle(self):
        self._make_case(
            mic1_fn=lambda mic0, room, n, d: mic0 * 0.8 + RNG.normal(0, 80, n),
            ref_mic_delay=9,
            aec_gain=0.9,
        )
        result = analyze_mod.analyze(self.dir)
        self.assertFalse(result["aec"]["passed"])
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
