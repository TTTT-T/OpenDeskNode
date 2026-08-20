import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_watcher():
    if "phase_02c_c5_live" in sys.modules:
        return sys.modules["phase_02c_c5_live"]
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
    create_ok=1,
    reconnects=0,
    disconnects=0,
    invalidations=0,
    talk_connected=True,
):
    return {
        "conversation_id": conv,
        "talk_session_id": session,
        "helloed": helloed,
        "conversations": conversations,
        "talk_connected": talk_connected,
        "metrics": {"session_invalidations": invalidations},
        "talk_stats": {
            "create_ok": create_ok,
            "reconnects": reconnects,
            "disconnects": disconnects,
        },
        "recovery": {
            "talk_reconnects": reconnects,
            "talk_disconnects": disconnects,
            "session_invalidations": invalidations,
        },
    }


class C5WatcherTests(unittest.TestCase):
    def test_historical_state_cannot_pass_bridge(self):
        stale = snapshot()
        base = watcher.capture_baseline(stale)
        verdict = watcher.evaluate(base, stale, "bridge")
        self.assertFalse(verdict["ok"])

    def test_bridge_restart_new_ws_passes(self):
        base = watcher.capture_baseline(snapshot(helloed=True, conversations=1, session="talk-1"))
        later = snapshot(conv=2, session="talk-2", conversations=2, create_ok=2, helloed=True)
        verdict = watcher.evaluate(base, later, "bridge")
        self.assertTrue(verdict["ok"])
        self.assertFalse(verdict["stale_session"])

    def test_bridge_restart_reusing_talk_session_fails(self):
        base = watcher.capture_baseline(snapshot(session="talk-1", conversations=1))
        later = snapshot(session="talk-1", conversations=2, create_ok=2)
        verdict = watcher.evaluate(base, later, "bridge")
        self.assertTrue(verdict["stale_session"])
        self.assertFalse(verdict["ok"])

    def test_gateway_recovery_requires_invalidation(self):
        base = watcher.capture_baseline(
            snapshot(talk_connected=True, reconnects=0, invalidations=0, session="talk-1")
        )
        later = snapshot(
            talk_connected=True,
            reconnects=1,
            disconnects=1,
            invalidations=1,
            session="talk-2",
            create_ok=2,
        )
        verdict = watcher.evaluate(base, later, "gateway")
        self.assertTrue(verdict["ok"])

    def test_gateway_without_invalidation_fails(self):
        base = watcher.capture_baseline(snapshot(session="talk-1"))
        later = snapshot(session="talk-1", reconnects=1, talk_connected=True)
        verdict = watcher.evaluate(base, later, "gateway")
        self.assertFalse(verdict["ok"])

    def test_wifi_recovery_needs_new_hello_evidence(self):
        base = watcher.capture_baseline(snapshot(helloed=True, session="talk-1"))
        later = snapshot(helloed=True, session="talk-1")
        verdict = watcher.evaluate(base, later, "wifi")
        self.assertFalse(verdict["ok"])
        recovered = snapshot(helloed=True, conversations=2, session="talk-2", create_ok=2)
        verdict = watcher.evaluate(base, recovered, "wifi")
        self.assertTrue(verdict["ok"])


if __name__ == "__main__":
    unittest.main()
