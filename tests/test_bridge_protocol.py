import unittest

from bridge.protocol import (
    CODEC_ID,
    DEVICE_HZ,
    FLAG_UTTERANCE_START,
    FRAME_BYTES,
    PROTOCOL_VERSION,
    ProtocolError,
    pack_audio_frame,
    unpack_audio_frame,
    validate_hello,
)


class ProtocolTests(unittest.TestCase):
    def test_audio_frame_roundtrip(self):
        pcm = b"\x01\x00" * 320
        frame = pack_audio_frame(7, 3, 1234, pcm, FLAG_UTTERANCE_START)
        parsed = unpack_audio_frame(frame)
        self.assertEqual(parsed["conversation_id"], 7)
        self.assertEqual(parsed["seq"], 3)
        self.assertEqual(parsed["ts_ms"], 1234)
        self.assertTrue(parsed["start"])
        self.assertEqual(parsed["pcm"], pcm)
        self.assertEqual(len(frame), 16 + FRAME_BYTES)

    def test_rejects_bad_magic(self):
        frame = pack_audio_frame(1, 0, 0, b"\x00\x00")
        broken = b"\x00" + frame[1:]
        with self.assertRaises(ProtocolError) as caught:
            unpack_audio_frame(broken)
        self.assertEqual(caught.exception.code, "invalid_message")

    def test_hello_accepts_device_contract(self):
        info = validate_hello(
            {
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
        )
        self.assertEqual(info["device_id"], "host-c0")

    def test_hello_rejects_24k(self):
        with self.assertRaises(ProtocolError) as caught:
            validate_hello(
                {
                    "type": "hello",
                    "protocol": 0,
                    "device_id": "x",
                    "audio": {
                        "sample_rate": 24000,
                        "channels": 1,
                        "bits": 16,
                        "frame_ms": 20,
                        "codec": CODEC_ID,
                    },
                }
            )
        self.assertEqual(caught.exception.code, "invalid_message")
