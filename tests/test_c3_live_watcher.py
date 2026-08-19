import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_watcher():
    if "phase_02c_c3_live" in sys.modules:
        return sys.modules["phase_02c_c3_live"]
    spec = importlib.util.spec_from_file_location(
        "phase_02c_c3_live", ROOT / "scripts" / "phase-02c-c3-live.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["phase_02c_c3_live"] = module
    return module


watcher = _load_watcher()


def snapshot(
    conv,
    frames,
    interrupts,
    transcripts,
    conversations=1,
    session="talk-1",
    cancel_ok=0,
):
    return {
        "conversation_id": conv,
        "talk_session_id": session,
        "conversations": conversations,
        "metrics": {
            "uplink_frames": frames,
            "interrupts": interrupts,
            "user_transcripts": transcripts,
            "dropped_after_interrupt": 0,
        },
        "talk_stats": {"event_seq": 0, "cancel_ok": cancel_ok},
    }


class C3WatcherBaselineTests(unittest.TestCase):
    def test_historical_interrupt_cannot_pass(self):
        stale = snapshot(5, 200, 1, [{"text": "旧", "talkType": "transcript.done"}])
        base = watcher.capture_baseline(stale)
        verdict = watcher.evaluate(base, stale)
        self.assertEqual(verdict["new_interrupts"], 0)
        self.assertFalse(verdict["barge_in_complete"])

    def test_interrupt_without_new_transcript_cannot_pass(self):
        base = watcher.capture_baseline(snapshot(5, 100, 0, []))
        later = snapshot(5, 180, 1, [])
        verdict = watcher.evaluate(base, later)
        self.assertEqual(verdict["new_interrupts"], 1)
        self.assertTrue(verdict["new_uplink"])
        self.assertFalse(verdict["barge_in_complete"])

    def test_new_conversation_cannot_pass(self):
        base = watcher.capture_baseline(snapshot(5, 100, 0, []))
        later = snapshot(
            6, 40, 1, [{"text": "新会话", "talkType": "transcript.done"}]
        )
        verdict = watcher.evaluate(base, later)
        self.assertFalse(verdict["same_conversation"])
        self.assertFalse(verdict["barge_in_complete"])

    def test_same_cid_interrupt_uplink_and_transcript_pass(self):
        base = watcher.capture_baseline(snapshot(5, 100, 0, []))
        later = snapshot(
            5,
            180,
            1,
            [{"text": "打断后再说", "talkType": "transcript.done"}],
            cancel_ok=1,
        )
        verdict = watcher.evaluate(base, later)
        self.assertTrue(verdict["barge_in_complete"])
        self.assertEqual(verdict["transcript"]["text"], "打断后再说")

    def test_delta_transcript_cannot_pass(self):
        base = watcher.capture_baseline(snapshot(5, 100, 0, []))
        later = snapshot(5, 180, 1, [{"text": "打", "talkType": "transcript.delta"}])
        verdict = watcher.evaluate(base, later)
        self.assertFalse(verdict["barge_in_complete"])


if __name__ == "__main__":
    unittest.main()
