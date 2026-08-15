import sqlite3
import tempfile
import unittest

from gateway.models import GatewayBar, GatewaySnapshot
from gateway.repository import (
    DEFAULT_DEVICE_ID,
    DEFAULT_SYMBOLS,
    SQLiteRepository,
)


class GatewayRepositoryTests(unittest.TestCase):
    def make_repository(self):
        temporary = tempfile.TemporaryDirectory()
        repository = SQLiteRepository(temporary.name + "/gateway.sqlite3")
        repository.initialize()
        return temporary, repository

    def test_seed_has_exactly_four_ordered_slots_and_constraints(self):
        temporary, repository = self.make_repository()
        self.addCleanup(temporary.cleanup)
        repository.ensure_seed_device()
        slots = repository.get_watchlist(DEFAULT_DEVICE_ID)
        self.assertEqual([slot.slot for slot in slots], [1, 2, 3, 4])
        self.assertEqual([slot.symbol for slot in slots], list(DEFAULT_SYMBOLS))
        self.assertEqual(len(repository.unique_symbols()), 4)
        with repository._lock:  # schema-level CHECK is the subject of this test
            repository._connection.execute(
                "INSERT INTO devices(device_id, name, created_at) VALUES (?, ?, ?)",
                ("raw-device", "Raw", "2026-08-15T00:00:00+08:00"),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                repository._connection.execute(
                    """
                    INSERT INTO watchlist_slots(
                        device_id, slot_1_symbol, slot_2_symbol,
                        slot_3_symbol, slot_4_symbol
                    ) VALUES ('raw-device', '600519', '600519', '300750', '688981')
                    """
                )

    def test_multi_device_order_and_reopen_persistence(self):
        temporary, repository = self.make_repository()
        self.addCleanup(temporary.cleanup)
        repository.ensure_seed_device()
        repository.create_device(
            "device-b",
            "Desk",
            ["000001", "300750", "688981", "600519"],
            ["平安银行", "宁德时代", "中芯国际", "贵州茅台"],
        )
        reordered = repository.reorder_watchlist("device-b", [4, 1, 3, 2])
        self.assertEqual(
            [slot.symbol for slot in reordered],
            ["600519", "000001", "688981", "300750"],
        )
        snapshot = GatewaySnapshot(
            symbol="600519",
            name="贵州茅台",
            current_price=100.0,
            previous_close=99.0,
            change_amount=1.0,
            change_percent=1.010101,
            status="UNKNOWN",
            intraday=(
                GatewayBar(
                    timestamp="2026-08-15T09:30:00+08:00",
                    price=100.0,
                    open=None,
                    high=None,
                    low=None,
                    close=100.0,
                    volume=10.0,
                    amount=1000.0,
                    source="fake",
                ),
            ),
            intraday_session_date="2026-08-15",
            quote_data_timestamp="2026-08-15T09:30:00+08:00",
            intraday_data_timestamp="2026-08-15T09:30:00+08:00",
            last_success_at="2026-08-15T09:30:01+08:00",
        )
        repository.upsert_snapshot(snapshot)
        repository.set_setting("quote_ttl_seconds", 5)
        repository.set_service_state("last_refresh_at", "2026-08-15T09:30:01+08:00")
        repository.close()

        reopened = SQLiteRepository(temporary.name + "/gateway.sqlite3")
        reopened.initialize()
        self.addCleanup(reopened.close)
        self.assertEqual([device.device_id for device in reopened.list_devices()], ["device-a", "device-b"])
        self.assertEqual(
            [slot.symbol for slot in reopened.get_watchlist("device-b")],
            ["600519", "000001", "688981", "300750"],
        )
        loaded = reopened.get_snapshot("600519")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.intraday[0].timestamp, "2026-08-15T09:30:00+08:00")
        self.assertEqual(reopened.get_setting("quote_ttl_seconds"), 5)
        self.assertEqual(reopened.get_service_state("last_refresh_at"), "2026-08-15T09:30:01+08:00")

    def test_snapshot_table_is_latest_only_not_long_history(self):
        temporary, repository = self.make_repository()
        self.addCleanup(temporary.cleanup)
        repository.initialize()
        first = GatewaySnapshot(symbol="600519", current_price=1.0)
        second = GatewaySnapshot(symbol="600519", current_price=2.0)
        repository.upsert_snapshot(first)
        repository.upsert_snapshot(second)
        self.assertEqual(repository.snapshot_count(), 1)
        self.assertEqual(repository.get_snapshot("600519").current_price, 2.0)


if __name__ == "__main__":
    unittest.main()
