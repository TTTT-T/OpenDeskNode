import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    if "phase_02c_accept" in sys.modules:
        del sys.modules["phase_02c_accept"]
    spec = importlib.util.spec_from_file_location(
        "phase_02c_accept", ROOT / "scripts" / "phase-02c-accept.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["phase_02c_accept"] = module
    return module


accept = _load()


class AcceptHardwareTests(unittest.TestCase):
    def test_prompts_cover_required_cases(self):
        for name in accept.CASES:
            self.assertIn(name, accept.PROMPTS)
        summary = accept.render_summary(
            {
                "C4_MULTI_TURN": {"status": "PASS"},
                "C3_LOCAL_STOP": {"status": "PASS"},
                "C5_BRIDGE_RECOVERY": {"status": "PASS"},
                "C5_GATEWAY_RECOVERY": {"status": "PASS"},
                "C5_WIFI_RECOVERY": {"status": "PASS"},
                "STOCK_REGRESSION": {"status": "PASS"},
                "VOICE_LONG_RUN": {"status": "PENDING"},
                "WAKE_WORD": {"status": "PENDING"},
            }
        )
        self.assertIn("C4_MULTI_TURN            PASS", summary)
        self.assertIn("WAKE_WORD                PENDING", summary)

    def test_wake_is_never_auto_pass(self):
        item = accept.evaluate_pending("WAKE_WORD")
        self.assertEqual(item["status"], "WAKE MODEL PENDING")
        self.assertNotEqual(item["status"], "PASS")

    def test_c3_without_ear_is_pending_not_pass(self):
        baseline = {"conversation_id": 6, "interrupts": 0, "cancel_ok": 0}
        later = {
            "conversation_id": 6,
            "metrics": {"interrupts": 1},
            "talk_stats": {"cancel_ok": 1},
        }
        item = accept.evaluate_c3(baseline, later, None)
        self.assertEqual(item["status"], "HW-ACCEPTANCE-PENDING")

    def test_stock_without_observation_is_pending(self):
        item = accept.evaluate_stock(None, None)
        self.assertEqual(item["status"], "HW-ACCEPTANCE-PENDING")
        self.assertNotEqual(item["status"], "PASS")

    def test_run_acceptance_starts_watchers_in_order_and_asks_humans(self):
        calls = []
        asks = []

        def watch(name):
            calls.append(name)
            if name == "C4_MULTI_TURN":
                return {"ok": True, "verdict": {"multi_turn_complete": True}}
            if name == "C3_LOCAL_STOP":
                return {"ok": True, "verdict": {"barge_in_complete": True}}
            return {
                "ok": True,
                "verdict": {
                    "ok": True,
                    "new_speech_starts": 1,
                    "new_uplink": True,
                    "new_create_ok": 1,
                    "new_transcript_done": 1,
                    "stale_session": False,
                },
            }

        def ask(prompt):
            asks.append(prompt)
            return True

        payload = accept.run_acceptance(watch_fn=watch, ask_fn=ask, head="test")
        self.assertEqual(
            calls,
            [
                "C4_MULTI_TURN",
                "C3_LOCAL_STOP",
                "C5_BRIDGE_RECOVERY",
                "C5_GATEWAY_RECOVERY",
                "C5_WIFI_RECOVERY",
            ],
        )
        self.assertEqual(len(asks), 3)
        results = payload["results"]
        self.assertEqual(results["C4_MULTI_TURN"]["status"], "PASS")
        self.assertEqual(results["C3_LOCAL_STOP"]["status"], "PASS")
        self.assertEqual(results["C5_BRIDGE_RECOVERY"]["status"], "PASS")
        self.assertEqual(results["STOCK_REGRESSION"]["status"], "PASS")
        self.assertEqual(results["WAKE_WORD"]["status"], "WAKE MODEL PENDING")
        self.assertIn("C4_MULTI_TURN", accept.WATCH_ORDER)
        for name in (
            "C5_BRIDGE_RECOVERY",
            "C5_GATEWAY_RECOVERY",
            "C5_WIFI_RECOVERY",
        ):
            self.assertIn("ARMED", accept.PROMPTS[name])
            self.assertIn("先按 BOOT", accept.PROMPTS[name])

    def test_c3_yes_without_watcher_ok_is_fail(self):
        item = accept.evaluate_c3_from_watch({"ok": False, "verdict": {}}, True)
        self.assertEqual(item["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
