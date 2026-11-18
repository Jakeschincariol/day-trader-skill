import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import _load
from india import indicators as ind

scan = _load.load("swing-scanner", "scan")
SYMS = ",".join(_load.FIXTURE_SYMBOLS)


def run(args, tmp):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = scan.main(args + ["--dir", tmp, "--offline", _load.INDIA_FIX, "--json"])
    return code, json.loads(buf.getvalue())


class Scanner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_universe_series_filter(self):
        code, out = run(["universe"], self.tmp)
        self.assertEqual(code, 0)
        self.assertIn("TCS", out["symbols"])
        with open(os.path.join(_load.INDIA_FIX, "EQUITY_L.csv")) as fh:
            be = [l.split(",")[0] for l in fh if ",BE," in l]
        self.assertTrue(be and not set(be) & set(out["symbols"]))
        with open(os.path.join(self.tmp, "universe.txt")) as fh:
            self.assertIn("TCS\n", fh.read())

    def test_scan_daily_offline(self):
        code, out = run(["daily", "--symbols", SYMS, "--now", "2026-11-18 16:00"], self.tmp)
        self.assertEqual(code, 0)
        self.assertEqual(out["as_of"], "2026-11-18")
        for h in out["hits"]:
            self.assertIn(h["setup"], ind.SETUPS)
            self.assertNotIn(h["band"], ("2", "5"))
            self.assertGreaterEqual(h["close"], 50)
            self.assertGreaterEqual(h["traded_value"], 5e7)
        with open(os.path.join(self.tmp, "watchlist.json")) as fh:
            self.assertEqual(json.load(fh)["as_of"], "2026-11-18")
        self.assertEqual(sorted((h["symbol"], h["setup"]) for h in out["hits"]), PINNED)

    def test_scan_mid_session_uses_yesterday(self):
        code, out = run(["daily", "--symbols", SYMS, "--now", "2026-11-18 11:00"], self.tmp)
        self.assertEqual(out["as_of"], "2026-11-17")

    def test_min_price_filter_drops_penny_stocks(self):
        code, out = run(["daily", "--symbols", SYMS, "--now", "2026-11-18 16:00", "--min-price", "0",
                         "--min-traded-value", "0"], self.tmp)
        code2, out2 = run(["daily", "--symbols", SYMS, "--now", "2026-11-18 16:00", "--min-price", "250",
                           "--min-traded-value", "0"], self.tmp)
        self.assertTrue(all(h["close"] >= 250 for h in out2["hits"]))
        self.assertGreaterEqual(len(out["hits"]), len(out2["hits"]))

    def test_unknown_symbol_is_a_note_not_a_crash(self):
        code, out = run(["daily", "--symbols", "NOSUCH", "--now", "2026-11-18 16:00"], self.tmp)
        self.assertEqual(out["hits"], [])
        self.assertTrue(any("NOSUCH" in n for n in out["notes"]))


# the fixture day's hits (real NSE data for 2026-11-18), quoted in the README
PINNED = [("HDFCBANK", "bull_flag"), ("ICICIBANK", "breakout_20d"), ("ICICIBANK", "bull_flag"),
          ("INFY", "pullback_ma50"), ("ITC", "breakout_20d"), ("LT", "bull_flag"), ("M&M", "bull_flag"),
          ("RELIANCE", "bull_flag"), ("SBIN", "breakout_20d")]

if __name__ == "__main__":
    unittest.main()
