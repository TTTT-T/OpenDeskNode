import unittest

from gateway.service import canonicalize_quote
from gateway.stock_provider.models import Quote


class GatewayProviderConversionTests(unittest.TestCase):
    def test_gateway_recomputes_change_without_trusting_provider_values(self):
        timestamp, amount, percent = canonicalize_quote(
            Quote(
                code="600519",
                name="贵州茅台",
                price=110.0,
                previous_close=100.0,
                change=-999.0,
                change_percent=-999.0,
                status="UNKNOWN",
                timestamp="2026-08-17T09:30:00+08:00",
                source="fake",
            )
        )
        self.assertEqual(timestamp, "2026-08-17T09:30:00+08:00")
        self.assertEqual(amount, 10.0)
        self.assertEqual(percent, 10.0)

    def test_missing_source_timestamp_is_not_replaced_by_fetch_time(self):
        timestamp, amount, percent = canonicalize_quote(
            Quote(
                code="000001",
                name="平安银行",
                price=11.0,
                previous_close=10.0,
                change=1.0,
                change_percent=10.0,
                status="UNKNOWN",
                timestamp=None,
                source="fallback",
            )
        )
        self.assertIsNone(timestamp)
        self.assertEqual(amount, 1.0)
        self.assertEqual(percent, 10.0)


if __name__ == "__main__":
    unittest.main()
