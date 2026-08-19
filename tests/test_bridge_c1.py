import unittest

from bridge.audio import TALK_HZ
from bridge.config import BridgeConfig
from bridge.protocol import FRAME_BYTES, PROTOCOL_VERSION, pack_audio_frame
from bridge.session import DeviceSession
from bridge.talk import FakeTalkClient


def hello():
    return {
        "type": "hello",
        "protocol": PROTOCOL_VERSION,
        "device_id": "host-c1",
        "fw_version": "test",
        "audio": {
            "sample_rate": 16000,
            "channels": 1,
            "bits": 16,
            "frame_ms": 20,
            "codec": "pcm_s16le_16k_mono",
        },
    }


class C1ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.talk = FakeTalkClient()
        self.texts = []

        async def send_text(message):
            self.texts.append(message)

        async def send_bytes(_frame):
            return None

        self.session = DeviceSession(
            self.talk,
            send_text,
            send_bytes,
            commit_silence_ms=1000,
        )
        await self.session.handle_text(hello())
        await self.session.handle_text({"type": "conversation_open", "reason": "manual"})
        await self.session.handle_text(
            {"type": "speech_start", "conversation_id": self.session.conversation_id}
        )

    async def test_seq_dup_gap_reorder(self):
        cid = self.session.conversation_id
        pcm = b"\x01\x00" * 320
        await self.session.handle_binary(pack_audio_frame(cid, 0, 0, pcm))
        await self.session.handle_binary(pack_audio_frame(cid, 0, 0, pcm))
        await self.session.handle_binary(pack_audio_frame(cid, 3, 60, pcm))
        await self.session.handle_binary(pack_audio_frame(cid, 2, 40, pcm))
        self.assertEqual(self.session.metrics["uplink_frames"], 2)
        self.assertEqual(self.session.metrics["seq_dup"], 1)
        self.assertEqual(self.session.metrics["seq_gap"], 2)
        self.assertEqual(self.session.metrics["seq_reorder"], 1)

    async def test_speech_end_injects_bridge_commit_silence(self):
        cid = self.session.conversation_id
        pcm = b"\x02\x00" * 320
        await self.session.handle_binary(pack_audio_frame(cid, 0, 0, pcm))
        before = sum(len(item[1]) for item in self.talk.appended)
        await self.session.handle_text({"type": "speech_end", "conversation_id": cid})
        after = sum(len(item[1]) for item in self.talk.appended)
        self.assertEqual(after - before, TALK_HZ * 2)
        self.assertEqual(self.session.metrics["commit_silence_bytes"], TALK_HZ * 2)
        self.assertTrue(all(byte == 0 for item in self.talk.appended[1:] for byte in item[1]))

    async def test_wrong_length_frame_is_dropped(self):
        before = self.session.metrics["dropped_old"]
        await self.session.handle_binary(b"\xa5" + b"\x00" * 20)
        self.assertEqual(self.session.metrics["dropped_old"], before + 1)


class C1ConfigTests(unittest.TestCase):
    def test_commit_silence_default(self):
        self.assertEqual(BridgeConfig().commit_silence_ms, 1000)
