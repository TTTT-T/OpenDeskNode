import json
import unittest

import numpy as np
from fastapi.testclient import TestClient

from bridge.app import create_app
from bridge.audio import TALK_HZ
from bridge.config import BridgeConfig
from bridge.protocol import (
    CODEC_ID,
    DEVICE_HZ,
    FRAME_BYTES,
    PROTOCOL_VERSION,
    pack_audio_frame,
    unpack_audio_frame,
)
from bridge.talk import FakeTalkClient


def sine_pcm(rate: int, freq: float, seconds: float) -> bytes:
    samples = np.arange(int(rate * seconds), dtype=np.float64) / rate
    wave = 10000 * np.sin(2 * np.pi * freq * samples)
    return np.clip(np.rint(wave), -32768, 32767).astype("<i2").tobytes()


def hello_payload():
    return {
        "type": "hello",
        "protocol": PROTOCOL_VERSION,
        "device_id": "host-c0",
        "fw_version": "fixture",
        "audio": {
            "sample_rate": DEVICE_HZ,
            "channels": 1,
            "bits": 16,
            "frame_ms": 20,
            "codec": CODEC_ID,
        },
    }


class C0FixtureTests(unittest.TestCase):
    def setUp(self):
        reply = sine_pcm(TALK_HZ, 600, 0.12)
        self.talk = FakeTalkClient(auto_reply_pcm24=reply)
        self.app = create_app(
            config=BridgeConfig(talk_enabled=False, log_path=":memory:"),
            talk=self.talk,
        )
        self.client = TestClient(self.app)

    def test_healthz(self):
        with self.client:
            body = self.client.get("/healthz").json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["service"], "eva-voice-bridge")
        self.assertEqual(body["talk_kind"], "FakeTalkClient")

    def test_c0_session_uplink_and_downlink(self):
        pcm = sine_pcm(DEVICE_HZ, 400, 0.1)
        with self.client.websocket_connect("/voice/v0") as ws:
            ws.send_json(hello_payload())
            self.assertEqual(ws.receive_json()["type"], "hello_ok")
            ws.send_json({"type": "conversation_open", "reason": "manual"})
            opened = ws.receive_json()
            self.assertEqual(opened["type"], "conversation_opened")
            cid = opened["conversation_id"]
            ws.send_json({"type": "speech_start", "conversation_id": cid})
            for seq, offset in enumerate(range(0, len(pcm), FRAME_BYTES)):
                chunk = pcm[offset : offset + FRAME_BYTES]
                if len(chunk) < FRAME_BYTES:
                    chunk = chunk + b"\x00" * (FRAME_BYTES - len(chunk))
                ws.send_bytes(pack_audio_frame(cid, seq, seq * 20, chunk))
            ws.send_json({"type": "speech_end", "conversation_id": cid})
            events = []
            frames = []
            for _ in range(20):
                message = ws.receive()
                if message.get("text"):
                    events.append(json.loads(message["text"]))
                    if events[-1]["type"] == "playback_end":
                        break
                elif message.get("bytes"):
                    frames.append(unpack_audio_frame(message["bytes"]))
        self.assertTrue(self.talk.created)
        self.assertGreater(sum(len(item[1]) for item in self.talk.appended), 0)
        types = [item["type"] for item in events]
        self.assertIn("playback_start", types)
        self.assertIn("playback_end", types)
        self.assertGreater(len(frames), 0)
        self.assertEqual(frames[0]["conversation_id"], cid)
        self.assertEqual(len(frames[0]["pcm"]), FRAME_BYTES)
        last = self.app.state.bridge.get("last_metrics") or {}
        self.assertGreater(last.get("playback_starts", 0), 0)
        self.assertGreater(last.get("playback_ends", 0), 0)
        self.assertGreater(last.get("downlink_peak", 0), 0)
        self.assertGreater(last.get("downlink_frames", 0), 0)

    def test_interrupt_cancels_talk_output(self):
        with self.client.websocket_connect("/voice/v0") as ws:
            ws.send_json(hello_payload())
            ws.receive_json()
            ws.send_json({"type": "conversation_open", "reason": "manual"})
            cid = ws.receive_json()["conversation_id"]
            ws.send_json({"type": "interrupt", "conversation_id": cid})
        self.assertEqual(self.talk.cancelled[0][1], "barge-in")

    def test_hello_required(self):
        with self.client.websocket_connect("/voice/v0") as ws:
            ws.send_json({"type": "conversation_open"})
            error = ws.receive_json()
        self.assertEqual(error["type"], "hello_error")
