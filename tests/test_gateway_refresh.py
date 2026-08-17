import asyncio
from datetime import date, datetime
import tempfile
import unittest

from gateway.calendar import MarketSessionClock, WeekdayCalendar, SHANGHAI_TZ
from gateway.config import GatewayConfig
from gateway.models import GatewayBar, GatewaySnapshot
from gateway.repository import SQLiteRepository
from gateway.service import StockGatewayService
from gateway.stock_provider.models import IntradayBar, Quote, SymbolRef


class FakeCoordinator:
    def __init__(self, fail_quotes=None, fail_intraday=None):
        self.fail_quotes = set(fail_quotes or ())
        self.fail_intraday = set(fail_intraday or ())
        self.quote_calls = []
        self.quote_batch_calls = []
        self.intraday_calls = []
        self._status = {
            "easyquotation-tencent": {"name": "easyquotation-tencent", "status": "FAKE"},
            "adata-sina": {"name": "adata-sina", "status": "FAKE"},
            "baidu-direct": {"name": "baidu-direct", "status": "FAKE"},
        }

    def quote(self, symbol):
        self.quote_calls.append(symbol)
        quotes, errors = self.quotes([symbol])
        if symbol in errors:
            raise RuntimeError(errors[symbol][0])
        return quotes[symbol]

    def quotes(self, symbols):
        symbols = list(symbols)
        self.quote_batch_calls.append(symbols)
        quotes = {}
        errors = {}
        for symbol in symbols:
            if symbol in self.fail_quotes:
                errors[symbol] = ["forced quote failure"]
                continue
            quotes[symbol] = Quote(
                code=symbol,
                name={"600519": "贵州茅台", "000001": "平安银行", "300750": "宁德时代", "688981": "中芯国际", "601318": "中国平安"}[symbol],
                price=100.0 + int(symbol[-2:]),
                previous_close=100.0,
                change=999.0,
                change_percent=999.0,
                status="UNKNOWN",
                timestamp="2026-08-17T10:00:00+08:00",
                source="fake-primary",
            )
        return quotes, errors

    def intraday(self, symbol, trading_date, start_time=None, end_time=None):
        self.intraday_calls.append((symbol, trading_date))
        if symbol in self.fail_intraday:
            raise RuntimeError("forced intraday failure")
        return [
            IntradayBar(
                code=symbol,
                timestamp=trading_date + "T09:30:00+08:00",
                price=100.0,
                open=None,
                high=None,
                low=None,
                close=100.0,
                volume=1.0,
                amount=100.0,
                source="fake-intraday",
            )
        ]

    def resolve_symbol(self, symbol):
        names = {"600519": "贵州茅台", "000001": "平安银行", "300750": "宁德时代", "688981": "中芯国际"}
        return SymbolRef(symbol, "SSE" if symbol.startswith("6") else "SZSE", symbol, names[symbol])

    def status(self):
        return self._status

    def restore_status(self, value):
        return None


