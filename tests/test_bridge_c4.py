import unittest

from bridge.protocol import PROTOCOL_VERSION, pack_audio_frame
from bridge.session import DeviceSession
from bridge.talk import FakeTalkClient


def hello():
    return {
        "type": "hello",
        "protocol": PROTOCOL_VERSION,
        "device_id": "host-c4",
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


class C4MultiTurnTests(unittest.IsolatedAsyncioTestCase):
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
        self.sid = self.session.talk_session_id

    async def test_second_turn_reuses_talk_session(self):
        await self.session.handle_text({"type": "speech_start", "conversation_id": self.cid})
        await self.session.handle_binary(pcm_frame(self.cid, 0))
        await self.session.handle_text({"type": "speech_end", "conversation_id": self.cid})
        await self.session.handle_text({"type": "speech_start", "conversation_id": self.cid})
        await self.session.handle_binary(pcm_frame(self.cid, 0))
        await self.session.handle_text({"type": "speech_end", "conversation_id": self.cid})
        self.assertEqual(len(self.talk.created), 1)
        self.assertEqual(self.talk.stats["create_ok"], 1)
        self.assertEqual(self.session.talk_session_id, self.sid)
        self.assertEqual(self.session.conversation_id, self.cid)
        self.assertEqual(self.session.metrics["speech_starts"], 2)
        self.assertEqual(self.session.metrics["conversation_creates"], 1)

    async def test_open_while_active_is_busy(self):
        before = list(self.talk.created)
        await self.session.handle_text({"type": "conversation_open", "reason": "manual"})
        self.assertEqual(self.texts[-1]["type"], "conversation_reject")
        self.assertEqual(self.texts[-1]["code"], "busy")
        self.assertEqual(self.talk.created, before)
        self.assertEqual(self.session.talk_session_id, self.sid)

    async def test_device_end_closes_talk_but_keeps_mapping_idle(self):
        await self.session.handle_text(
            {"type": "conversation_end", "conversation_id": self.cid, "reason": "timeout"}
        )
        self.assertIsNone(self.session.talk_session_id)
        self.assertEqual(self.talk.closed, [self.sid])
        await self.session.handle_text({"type": "conversation_open", "reason": "manual"})
        self.assertEqual(len(self.talk.created), 2)
        self.assertIsNotNone(self.session.talk_session_id)
        self.assertNotEqual(self.session.talk_session_id, self.sid)
