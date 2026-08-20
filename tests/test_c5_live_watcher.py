import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_watcher():
    if "phase_02c_c5_live" in sys.modules:
        del sys.modules["phase_02c_c5_live"]
    spec = importlib.util.spec_from_file_location(
        "phase_02c_c5_live", ROOT / "scripts" / "phase-02c-c5-live.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["phase_02c_c5_live"] = module
    return module


watcher = _load_watcher()


def snapshot(
    conv=1,
    session="talk-1",
    helloed=True,
    conversations=1,
    create_ok=0,
    speech_starts=0,
    uplink_frames=0,
    transcripts=None,
    talk_connected=True,
):
    return {
        "conversation_id": conv,
        "talk_session_id": session,
        "helloed": helloed,
        "conversations": conversations,
        "talk_connected": talk_connected,
        "metrics": {
            "speech_starts": speech_starts,
            "uplink_frames": uplink_frames,
            "user_transcripts": transcripts or [],
            "session_invalidations": 0,
        },
        "talk_stats": {"create_ok": create_ok},
    }


def done(text="hi"):
    return {"text": text, "talkType": "transcript.done", "ts": 1.0}


def usable(session="talk-2", conversations=1):
    return snapshot(
        conv=2,
        session=session,
        conversations=conversations,
        create_ok=1,
        speech_starts=1,
        uplink_frames=40,
        transcripts=[done()],
        helloed=True,
        talk_connected=True,
    )


class C5WatcherTests(unittest.TestCase):
    def test_historical_state_cannot_pass(self):
        stale = snapshot(session="talk-1", create_ok=1, speech_starts=2, uplink_frames=400)
        state = watcher.init_state(stale)
        verdict = watcher.evaluate(state, stale, "bridge")
        self.assertFalse(verdict["ok"])

    def test_hello_only_after_bridge_outage_cannot_pass(self):
        state = watcher.init_state(snapshot(session="talk-old", conversations=9))
        watcher.step(state, None, False, "bridge")
        hello = snapshot(session=None, helloed=True, conversations=1, speech_starts=0)
        verdict = watcher.step(state, hello, True, "bridge")
        self.assertTrue(verdict["saw_outage"])
        self.assertTrue(verdict["recovered"])
        self.assertTrue(verdict["hello_only"])
        self.assertFalse(verdict["ok"])

    def test_conversations_delta_alone_cannot_pass(self):
        state = watcher.init_state(snapshot(session="talk-old", conversations=1))
        watcher.step(state, None, False, "bridge")
        later = snapshot(session="talk-old", conversations=99, helloed=True, create_ok=0)
        verdict = watcher.step(state, later, True, "bridge")
        self.assertFalse(verdict["used_conversations_delta"])
        self.assertTrue(verdict["stale_session"])
        self.assertFalse(verdict["ok"])

    def test_bridge_restart_usability_passes_with_saved_stale_id(self):
        state = watcher.init_state(snapshot(session="talk-old", conversations=7))
        watcher.step(state, None, False, "bridge")
        watcher.step(state, snapshot(session=None, helloed=True, conversations=1), True, "bridge")
        verdict = watcher.step(state, usable(session="talk-new", conversations=1), True, "bridge")
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["stale_session_id"], "talk-old")
        self.assertEqual(verdict["new_session_id"], "talk-new")
        self.assertFalse(verdict["used_conversations_delta"])

    def test_reusing_stale_session_fails(self):
        state = watcher.init_state(snapshot(session="talk-old"))
        watcher.step(state, None, False, "bridge")
        watcher.step(state, snapshot(session=None, helloed=True), True, "bridge")
        verdict = watcher.step(state, usable(session="talk-old"), True, "bridge")
        self.assertTrue(verdict["stale_session"])
        self.assertFalse(verdict["ok"])

    def test_gateway_hello_only_fails_usability_passes(self):
        state = watcher.init_state(snapshot(session="talk-1", talk_connected=True))
        watcher.step(state, snapshot(session=None, talk_connected=False, helloed=True), True, "gateway")
        hello = snapshot(session=None, talk_connected=True, helloed=True, create_ok=0)
        verdict = watcher.step(state, hello, True, "gateway")
        self.assertTrue(verdict["recovered"])
        self.assertFalse(verdict["ok"])
        verdict = watcher.step(state, usable(session="talk-2"), True, "gateway")
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["stale_session_id"], "talk-1")

    def test_wifi_requires_new_session_and_speech(self):
        state = watcher.init_state(snapshot(session="talk-1", helloed=True))
        watcher.step(state, snapshot(session=None, helloed=False, talk_connected=True), True, "wifi")
        hello = snapshot(session=None, helloed=True, talk_connected=True)
        verdict = watcher.step(state, hello, True, "wifi")
        self.assertFalse(verdict["ok"])
        verdict = watcher.step(state, usable(session="talk-2"), True, "wifi")
        self.assertTrue(verdict["ok"])


if __name__ == "__main__":
    unittest.main()
