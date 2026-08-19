import json
import unittest

from bridge.audio import TALK_HZ
from bridge.config import BridgeConfig
from bridge.protocol import FRAME_BYTES, PROTOCOL_VERSION, pack_audio_frame
from bridge.session import DeviceSession
from bridge.talk import FakeTalkClient, GatewayTalkClient


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

    async def test_session_scoped_user_transcripts(self):
        sid = self.session.talk_session_id
        event = {
            "type": "transcript",
            "sessionId": sid,
            "talkEvent": {"type": "transcript.done", "transcript": "你好 EVA"},
        }
        await self.session.on_talk_event(event)
        self.assertEqual(len(self.session.metrics["user_transcripts"]), 1)
        final = self.session.metrics["last_user_transcript"]
        self.assertEqual(final["text"], "你好 EVA")
        self.assertEqual(final["talkType"], "transcript.done")

        delta = {
            "type": "transcript",
            "sessionId": sid,
            "talkEvent": {"type": "transcript.delta", "transcript": "你"},
        }
        await self.session.on_talk_event(delta)
        self.assertEqual(len(self.session.metrics["user_transcripts"]), 2)
        self.assertEqual(self.session.metrics["last_user_transcript"]["text"], "你好 EVA")

        other = {
            "type": "transcript",
            "sessionId": "talk-somewhere-else",
            "talkEvent": {"type": "transcript.done", "transcript": "别的会话"},
        }
        await self.session.on_talk_event(other)
        self.assertEqual(len(self.session.metrics["user_transcripts"]), 2)

        assistant = {
            "type": "text",
            "sessionId": sid,
            "talkEvent": {"type": "output.text.delta", "text": "EVA 回复"},
        }
        await self.session.on_talk_event(assistant)
        self.assertEqual(len(self.session.metrics["user_transcripts"]), 2)


class GatewayTalkStatsTests(unittest.TestCase):
    def _client(self):
        return GatewayTalkClient("ws://127.0.0.1:18789", "token")

    def test_transcript_entries_carry_session_eventseq_ts(self):
        client = self._client()
        client._collect_text(
            {"text": "你好 EVA", "sessionId": "talk-live-1"},
            "transcript.done",
            7,
            1700000000.0,
        )
        client._collect_text(
            {"text": "assistant says", "sessionId": "talk-live-1"},
            "output.text.done",
            8,
            1700000001.0,
        )
        self.assertEqual(len(client.stats["transcripts"]), 1)
        self.assertEqual(len(client.stats["texts"]), 1)
        entry = client.stats["transcripts"][0]
        self.assertEqual(entry["text"], "你好 EVA")
        self.assertEqual(entry["sessionId"], "talk-live-1")
        self.assertEqual(entry["eventSeq"], 7)
        self.assertEqual(entry["ts"], 1700000000.0)
        self.assertEqual(entry["talkType"], "transcript.done")

    def test_next_event_is_monotonic(self):
        client = self._client()
        first = client._next_event()
        second = client._next_event()
        self.assertEqual(first[0], 1)
        self.assertEqual(second[0], 2)
        self.assertGreaterEqual(second[1], first[1])
        self.assertEqual(client.stats["events"], 2)


class _FakeWS:
    def __init__(self, messages):
        self._messages = messages

    def __aiter__(self):
        return self._agen()

    async def _agen(self):
        for message in self._messages:
            yield json.dumps(message)

    async def close(self):
        return None


class TalkReaderSurvivalTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_loop_survives_listener_failure(self):
        # A device WS dying mid-downlink must not kill the shared Talk reader.
        client = GatewayTalkClient("ws://127.0.0.1:18789", "token")
        client._connected = True
        seen = []

        async def listener(payload):
            seen.append(payload.get("type"))
            if payload.get("type") == "boom":
                raise RuntimeError("device websocket gone")

        client.set_listener(listener)
        client._ws = _FakeWS(
            [
                {
                    "type": "event",
                    "event": "talk.event",
                    "payload": {"type": "boom", "sessionId": "s1"},
                },
                {
                    "type": "event",
                    "event": "talk.event",
                    "payload": {"type": "still-drained", "sessionId": "s1"},
                },
            ]
        )
        await client._read_loop()
        self.assertEqual(seen, ["boom", "still-drained"])
        self.assertTrue(client.connected)


class C1ConfigTests(unittest.TestCase):
    def test_commit_silence_default(self):
        self.assertEqual(BridgeConfig().commit_silence_ms, 1000)
