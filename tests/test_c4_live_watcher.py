import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_watcher():
    if "phase_02c_c4_live" in sys.modules:
        return sys.modules["phase_02c_c4_live"]
    spec = importlib.util.spec_from_file_location(
        "phase_02c_c4_live", ROOT / "scripts" / "phase-02c-c4-live.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["phase_02c_c4_live"] = module
    return module


watcher = _load_watcher()


def snapshot(
    conv,
    starts,
    frames,
    transcripts,
    conversations=1,
    session="talk-1",
    create_ok=1,
    playback_starts=0,
):
    return {
        "conversation_id": conv,
        "talk_session_id": session,
        "conversations": conversations,
        "metrics": {
            "speech_starts": starts,
            "uplink_frames": frames,
            "playback_starts": playback_starts,
            "user_transcripts": transcripts,
        },
        "talk_stats": {"event_seq": 0, "create_ok": create_ok},
    }


def done(text, ts=1.0):
    return {"text": text, "talkType": "transcript.done", "ts": ts}


class C4WatcherBaselineTests(unittest.TestCase):
    def test_historical_turns_cannot_pass(self):
        stale = snapshot(5, 2, 400, [done("一"), done("二")])
        base = watcher.capture_baseline(stale)
        verdict = watcher.evaluate(base, stale)
        self.assertEqual(verdict["new_speech_starts"], 0)
        self.assertFalse(verdict["multi_turn_complete"])

    def test_one_new_turn_cannot_pass(self):
        base = watcher.capture_baseline(snapshot(5, 1, 200, [done("一")]))
        later = snapshot(5, 2, 400, [done("一"), done("二")])
        verdict = watcher.evaluate(base, later)
        self.assertEqual(verdict["new_speech_starts"], 1)
        self.assertFalse(verdict["multi_turn_complete"])

    def test_new_conversation_cannot_pass(self):
        base = watcher.capture_baseline(snapshot(5, 1, 200, [done("一")]))
        later = snapshot(6, 2, 80, [done("新1"), done("新2")], session="talk-2", create_ok=2)
        verdict = watcher.evaluate(base, later)
        self.assertFalse(verdict["same_conversation"])
        self.assertFalse(verdict["multi_turn_complete"])

    def test_recreated_talk_session_cannot_pass(self):
        base = watcher.capture_baseline(snapshot(5, 1, 200, [done("一")], session="talk-1"))
        later = snapshot(
            5, 3, 500, [done("一"), done("二"), done("三")], session="talk-2", create_ok=2
        )
        verdict = watcher.evaluate(base, later)
        self.assertFalse(verdict["same_talk_session"])
        self.assertFalse(verdict["session_reused"])
        self.assertFalse(verdict["multi_turn_complete"])

    def test_two_new_turns_same_session_pass(self):
        base = watcher.capture_baseline(snapshot(5, 1, 200, [done("一")]))
        later = snapshot(
            5,
            3,
            600,
            [done("一"), done("二", 2), done("三", 3)],
            playback_starts=2,
        )
        verdict = watcher.evaluate(base, later)
        self.assertTrue(verdict["multi_turn_complete"])
        self.assertTrue(verdict["session_reused"])
        self.assertEqual(verdict["new_speech_starts"], 2)
        self.assertEqual(verdict["turns"][-1]["text"], "三")

    def test_idle_baseline_locks_first_session(self):
        base = watcher.capture_baseline(snapshot(None, 0, 0, [], session=None, create_ok=0))
        later = snapshot(
            1,
            2,
            400,
            [done("首轮"), done("跟进")],
            session="talk-live",
            create_ok=1,
            playback_starts=2,
        )
        verdict = watcher.evaluate(base, later)
        self.assertTrue(verdict["same_conversation"])
        self.assertTrue(verdict["same_talk_session"])
        self.assertTrue(verdict["multi_turn_complete"])

    def test_delta_transcript_cannot_pass(self):
        base = watcher.capture_baseline(snapshot(5, 1, 200, [done("一")]))
        later = snapshot(
            5,
            3,
            600,
            [
                done("一"),
                {"text": "跟", "talkType": "transcript.delta", "ts": 2},
                {"text": "再", "talkType": "transcript.delta", "ts": 3},
            ],
        )
        verdict = watcher.evaluate(base, later)
        self.assertEqual(verdict["new_speech_starts"], 2)
        self.assertFalse(verdict["multi_turn_complete"])


if __name__ == "__main__":
    unittest.main()
