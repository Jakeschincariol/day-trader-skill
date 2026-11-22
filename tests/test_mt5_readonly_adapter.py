import unittest
from datetime import timezone
from types import SimpleNamespace

from alpha_mt5 import (
    MT5ConnectionError,
    MT5DataUnavailable,
    ReadOnlyMT5Adapter,
)


class FakeMT5:
    def __init__(self, initialize_result=True, terminal_connected=True):
        self.initialize_result = initialize_result
        self.terminal_connected = terminal_connected
        self.symbol_tick = {
            "time": 1735689600,
            "time_msc": 1735689600123,
            "bid": 1.1,
            "ask": 1.2,
            "last": 1.15,
            "volume": 7.0,
        }
        self.rate_rows = [
            {
                "time": 1735689600,
                "open": 1.0,
                "high": 1.3,
                "low": 0.9,
                "close": 1.2,
                "tick_volume": 22,
                "spread": 3,
                "real_volume": 0,
            }
        ]
        self.shutdown_called = False
        self.order_send_called = False

    def initialize(self):
        return self.initialize_result

    def last_error(self):
        return (1, "test failure")

    def shutdown(self):
        self.shutdown_called = True

    def terminal_info(self):
        return SimpleNamespace(
            connected=self.terminal_connected, name="Demo Terminal", build=5000
        )

    def account_info(self):
        return SimpleNamespace(currency="USD", balance=1000.0, equity=990.0)

    def symbol_info(self, symbol):
        if symbol == "MISSING":
            return None
        return SimpleNamespace(
            name=symbol,
            digits=5,
            point=0.00001,
            trade_tick_size=0.00001,
            trade_tick_value_profit=1.0,
            trade_tick_value_loss=1.0,
            trade_contract_size=100000.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_stops_level=10,
            trade_freeze_level=0,
            trade_mode=4,
            currency_base="EUR",
            currency_profit="USD",
            currency_margin="USD",
        )

    def symbol_info_tick(self, symbol):
        if symbol == "MISSING":
            return None
        return self.symbol_tick

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        return self.rate_rows[:count]

    def order_send(self, *_args, **_kwargs):
        self.order_send_called = True
        raise AssertionError("read-only adapter must never send orders")


class ReadOnlyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeMT5()
        self.adapter = ReadOnlyMT5Adapter(self.api)
        self.adapter.connect()

    def test_health_is_minimal_and_connected(self):
        health = self.adapter.health()
        self.assertTrue(health.connected)
        self.assertEqual(health.account_currency, "USD")
        self.assertEqual(health.account_equity, 990.0)

    def test_symbol_metadata_is_returned_without_inference(self):
        spec = self.adapter.symbol_spec("EURUSD")
        self.assertEqual(spec.volume_step, 0.01)
        self.assertEqual(spec.tick_size, 0.00001)
        self.assertEqual(spec.currency_profit, "USD")

    def test_quote_timestamp_is_utc(self):
        quote = self.adapter.quote("EURUSD")
        self.assertEqual(quote.time_utc.tzinfo, timezone.utc)
        self.assertEqual(quote.bid, 1.1)

    def test_non_finite_tick_values_are_not_returned_as_numbers(self):
        self.api.symbol_tick["bid"] = float("nan")
        quote = self.adapter.quote("EURUSD")
        self.assertIsNone(quote.bid)

    def test_bars_are_normalized(self):
        bars = self.adapter.bars("EURUSD", 1, 10)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].close, 1.2)
        self.assertEqual(bars[0].tick_volume, 22)

    def test_missing_symbol_or_tick_fails_closed(self):
        with self.assertRaises(MT5DataUnavailable):
            self.adapter.symbol_spec("MISSING")
        with self.assertRaises(MT5DataUnavailable):
            self.adapter.quote("MISSING")

    def test_reads_require_terminal_connection(self):
        self.api.terminal_connected = False
        with self.assertRaises(MT5ConnectionError):
            self.adapter.quote("EURUSD")

    def test_initialize_failure_is_reported(self):
        adapter = ReadOnlyMT5Adapter(FakeMT5(initialize_result=False))
        with self.assertRaises(MT5ConnectionError):
            adapter.connect()

    def test_count_must_be_positive_integer(self):
        with self.assertRaises(ValueError):
            self.adapter.bars("EURUSD", 1, 0)
        with self.assertRaises(ValueError):
            self.adapter.bars("EURUSD", 1, True)

    def test_close_only_shuts_down_session(self):
        self.adapter.close()
        self.assertTrue(self.api.shutdown_called)
        self.assertFalse(self.api.order_send_called)


if __name__ == "__main__":
    unittest.main()
