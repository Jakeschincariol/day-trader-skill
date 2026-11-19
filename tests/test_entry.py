import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime

import _load
from india import config, ticks

entry = _load.load("swing-entry", "entry")
CFG = config.load("/nonexistent")
AFTER_CLOSE = datetime(2026, 11, 18, 16, 0)


def bar(d, c, h=None, l=None, o=None, v=1000):
    return {"d": d, "o": c if o is None else o, "h": c if h is None else h, "l": c if l is None else l, "c": c, "v": v}


BASE = [bar("2026-11-%02d" % d, 98.0) for d in (9, 10, 11, 12, 13, 16)]


class Evaluate(unittest.TestCase):
    def test_triggered_on_close_not_wick(self):
        bars = BASE + [bar("2026-11-17", 99, h=105), bar("2026-11-18", 101, h=104)]
        r = entry.evaluate(bars, level=100, since="2026-11-16", now=AFTER_CLOSE, cfg=CFG)
        self.assertEqual((r["state"], r["trigger_date"]), ("triggered", "2026-11-18"))
        self.assertEqual(r["order"]["valid_for"], "2026-11-19")
        self.assertFalse(r["provisional"])

    def test_forming_bar_not_a_trigger(self):
        bars = BASE + [bar("2026-11-17", 99), bar("2026-11-18", 101)]
        r = entry.evaluate(bars, level=100, since="2026-11-16", now=datetime(2026, 11, 18, 14, 0), cfg=CFG)
        self.assertEqual(r["state"], "waiting")
        self.assertAlmostEqual(r["distance_pct"], 1.01, places=2)

    def test_pre_close_is_provisional(self):
        bars = BASE + [bar("2026-11-17", 99), bar("2026-11-18", 101)]
        r = entry.evaluate(bars, level=100, since="2026-11-16", now=datetime(2026, 11, 18, 15, 15), cfg=CFG,
                           pre_close=True)
        self.assertEqual(r["state"], "triggered")
        self.assertTrue(r["provisional"])

    def test_pre_close_outside_window_ignored(self):
        bars = BASE + [bar("2026-11-17", 99), bar("2026-11-18", 101)]
        r = entry.evaluate(bars, level=100, since="2026-11-16", now=datetime(2026, 11, 18, 11, 0), cfg=CFG,
                           pre_close=True)
        self.assertEqual(r["state"], "waiting")

    def test_stale_after_days_and_run_up(self):
        days = ["2026-11-%02d" % d for d in (10, 11, 12, 13, 16, 17, 18)]
        bars = [bar(days[0], 98), bar(days[1], 101)] + [bar(d, 104) for d in days[2:]]
        r = entry.evaluate(bars, level=100, since="2026-11-10", now=AFTER_CLOSE, cfg=CFG)
        self.assertEqual(r["state"], "stale")

    def test_extended_trigger_day_is_not_stale(self):
        bars = BASE + [bar("2026-11-17", 99), bar("2026-11-18", 105)]
        r = entry.evaluate(bars, level=100, since="2026-11-16", now=AFTER_CLOSE, cfg=CFG)
        self.assertEqual(r["state"], "triggered")
        self.assertIn("5.0% above", r["reason"])

    def test_failed_back_under(self):
        bars = BASE + [bar("2026-11-17", 101), bar("2026-11-18", 99)]
        r = entry.evaluate(bars, level=100, since="2026-11-16", now=AFTER_CLOSE, cfg=CFG)
        self.assertEqual(r["state"], "failed")
        self.assertNotIn("order", r)

    def test_late_check_orders_for_next_session_from_latest_close(self):
        # triggered on the 16th, checked after the 18th close: the order is for the 19th
        bars = BASE[:-1] + [bar("2026-11-16", 101, h=101.5), bar("2026-11-17", 101.5, h=102), bar("2026-11-18", 102, h=102.4)]
        r = entry.evaluate(bars, level=100, since="2026-11-13", now=AFTER_CLOSE, cfg=CFG)
        self.assertEqual((r["state"], r["trigger_date"]), ("triggered", "2026-11-16"))
        self.assertEqual(r["order"]["valid_for"], "2026-11-19")
        self.assertEqual(r["order"]["price"], ticks.round_up(102 * 1.005))
        self.assertEqual(r["late_sessions"], 2)
        self.assertIn("2 sessions ago", r["reason"])

    def test_pre_close_order_is_for_today(self):
        bars = BASE + [bar("2026-11-17", 99), bar("2026-11-18", 101)]
        r = entry.evaluate(bars, level=100, since="2026-11-16", now=datetime(2026, 11, 18, 15, 15), cfg=CFG,
                           pre_close=True)
        self.assertEqual(r["order"]["valid_for"], "2026-11-18")

    def test_volume_check(self):
        bars = [bar("2026-10-%02d" % d, 98, v=1000) for d in range(1, 21)] + [bar("2026-11-18", 101, v=1200)]
        r = entry.evaluate(bars, level=100, since="2026-10-20", now=AFTER_CLOSE, cfg=CFG, min_volume_x=1.5)
        self.assertEqual(r["state"], "waiting")
        self.assertIn("volume", r["reason"])

    def test_limit_price_on_tick(self):
        bars = BASE + [bar("2026-11-17", 99), bar("2026-11-18", 3401.7, h=3420.3)]
        r = entry.evaluate(bars, level=3400, since="2026-11-16", now=AFTER_CLOSE, cfg=CFG)
        self.assertEqual(r["order"], {"style": "limit", "price": 3418.80, "valid_for": "2026-11-19"})
        self.assertTrue(ticks.is_valid(r["order"]["price"]))
        r2 = entry.evaluate(bars, level=3400, since="2026-11-16", now=AFTER_CLOSE, cfg=dict(CFG, entry_style="sl-buy"))
        self.assertEqual(r2["order"]["trigger"], 3420.40)
        self.assertEqual(r2["order"]["price"], 3437.60)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_cli(self, args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = entry.main(args + ["--dir", self.tmp, "--offline", _load.INDIA_FIX, "--json",
                                      "--now", "2026-11-18 16:00"])
        return code, json.loads(buf.getvalue())

    def test_check_offline_writes_entry_json(self):
        code, r = self.run_cli(["check", "ICICIBANK", "--setup", "breakout_20d", "--write"])
        self.assertEqual((r["state"], r["trigger_date"]), ("triggered", "2026-11-18"))
        with open(os.path.join(self.tmp, "entry.json")) as fh:
            saved = json.load(fh)
        self.assertEqual(saved["symbol"], "ICICIBANK")
        self.assertEqual(saved["setup"], "breakout_20d")
        self.assertIn("trigger_high", saved)

    def test_check_unknown_setup_on_stock(self):
        code, r = self.run_cli(["check", "TCS", "--setup", "breakout_52w"])
        self.assertEqual(code, 2)
        self.assertIn("did not fire", r["error"])


if __name__ == "__main__":
    unittest.main()
