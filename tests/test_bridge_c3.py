import unittest

from bridge.audio import TALK_HZ
from bridge.protocol import PROTOCOL_VERSION, pack_audio_frame
from bridge.session import DeviceSession
from bridge.talk import FakeTalkClient


def hello():
    return {
        "type": "hello",
        "protocol": PROTOCOL_VERSION,
        "device_id": "host-c3",
        "fw_version": "test",
        "audio": {
            "sample_rate": 16000,
            "channels": 1,
            "bits": 16,
            "frame_ms": 20,
            "codec": "pcm_s16le_16k_mono",
        },
    }


def pcm_frame(cid, seq):
    return pack_audio_frame(cid, seq, seq * 20, b"\x10\x00" * 320)


class C3BargeInTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.talk = FakeTalkClient()
        self.texts = []
        self.frames = []

        async def send_text(message):
            self.texts.append(message)

        async def send_bytes(frame):
            self.frames.append(frame)

        self.session = DeviceSession(self.talk, send_text, send_bytes, commit_silence_ms=0)
        await self.session.handle_text(hello())
        await self.session.handle_text({"type": "conversation_open", "reason": "manual"})
        self.cid = self.session.conversation_id

    async def test_interrupt_cancels_and_drops_leftover_downlink(self):
        leftover = b"\x22\x00" * (TALK_HZ // 10)
        await self.talk.emit_output_delta(self.session.talk_session_id, leftover)
        self.assertTrue(self.session.playing)
        starts_before = self.session.metrics["playback_starts"]
        frames_before = self.session.metrics["downlink_frames"]

        await self.session.handle_text({"type": "interrupt", "conversation_id": self.cid})
        self.assertEqual(self.talk.cancelled[0][1], "barge-in")
        self.assertEqual(self.session.metrics["interrupts"], 1)
        self.assertFalse(self.session.playing)
        self.assertTrue(self.session.suppress_downlink)
        self.assertIn("playback_end", [item["type"] for item in self.texts])

        await self.talk.emit_output_delta(self.session.talk_session_id, leftover)
        self.assertGreater(self.session.metrics["dropped_after_interrupt"], 0)
        self.assertEqual(self.session.metrics["playback_starts"], starts_before)
        self.assertEqual(self.session.metrics["downlink_frames"], frames_before)
        self.assertFalse(self.session.playing)

    async def test_new_turn_after_interrupt_gets_downlink(self):
        first = b"\x11\x00" * (TALK_HZ // 10)
        second = b"\x33\x00" * (TALK_HZ // 10)
        await self.talk.emit_output_delta(self.session.talk_session_id, first)
        await self.session.handle_text({"type": "interrupt", "conversation_id": self.cid})
        await self.talk.emit_output_delta(self.session.talk_session_id, first)
        dropped = self.session.metrics["dropped_after_interrupt"]

        await self.session.handle_text({"type": "speech_start", "conversation_id": self.cid})
        await self.session.handle_binary(pcm_frame(self.cid, 0))
        await self.session.handle_text({"type": "speech_end", "conversation_id": self.cid})
        self.assertFalse(self.session.suppress_downlink)

        await self.talk.emit_output(self.session.talk_session_id, second)
        self.assertEqual(self.session.metrics["dropped_after_interrupt"], dropped)
        self.assertGreaterEqual(self.session.metrics["playback_starts"], 2)
        self.assertTrue(any(item["type"] == "playback_start" for item in self.texts[-4:]))

    async def test_speech_start_after_interrupt_resets_uplink_seq(self):
        await self.session.handle_text({"type": "speech_start", "conversation_id": self.cid})
        await self.session.handle_binary(pcm_frame(self.cid, 0))
        await self.session.handle_text({"type": "interrupt", "conversation_id": self.cid})
        await self.session.handle_text({"type": "speech_start", "conversation_id": self.cid})
        await self.session.handle_binary(pcm_frame(self.cid, 0))
        self.assertEqual(self.session.uplink_seq_seen, 0)
        self.assertEqual(self.session.metrics["seq_dup"], 0)


if __name__ == "__main__":
    unittest.main()
