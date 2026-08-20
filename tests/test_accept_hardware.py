import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    if "phase_02c_accept" in sys.modules:
        return sys.modules["phase_02c_accept"]
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


if __name__ == "__main__":
    unittest.main()
