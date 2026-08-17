import inspect
import unittest

from gateway.stock_provider.adapters import (
    BaiduDirectAdapter,
    build_provider,
    intraday_from_mapping,
    normalize_code,
    parse_baidu_priceinfo,
    quote_from_mapping,
)
from gateway.stock_provider.models import IntradayBar, Quote, SymbolRef
from gateway.stock_provider.protocol import (
    ProviderCapabilityError,
    ProviderError,
    StockProvider,
)


class StockProviderBoundaryTests(unittest.TestCase):
    def test_protocol_has_only_the_three_provider_operations(self):
        names = {
            name
            for name, member in inspect.getmembers(StockProvider)
            if not name.startswith("_") and callable(member)
        }
        self.assertEqual(
            names,
            {"get_intraday", "get_quotes", "resolve_symbol"},
        )

    def test_symbol_normalization_preserves_exchange_mapping(self):
        self.assertEqual(normalize_code("sh600519"), "600519")
        self.assertEqual(normalize_code("000001"), "000001")
        self.assertEqual(normalize_code("sz300750"), "300750")
        with self.assertRaises(ValueError):
            normalize_code("not-a-share")
        with self.assertRaises(ValueError):
            normalize_code("bad600519")

    def test_tencent_row_is_converted_inside_adapter_boundary(self):
        quote = quote_from_mapping(
            "600519",
            {
                "name": "贵州茅台",
                "now": 1341.99,
                "close": 1355.29,
                "涨跌": -13.30,
                "涨跌(%)": -0.98,
                "datetime": "2026-08-14 16:14:43",
                "涨停价": 1490.82,
                "跌停价": 1219.76,
            },
            "Tencent via easyquotation",
        )
        self.assertIsInstance(quote, Quote)
        self.assertEqual(quote.name, "贵州茅台")
        self.assertEqual(quote.previous_close, 1355.29)
        self.assertEqual(quote.status, "NORMAL")
        self.assertEqual(quote.limit_up, 1490.82)
        self.assertIn("+08:00", quote.timestamp)

    def test_intraday_row_is_converted_inside_adapter_boundary(self):
        bar = intraday_from_mapping(
            "000001",
            {
                "日期": "2026-08-14 09:31:00",
                "开盘": 11.2,
                "最高": 11.3,
                "最低": 11.1,
                "收盘": 11.25,
                "成交量": 1234,
                "成交额": 5678,
            },
            "test-source",
        )
        self.assertIsInstance(bar, IntradayBar)
        self.assertEqual(bar.code, "000001")
        self.assertEqual(bar.close, 11.25)
        self.assertIn("+08:00", bar.timestamp)

    def test_canonical_models_are_small_and_provider_neutral(self):
        self.assertEqual(
            set(field.name for field in SymbolRef.__dataclass_fields__.values()),
            {"code", "exchange", "provider_symbol", "name"},
        )
        self.assertIn("source", Quote.__dataclass_fields__)
        self.assertIn("source", IntradayBar.__dataclass_fields__)

    def test_baidu_priceinfo_uses_ori_amount_not_display_amount(self):
        bars = parse_baidu_priceinfo(
            "600519",
            [
                {
                    "time": "1786671000",
                    "datetime": "08-14 09:30",
                    "price": "1355.00",
                    "volume": "227",
                    "amount": "3071.38万",
                    "oriAmount": "30713785",
                },
                {
                    "time": "1786671060",
                    "datetime": "08-14 09:31",
                    "price": "1353.27",
                    "volume": "1",
                    "amount": "1.28亿",
                },
                {
                    "time": "1786692600",
                    "datetime": "08-14 15:30",
                    "price": "1341.99",
                    "volume": "--",
                    "amount": "--",
                    "oriAmount": "0",
                },
            ],
            "2026-08-14",
        )
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].amount, 30713785.0)
        self.assertEqual(bars[0].volume, 227.0)
        self.assertEqual(bars[0].timestamp, "2026-08-14T09:30:00+08:00")
        self.assertIsNone(bars[1].amount)

    def test_baidu_explicit_full_date_is_accepted_but_incomplete_date_is_not(self):
        bars = parse_baidu_priceinfo(
            "000001",
            [
                {
                    "datetime": "2026-08-14 09:31:00",
                    "price": "11.25",
                    "volume": "10",
                    "oriAmount": "1125",
                }
            ],
            "2026-08-14",
        )
        self.assertEqual(bars[0].timestamp, "2026-08-14T09:31:00+08:00")
        with self.assertRaises(ProviderError):
            parse_baidu_priceinfo(
                "000001",
                [
                    {
                        "datetime": "08-14 09:31",
                        "price": "11.25",
                        "volume": "10",
                        "oriAmount": "1125",
                    }
                ],
                "2026-08-14",
            )

    def test_baidu_rejects_observed_date_mismatch(self):
        with self.assertRaisesRegex(ProviderError, "does not match requested date"):
            parse_baidu_priceinfo(
                "600519",
                [
                    {
                        "time": "1786671000",
                        "price": "1355",
                        "volume": "1",
                        "oriAmount": "135500",
                    }
                ],
                "2026-08-15",
            )

    def test_baidu_malformed_response_is_rejected(self):
        class FakeResponse:
            def read(self):
                return b'{"ResultCode":"0","Result":{"priceinfo":{}}}'

            def close(self):
                pass

        provider = BaiduDirectAdapter(opener=lambda request, timeout: FakeResponse())
        with self.assertRaisesRegex(ProviderError, "no priceinfo rows"):
            provider.get_intraday("600519", "2026-08-14")

    def test_baidu_is_intraday_only_and_registered(self):
        provider = build_provider("baidu-direct")
        self.assertEqual(provider.name, "baidu-direct")
        with self.assertRaises(ProviderCapabilityError):
            provider.get_quotes(["600519"])


if __name__ == "__main__":
    unittest.main()
