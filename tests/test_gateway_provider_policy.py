import time
import unittest

from gateway.providers import ProviderCoordinator, ProviderTimeout, call_with_timeout
from gateway.stock_provider.models import Quote


class GatewayProviderPolicyTests(unittest.TestCase):
    def test_call_timeout_is_explicit_and_bounded(self):
        started = time.monotonic()
        with self.assertRaises(ProviderTimeout):
            call_with_timeout(lambda: time.sleep(0.2), 0.01)
        self.assertLess(time.monotonic() - started, 0.1)

    def test_retry_count_and_backoff_are_limited(self):
        calls = []

        class FakeProvider:
            def get_quotes(self, symbols):
                calls.append(list(symbols))
                if len(calls) < 2:
                    raise RuntimeError("first call fails")
                return [
                    Quote(
                        code="600519",
                        name="贵州茅台",
                        price=100.0,
                        previous_close=99.0,
                        change=1.0,
                        change_percent=1.0,
                        status="UNKNOWN",
                        timestamp="2026-08-17T09:30:00+08:00",
                        source="fake",
                    )
                ]

            def resolve_symbol(self, symbol):
                raise NotImplementedError

            def get_intraday(self, symbol, trading_date, start_time=None, end_time=None):
                raise NotImplementedError

        provider = FakeProvider()
        coordinator = ProviderCoordinator(
            provider_factory=lambda name: provider,
            timeout_seconds=1,
            retries=1,
            backoff_seconds=0,
            sleep=lambda _seconds: None,
        )
        quote = coordinator.quote("600519")
        self.assertEqual(quote.price, 100.0)
        self.assertEqual(len(calls), 2)

    def test_quotes_use_one_primary_batch_and_fallback_only_missing_symbols(self):
        symbols = ["600519", "000001", "300750", "688981"]
        primary_calls = []
        fallback_calls = []

        def quote(code, source):
            return Quote(
                code=code,
                name=code,
                price=100.0,
                previous_close=99.0,
                change=1.0,
                change_percent=1.0,
                status="UNKNOWN",
                timestamp="2026-08-17T09:30:00+08:00",
                source=source,
            )

        class FakeProvider:
            def __init__(self, calls, missing=()):
                self.calls = calls
                self.missing = set(missing)

            def get_quotes(self, requested):
                requested = list(requested)
                self.calls.append(requested)
                return [
                    quote(code, "primary" if self.calls is primary_calls else "fallback")
                    for code in requested
                    if code not in self.missing
                ]

            def resolve_symbol(self, symbol):
                raise NotImplementedError

            def get_intraday(self, symbol, trading_date, start_time=None, end_time=None):
                raise NotImplementedError

        primary = FakeProvider(primary_calls, missing={"000001"})
        fallback = FakeProvider(fallback_calls)
        coordinator = ProviderCoordinator(
            provider_factory=lambda name: (
                primary if name == coordinator.PRIMARY_QUOTE else fallback
            ),
            timeout_seconds=1,
            retries=0,
            backoff_seconds=0,
        )

        quotes, errors = coordinator.quotes(symbols)

        self.assertEqual(primary_calls, [symbols])
        self.assertEqual(fallback_calls, [["000001"]])
        self.assertEqual(set(quotes), set(symbols))
        self.assertEqual(quotes["000001"].source, "fallback")
        self.assertIn("000001", errors)
        self.assertTrue(any("primary" in item for item in errors["000001"]))


if __name__ == "__main__":
    unittest.main()
