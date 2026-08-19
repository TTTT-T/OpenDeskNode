import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_watcher():
    if "phase_02c_c1_live" in sys.modules:
        return sys.modules["phase_02c_c1_live"]
    spec = importlib.util.spec_from_file_location(
        "phase_02c_c1_live", ROOT / "scripts" / "phase-02c-c1-live.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["phase_02c_c1_live"] = module
    return module


watcher = _load_watcher()


def snapshot(conv, frames, transcripts, conversations=1, session="talk-1"):
    return {
        "conversation_id": conv,
        "talk_session_id": session,
        "conversations": conversations,
        "metrics": {
            "uplink_frames": frames,
            "uplink_bytes": frames * 640,
            "user_transcripts": transcripts,
        },
        "talk_stats": {"event_seq": 0},
    }


class WatcherBaselineTests(unittest.TestCase):
    def test_baseline_captures_current_counters(self):
        base = watcher.capture_baseline(
            snapshot(5, 249, [{"text": "旧转写", "talkType": "transcript.done", "ts": 1.0}])
        )
        self.assertEqual(base["conversation_id"], 5)
        self.assertEqual(base["uplink_frames"], 249)
        self.assertEqual(base["user_transcripts"], 1)

    def test_historical_transcript_cannot_pass(self):
        stale = snapshot(5, 249, [{"text": "旧转写", "talkType": "transcript.done", "ts": 1.0}])
        base = watcher.capture_baseline(stale)
        # Only historical evidence, nothing new after start: must not pass even
        # though transcripts exist and "transcript.done" was seen historically.
        verdict = watcher.evaluate(base, stale)
        self.assertFalse(verdict["new_uplink"])
        self.assertEqual(verdict["transcript"], None)

    def test_new_uplink_without_new_transcript_cannot_pass(self):
        base = watcher.capture_baseline(snapshot(5, 0, []))
        grew = snapshot(
            5,
            120,
            [],
        )
        verdict = watcher.evaluate(base, grew)
        self.assertTrue(verdict["new_uplink"])
        self.assertEqual(verdict["transcript"], None)

    def test_new_transcript_without_new_uplink_cannot_pass(self):
        base = watcher.capture_baseline(snapshot(5, 10, []))
        later = snapshot(
            5,
            10,
            [{"text": "你好 EVA", "talkType": "transcript.done", "ts": 2.0}],
        )
        verdict = watcher.evaluate(base, later)
        self.assertFalse(verdict["new_uplink"])
        self.assertIsNotNone(verdict["transcript"])

    def test_new_uplink_and_new_transcript_pass(self):
        base = watcher.capture_baseline(snapshot(5, 0, []))
        later = snapshot(
            5,
            120,
            [
                {"text": "你", "talkType": "transcript.delta", "ts": 2.0},
                {"text": "你好 EVA，这是 ESP32 麦克风测试", "talkType": "transcript.done", "ts": 3.0},
            ],
        )
        verdict = watcher.evaluate(base, later)
        self.assertTrue(verdict["new_uplink"])
        self.assertEqual(verdict["transcript"]["text"], "你好 EVA，这是 ESP32 麦克风测试")
        self.assertEqual(verdict["transcript"]["talkType"], "transcript.done")

    def test_partial_transcript_delta_alone_cannot_pass(self):
        # Streaming transcript.delta partials are not committed evidence; only
        # transcript.done may grant PASS.
        base = watcher.capture_baseline(snapshot(5, 0, []))
        later = snapshot(
            5,
            120,
            [{"text": "正", "talkType": "transcript.delta", "ts": 2.0}],
        )
        verdict = watcher.evaluate(base, later)
        self.assertTrue(verdict["new_uplink"])
        self.assertEqual(verdict["transcript"], None)

    def test_stale_frames_from_previous_session_cannot_pass(self):
        # Bridge keeps no current session at start; /metrics falls back to the
        # previous run's counters (conversation_id None, 249 stale frames).
        stale = snapshot(None, 249, [{"text": "旧转写", "talkType": "transcript.done", "ts": 1.0}])
        base = watcher.capture_baseline(stale)
        still_stale = snapshot(None, 249, stale["metrics"]["user_transcripts"])
        verdict = watcher.evaluate(base, still_stale)
        self.assertFalse(verdict["new_uplink"])
        self.assertEqual(verdict["transcript"], None)

    def test_fresh_session_frames_after_baseline_count_as_new(self):
        stale = snapshot(None, 249, [{"text": "旧转写", "talkType": "transcript.done", "ts": 1.0}])
        base = watcher.capture_baseline(stale)
        fresh = snapshot(
            1,
            60,
            [
                {"text": "你好 EVA", "talkType": "transcript.done", "ts": 2.0},
            ],
        )
        verdict = watcher.evaluate(base, fresh)
        self.assertTrue(verdict["new_uplink"])
        self.assertEqual(verdict["transcript"]["text"], "你好 EVA")

    def test_second_utterance_uses_incremental_baseline(self):
        # Simulates turn 2 after turn 1 already produced evidence: with the
        # watcher restarted (fresh baseline), only growth beyond the captured
        # state counts.
        base = watcher.capture_baseline(
            snapshot(5, 120, [{"text": "第一轮", "talkType": "transcript.done", "ts": 1.0}])
        )
        unchanged = snapshot(
            5,
            120,
            [{"text": "第一轮", "talkType": "transcript.done", "ts": 1.0}],
        )
        self.assertFalse(watcher.evaluate(base, unchanged)["new_uplink"])
        turn2 = snapshot(
            5,
            240,
            [
                {"text": "第一轮", "talkType": "transcript.done", "ts": 1.0},
                {"text": "第二轮", "talkType": "transcript.done", "ts": 2.0},
            ],
        )
        verdict = watcher.evaluate(base, turn2)
        self.assertTrue(verdict["new_uplink"])
        self.assertEqual(verdict["transcript"]["text"], "第二轮")


if __name__ == "__main__":
    unittest.main()
