import unittest

from bridge.protocol import PROTOCOL_VERSION, pack_audio_frame
from bridge.session import DeviceSession
from bridge.talk import FakeTalkClient


def hello():
    return {
        "type": "hello",
        "protocol": PROTOCOL_VERSION,
        "device_id": "host-c5",
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


class C5RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.talk = FakeTalkClient()
        self.texts = []

        async def send_text(message):
            self.texts.append(message)

        async def send_bytes(_frame):
            return None

        self.session = DeviceSession(self.talk, send_text, send_bytes, commit_silence_ms=0)
        await self.session.handle_text(hello())
        await self.session.handle_text({"type": "conversation_open", "reason": "manual"})
        self.cid = self.session.conversation_id
        self.sid = self.session.talk_session_id

    async def test_gateway_drop_invalidates_session(self):
        await self.talk.drop()
        self.assertIsNone(self.session.talk_session_id)
        self.assertGreaterEqual(self.session.metrics["session_invalidations"], 1)
        self.assertEqual(self.texts[-1]["type"], "conversation_end")
        self.assertFalse(self.session.playing)

    async def test_stale_session_is_not_reused(self):
        await self.talk.drop()
        await self.talk.recover()
        before = list(self.talk.created)
        await self.session.handle_text({"type": "conversation_open", "reason": "manual"})
        self.assertEqual(len(self.talk.created), len(before) + 1)
        self.assertNotEqual(self.session.talk_session_id, self.sid)
        self.assertNotIn(self.session.talk_session_id, self.talk.stale)

    async def test_append_after_drop_does_not_keep_speaking_state(self):
        await self.session.handle_text({"type": "speech_start", "conversation_id": self.cid})
        await self.talk.drop()
        await self.session.handle_binary(pcm_frame(self.cid, 0))
        self.assertIsNone(self.session.talk_session_id)
        self.assertFalse(self.session.playing)

    async def test_create_failure_rejects_without_stale_id(self):
        await self.session.handle_text(
            {"type": "conversation_end", "conversation_id": self.cid, "reason": "user"}
        )
        self.talk.fail_create = True
        await self.session.handle_text({"type": "conversation_open", "reason": "manual"})
        self.assertEqual(self.texts[-1]["type"], "conversation_reject")
        self.assertEqual(self.texts[-1]["code"], "backend_unavailable")
        self.assertIsNone(self.session.talk_session_id)

    async def test_session_closed_event_resets_resampler_state(self):
        await self.talk.emit_output_delta(self.sid, b"\x11\x00" * 480)
        self.assertTrue(self.session.playing)
        await self.session.on_talk_event(
            {"type": "close", "sessionId": self.sid, "talkEvent": {"type": "session.closed"}}
        )
        self.assertFalse(self.session.playing)
        self.assertIsNone(self.session.talk_session_id)
        self.assertGreaterEqual(self.session.metrics["session_invalidations"], 1)

    async def test_malformed_conversation_does_not_crash(self):
        with self.assertRaises(Exception):
            await self.session.handle_text(
                {"type": "speech_start", "conversation_id": self.cid + 99}
            )
        self.assertEqual(self.session.talk_session_id, self.sid)
