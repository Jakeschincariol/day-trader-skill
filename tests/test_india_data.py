import os
import tempfile
import unittest
from datetime import date, datetime
from unittest import mock

import _load
from india import config, data, symbols


class Data(unittest.TestCase):
    def setUp(self):
        self.f = data.Fetcher(cache_dir=None, offline=_load.INDIA_FIX)

    def test_yahoo_daily_offline(self):
        bars = data.yahoo_daily(self.f, symbols.parse("TCS"))
        self.assertGreater(len(bars), 1200)
        self.assertEqual(set(bars[-1]), {"d", "o", "h", "l", "c", "v"})
        self.assertTrue(all(a["d"] < b["d"] for a, b in zip(bars, bars[1:])))
        self.assertTrue(all(b["l"] <= b["c"] <= b["h"] for b in bars[-50:]))

    def test_drop_unfinished_bar(self):
        bars = [{"d": "2026-11-17", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1},
                {"d": "2026-11-18", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]
        self.assertEqual(len(data.drop_unfinished(bars, datetime(2026, 11, 18, 14, 0))), 1)
        self.assertEqual(len(data.drop_unfinished(bars, datetime(2026, 11, 18, 16, 0))), 2)

    def test_cache_filename_safe(self):
        key = data.cache_key_for("chart", symbols.parse("M&M"), "5y")
        self.assertEqual(key, "chart-M_and_M.NS-5y.json")

    def test_ampersand_symbol_offline(self):
        bars = data.yahoo_daily(self.f, symbols.parse("M&M"))
        self.assertGreater(len(bars), 1200)

    def test_spark_closes(self):
        syms = [symbols.parse(s) for s in _load.FIXTURE_SYMBOLS]
        out = data.yahoo_spark(self.f, syms, "1y")
        self.assertIn("TCS", out)
        self.assertGreater(len(out["TCS"]), 200)
        b = out["TCS"][-1]
        self.assertEqual(b["o"], b["c"])

    def test_equity_list_and_bands(self):
        eq = data.nse_equity_list(self.f)
        self.assertIn("TCS", {r["symbol"] for r in eq})
        self.assertEqual({r["series"] for r in eq if r["symbol"] == "TCS"}, {"EQ"})
        self.assertIn(data.nse_price_bands(self.f).get("TCS"), ("2", "5", "10", "20", "-"))

    def test_delivery_pct(self):
        got = data.nse_delivery(self.f, date(2026, 11, 18))
        self.assertTrue(0 < got["TCS"] <= 100)

    def test_offline_never_hits_network(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            data.yahoo_daily(self.f, symbols.parse("M&M"))

    def test_offline_missing_file_is_clear(self):
        with self.assertRaises(data.DataError) as cm:
            data.yahoo_daily(self.f, symbols.parse("NOSUCH"))
        self.assertIn("offline", str(cm.exception))


class Config(unittest.TestCase):
    def test_defaults_and_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(config.load(tmp)["risk_per_trade_pct"], 1.0)
            with open(os.path.join(tmp, "config.json"), "w") as fh:
                fh.write('{"capital": 500000, "charges": {"brokerage_per_order": 20}}')
            cfg = config.load(tmp)
            self.assertEqual(cfg["capital"], 500000)
            self.assertEqual(cfg["max_hold_days"], 15)
            self.assertEqual(cfg["charges"]["brokerage_per_order"], 20)
            p = config.trader_path(tmp, "state/risk.json")
            self.assertTrue(os.path.isdir(os.path.dirname(p)))

    def test_fingerprint_stable(self):
        a = config.fingerprint({"qty": 5, "symbol": "TCS"})
        self.assertEqual(a, config.fingerprint({"symbol": "TCS", "qty": 5}))
        self.assertNotEqual(a, config.fingerprint({"symbol": "TCS", "qty": 6}))


if __name__ == "__main__":
    unittest.main()
