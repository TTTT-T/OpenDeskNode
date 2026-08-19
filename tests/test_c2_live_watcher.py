import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_watcher():
    if "phase_02c_c2_live" in sys.modules:
        return sys.modules["phase_02c_c2_live"]
    spec = importlib.util.spec_from_file_location(
        "phase_02c_c2_live", ROOT / "scripts" / "phase-02c-c2-live.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["phase_02c_c2_live"] = module
    return module


watcher = _load_watcher()


def snapshot(conv, frames, starts, ends, peak=1200, conversations=1, session="talk-1"):
    return {
        "conversation_id": conv,
        "talk_session_id": session,
        "conversations": conversations,
        "metrics": {
            "downlink_frames": frames,
            "playback_starts": starts,
            "playback_ends": ends,
            "downlink_peak": peak,
        },
        "talk_stats": {"event_seq": 0},
    }


class C2WatcherBaselineTests(unittest.TestCase):
    def test_historical_downlink_cannot_pass(self):
        stale = snapshot(5, 478, 1, 1)
        base = watcher.capture_baseline(stale)
        verdict = watcher.evaluate(base, stale)
        self.assertFalse(verdict["new_downlink"])
        self.assertEqual(verdict["new_playback_ends"], 0)
        self.assertFalse(verdict["playback_complete"])

    def test_new_frames_without_playback_end_cannot_pass(self):
        base = watcher.capture_baseline(snapshot(5, 0, 0, 0, peak=0))
        later = snapshot(5, 40, 1, 0, peak=800)
        verdict = watcher.evaluate(base, later)
        self.assertTrue(verdict["new_downlink"])
        self.assertEqual(verdict["new_playback_ends"], 0)
        self.assertFalse(verdict["playback_complete"])

    def test_silent_downlink_cannot_pass(self):
        base = watcher.capture_baseline(snapshot(5, 0, 0, 0, peak=0))
        later = snapshot(5, 40, 1, 1, peak=0)
        verdict = watcher.evaluate(base, later)
        self.assertTrue(verdict["new_downlink"])
        self.assertEqual(verdict["new_playback_ends"], 1)
        self.assertFalse(verdict["playback_complete"])

    def test_new_downlink_and_playback_end_pass(self):
        base = watcher.capture_baseline(snapshot(5, 0, 0, 0, peak=0))
        later = snapshot(5, 80, 1, 1, peak=2400)
        verdict = watcher.evaluate(base, later)
        self.assertTrue(verdict["playback_complete"])
        self.assertEqual(verdict["downlink_peak"], 2400)

    def test_stale_session_cannot_pass(self):
        stale = snapshot(None, 478, 1, 1)
        base = watcher.capture_baseline(stale)
        still = snapshot(None, 478, 1, 1)
        verdict = watcher.evaluate(base, still)
        self.assertFalse(verdict["playback_complete"])

    def test_fresh_session_after_baseline_counts(self):
        stale = snapshot(None, 478, 1, 1)
        base = watcher.capture_baseline(stale)
        fresh = snapshot(2, 60, 1, 1, peak=1800)
        verdict = watcher.evaluate(base, fresh)
        self.assertTrue(verdict["playback_complete"])


if __name__ == "__main__":
    unittest.main()