class GatewayRefreshTests(unittest.TestCase):
    def make(self, coordinator, stale_seconds=300.0, calendar=None):
        temporary = tempfile.TemporaryDirectory()
        repository = SQLiteRepository(temporary.name + "/gateway.sqlite3")
        repository.initialize()
        repository.ensure_seed_device()
        config = GatewayConfig(
            database_path=temporary.name + "/gateway.sqlite3",
            log_path=":memory:",
            quote_ttl_seconds=5,
            intraday_ttl_seconds=30,
            off_market_refresh_seconds=300,
            stale_seconds=stale_seconds,
            provider_timeout_seconds=1,
            provider_retries=0,
            provider_backoff_seconds=0,
        )
        clock = MarketSessionClock(calendar or WeekdayCalendar())
        service = StockGatewayService(repository, config, coordinator, clock)
        return temporary, repository, service

    def test_partial_failure_keeps_old_snapshot_and_updates_other_symbols(self):
        temporary, repository, service = self.make(
            FakeCoordinator(fail_quotes={"000001"}, fail_intraday={"000001"})
        )
        self.addCleanup(temporary.cleanup)
        repository.upsert_snapshot(
            GatewaySnapshot(
                symbol="000001",
                name="旧平安银行",
                current_price=9.0,
                previous_close=10.0,
                change_amount=-1.0,
                change_percent=-10.0,
                last_success_at="2026-08-17T09:00:00+08:00",
                quote_fetched_at="2026-08-17T09:00:00+08:00",
                intraday_fetched_at="2026-08-17T09:00:00+08:00",
                quote_data_timestamp="2026-08-17T09:00:00+08:00",
            )
        )
        result = asyncio.run(
            service.refresh_once(
                force=True,
                now=datetime(2026, 8, 17, 10, 0, tzinfo=SHANGHAI_TZ),
            )
        )
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(repository.get_snapshot("000001").current_price, 9.0)
        self.assertEqual(repository.get_snapshot("600519").current_price, 119.0)
        self.assertTrue(repository.get_snapshot("600519").intraday)
        self.assertEqual(repository.get_snapshot("000001").last_success_at, "2026-08-17T09:00:00+08:00")

    def test_refresh_uses_one_batch_for_four_unique_due_quotes(self):
        coordinator = FakeCoordinator()
        temporary, _repository, service = self.make(coordinator)
        self.addCleanup(temporary.cleanup)

        asyncio.run(
            service.refresh_once(
                force=True,
                now=datetime(2026, 8, 17, 10, 0, tzinfo=SHANGHAI_TZ),
            )
        )

        self.assertEqual(len(coordinator.quote_batch_calls), 1)
        self.assertEqual(
            set(coordinator.quote_batch_calls[0]),
            {"600519", "000001", "300750", "688981"},
        )
        self.assertEqual(coordinator.quote_calls, [])

    def test_stale_is_derived_from_last_success_and_restart_serves_sqlite_fallback(self):
        temporary, repository, service = self.make(
            FakeCoordinator(fail_quotes={"600519", "000001", "300750", "688981"}, fail_intraday={"600519", "000001", "300750", "688981"}),
            stale_seconds=300,
        )
        self.addCleanup(temporary.cleanup)
        repository.upsert_snapshot(
            GatewaySnapshot(
                symbol="600519",
                name="贵州茅台",
                current_price=123.0,
                previous_close=120.0,
                change_amount=3.0,
                change_percent=2.5,
                last_success_at="2026-08-17T09:00:00+08:00",
                quote_fetched_at="2026-08-17T09:00:00+08:00",
                quote_data_timestamp="2026-08-17T09:00:00+08:00",
            )
        )
        dashboard = service.dashboard(
            "device-a", datetime(2026, 8, 17, 9, 4, tzinfo=SHANGHAI_TZ)
        )
        self.assertEqual(dashboard["quotes"][0]["current_price"], 123.0)
        self.assertFalse(dashboard["stale"])
        self.assertNotIn("next_open_in_seconds", dashboard)
        compact = service.dashboard(
            "device-a",
            datetime(2026, 8, 17, 9, 4, tzinfo=SHANGHAI_TZ),
            intraday_samples=32,
        )
        self.assertEqual(compact["next_open_in_seconds"], 1560)
        stale = service.dashboard(
            "device-a", datetime(2026, 8, 17, 9, 6, tzinfo=SHANGHAI_TZ)
        )
        self.assertTrue(stale["quotes"][0]["stale"])
        repository.close()

        reopened = SQLiteRepository(temporary.name + "/gateway.sqlite3")
        reopened.initialize()
        self.addCleanup(reopened.close)
        restarted = StockGatewayService(
            reopened,
            service.config,
            FakeCoordinator(fail_quotes={"600519"}),
            MarketSessionClock(WeekdayCalendar()),
        )
        fallback = restarted.dashboard(
            "device-a", datetime(2026, 8, 17, 9, 4, tzinfo=SHANGHAI_TZ)
        )
        self.assertEqual(fallback["quotes"][0]["current_price"], 123.0)
        self.assertEqual(fallback["quotes"][0]["data_timestamp"], "2026-08-17T09:00:00+08:00")

    def test_dashboard_downsamples_intraday_evenly_and_preserves_endpoints(self):
        temporary, repository, service = self.make(FakeCoordinator())
        self.addCleanup(temporary.cleanup)
        bars = tuple(
            GatewayBar(
                timestamp="2026-08-17T%02d:%02d:00+08:00" % (9 + index // 60, index % 60),
                price=100.0 + index / 100.0,
                open=None,
                high=None,
                low=None,
                close=100.0 + index / 100.0,
                volume=None,
                amount=None,
                source="fixture",
            )
            for index in range(240)
        )
        repository.upsert_snapshot(
            GatewaySnapshot(
                symbol="600519",
                name="贵州茅台",
                current_price=102.39,
                previous_close=100.0,
                intraday=bars,
                intraday_session_date="2026-08-17",
                last_success_at="2026-08-17T10:00:00+08:00",
            )
        )

        full = service.dashboard(
            "device-a", datetime(2026, 8, 17, 10, 0, tzinfo=SHANGHAI_TZ)
        )
        bounded = service.dashboard(
            "device-a",
            datetime(2026, 8, 17, 10, 0, tzinfo=SHANGHAI_TZ),
            intraday_samples=32,
        )

        self.assertEqual(len(full["quotes"][0]["intraday"]), 240)
        self.assertEqual(len(bounded["quotes"][0]["intraday"]), 32)
        self.assertEqual(len(bounded["intraday"][0]["bars"]), 32)
        self.assertEqual(bounded["quotes"][0]["intraday"][0], bars[0].to_dict())
        self.assertEqual(bounded["quotes"][0]["intraday"][-1], bars[-1].to_dict())

    def test_refresh_lifecycle_starts_and_stops_cleanly(self):
        temporary, repository, service = self.make(FakeCoordinator())
        self.addCleanup(temporary.cleanup)

        async def run():
            await service.start()
            await asyncio.sleep(0.05)
            await service.stop()
            return service._task, service._started

        task, started = asyncio.run(run())
        self.assertIsNone(task)
        self.assertFalse(started)
        self.assertIsNotNone(repository.get_service_state("last_refresh_at"))

    def test_cache_ttl_skips_a_recent_refresh_and_unique_symbols_are_one_pass(self):
        coordinator = FakeCoordinator()
        temporary, repository, service = self.make(coordinator)
        self.addCleanup(temporary.cleanup)
        repository.create_device(
            "device-b",
            "Desk",
            ["000001", "300750", "688981", "601318"],
        )
        first = asyncio.run(
            service.refresh_once(
                force=True,
                now=datetime(2026, 8, 17, 10, 0, tzinfo=SHANGHAI_TZ),
            )
        )
        self.assertEqual(first["attempted"], 5)
        quote_batch_count = len(coordinator.quote_batch_calls)
        intraday_count = len(coordinator.intraday_calls)
        asyncio.run(
            service.refresh_once(
                force=False,
                now=datetime(2026, 8, 17, 10, 0, 1, tzinfo=SHANGHAI_TZ),
            )
        )
        self.assertEqual(len(coordinator.quote_batch_calls), quote_batch_count)
        self.assertEqual(len(coordinator.intraday_calls), intraday_count)

    def test_startup_force_fetches_latest_session_on_weekend(self):
        coordinator = FakeCoordinator()
        temporary, _repository, service = self.make(coordinator)
        self.addCleanup(temporary.cleanup)

        result = asyncio.run(
            service.refresh_once(
                force=True,
                now=datetime(2026, 8, 16, 12, 0, tzinfo=SHANGHAI_TZ),
            )
        )

        self.assertEqual(result["market_session"]["state"], "STANDBY")
        self.assertEqual(
            {trading_date for _symbol, trading_date in coordinator.intraday_calls},
            {"2026-08-14"},
        )

    def test_startup_force_fetches_latest_session_before_holiday(self):
        coordinator = FakeCoordinator()
        temporary, _repository, service = self.make(
            coordinator, calendar=WeekdayCalendar({date(2026, 10, 1)})
        )
        self.addCleanup(temporary.cleanup)

        result = asyncio.run(
            service.refresh_once(
                force=True,
                now=datetime(2026, 10, 1, 10, 0, tzinfo=SHANGHAI_TZ),
            )
        )

        self.assertEqual(result["market_session"]["state"], "STANDBY")
        self.assertEqual(
            {trading_date for _symbol, trading_date in coordinator.intraday_calls},
            {"2026-09-30"},
        )

    def test_premarket_does_not_request_untraded_current_session(self):
        coordinator = FakeCoordinator()
        temporary, _repository, service = self.make(coordinator)
        self.addCleanup(temporary.cleanup)

        result = asyncio.run(
            service.refresh_once(
                force=True,
                now=datetime(2026, 8, 17, 9, 0, tzinfo=SHANGHAI_TZ),
            )
        )

        self.assertEqual(result["market_session"]["state"], "PRE_MARKET")
        self.assertEqual(
            {trading_date for _symbol, trading_date in coordinator.intraday_calls},
            {"2026-08-14"},
        )


if __name__ == "__main__":
    unittest.main()
