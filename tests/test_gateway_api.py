import tempfile
import unittest

from fastapi.testclient import TestClient

from gateway.app import create_app
from gateway.calendar import MarketSessionClock, WeekdayCalendar
from gateway.config import GatewayConfig
from gateway.repository import SQLiteRepository
from tests.test_gateway_refresh import FakeCoordinator


class GatewayAPITests(unittest.TestCase):
    def make_client(self):
        temporary = tempfile.TemporaryDirectory()
        repository = SQLiteRepository(temporary.name + "/gateway.sqlite3")
        config = GatewayConfig(
            database_path=temporary.name + "/gateway.sqlite3",
            log_path=":memory:",
            provider_timeout_seconds=1,
            provider_retries=0,
            provider_backoff_seconds=0,
        )
        app = create_app(
            config=config,
            repository=repository,
            providers=FakeCoordinator(),
            market_clock=MarketSessionClock(WeekdayCalendar()),
        )
        return temporary, TestClient(app)

    def test_dashboard_schema_is_stable_and_only_dashboard_touches_access(self):
        temporary, client = self.make_client()
        self.addCleanup(temporary.cleanup)
        with client:
            before = client.get("/api/v1/devices/device-a").json()["device"]["last_accessed_at"]
            preview = client.get("/api/v1/devices/device-a/preview")
            self.assertEqual(preview.status_code, 200)
            after_preview = client.get("/api/v1/devices/device-a").json()["device"]["last_accessed_at"]
            self.assertEqual(before, after_preview)
            response = client.get("/api/v1/dashboard/device-a")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["schema_version"], 1)
            self.assertEqual(len(body["watchlist"]), 4)
            self.assertEqual(len(body["quotes"]), 4)
            self.assertEqual(len(body["intraday"]), 4)
            self.assertIn("market_session", body)
            self.assertIn("next_open_at", body)
            self.assertIn("gateway_timestamp", body)
            self.assertIn("data_timestamp", body)
            self.assertIn("freshness", body)
            for quote in body["quotes"]:
                self.assertTrue(
                    {
                        "symbol",
                        "name",
                        "current_price",
                        "previous_close",
                        "change_amount",
                        "change_percent",
                        "status",
                        "intraday",
                        "data_timestamp",
                        "last_success_at",
                        "freshness",
                        "stale",
                    }.issubset(quote)
                )
            touched = client.get("/api/v1/devices/device-a").json()["device"]["last_accessed_at"]
            self.assertIsNotNone(touched)

    def test_device_crud_resolve_confirm_save_and_reorder(self):
        temporary, client = self.make_client()
        self.addCleanup(temporary.cleanup)
        with client:
            created = client.post(
                "/api/v1/devices",
                json={
                    "device_id": "device-b",
                    "name": "Desk",
                    "symbols": ["600519", "000001", "300750", "688981"],
                },
            )
            self.assertEqual(created.status_code, 201)
            self.assertEqual(len(created.json()["watchlist"]), 4)
            resolved = client.get("/api/v1/symbols/resolve?symbol=600519")
            self.assertEqual(resolved.status_code, 200)
            self.assertEqual(resolved.json()["symbol"]["name"], "贵州茅台")
            confirmed = client.post(
                "/api/v1/symbols/confirm",
                json={"symbol": "600519", "name": "贵州茅台"},
            )
            self.assertEqual(confirmed.status_code, 200)
            self.assertTrue(confirmed.json()["confirmed"])
            saved = client.post(
                "/api/v1/devices/device-b/watchlist",
                json={
                    "symbols": ["688981", "300750", "000001", "600519"],
                    "names": ["中芯国际", "宁德时代", "平安银行", "贵州茅台"],
                },
            )
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.json()["slots"][0]["symbol"], "688981")
            reordered = client.post(
                "/api/v1/devices/device-b/watchlist/reorder",
                json={"slot_order": [4, 1, 2, 3]},
            )
            self.assertEqual(reordered.status_code, 200)
            self.assertEqual(
                [slot["symbol"] for slot in reordered.json()["slots"]],
                ["600519", "688981", "300750", "000001"],
            )
            invalid = client.post(
                "/api/v1/devices/device-b/watchlist",
                json={"symbols": ["sh600519", "000001", "300750", "688981"]},
            )
            self.assertEqual(invalid.status_code, 422)

    def test_health_and_local_web_are_available(self):
        temporary, client = self.make_client()
        self.addCleanup(temporary.cleanup)
        with client:
            health = client.get("/healthz")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["service"], "stock-gateway")
            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn("明确保存", page.text)
            self.assertIn("data-resolve", page.text)
            self.assertNotIn("cdnjs.cloudflare.com", page.text)


if __name__ == "__main__":
    unittest.main()
