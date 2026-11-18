import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date

import _load
from india import levels, ticks

exit_ = _load.load("swing-exit", "exit")
entry = _load.load("swing-entry", "entry")


def bars_with(lows, h_pad=20.0, c=3400.0):
    return [{"d": "2026-10-%02d" % (k + 1), "o": c, "h": c + h_pad, "l": lo, "c": c, "v": 1000}
            for k, lo in enumerate(lows)]


class Levels(unittest.TestCase):
    def test_swing_low_rounded_down_to_tick(self):
        bars = bars_with([3350.0] * 10 + [3296.17] + [3380.0] * 9)
        stop, how = levels.compute_stop(bars, 19, 3412.40, "swing-low")
        self.assertEqual(stop, 3296.10)
        self.assertIn("lowest low of the last 10", how)
        stop5, _ = levels.compute_stop(bars, 19, 3412.40, "swing-low:5")
        self.assertEqual(stop5, 3380.0)

    def test_setup_low_and_pct_and_price(self):
        bars = bars_with([3300.0] * 19 + [3311.33])
        self.assertEqual(levels.compute_stop(bars, 19, 3412.40, "setup-low")[0], 3311.30)
        self.assertEqual(levels.compute_stop(bars, 19, 3412.40, "pct:3")[0], 3310.0)
        self.assertEqual(levels.compute_stop(bars, 19, 3412.40, "price:3290.07")[0], 3290.0)

    def test_atr_stop(self):
        bars = [{"d": "x", "o": 3400.0, "h": 3420.0, "l": 3380.0, "c": 3400.0, "v": 1} for _ in range(20)]
        stop, how = levels.compute_stop(bars, 19, 3412.40, "atr:2")
        self.assertEqual(stop, 3332.40)            # 3412.40 - 2 x 40
        self.assertIn("ATR", how)

    def test_refuses_stop_above_entry(self):
        bars = bars_with([3300.0] * 20)
        with self.assertRaises(levels.PlanError):
            levels.compute_stop(bars, 19, 3412.40, "price:3420")

    def test_refuses_noise_tight_stop(self):
        bars = [{"d": "x", "o": 3400.0, "h": 3450.0, "l": 3350.0, "c": 3400.0, "v": 1} for _ in range(20)]
        with self.assertRaises(levels.PlanError) as cm:
            levels.compute_stop(bars, 19, 3412.40, "price:3400")   # 12.40 risk vs ATR 100
        self.assertIn("0.5 x ATR", str(cm.exception))

    def test_bad_method(self):
        with self.assertRaises(levels.PlanError):
            levels.compute_stop(bars_with([3300.0] * 20), 19, 3412.40, "moon")

    def test_target_2r(self):
        self.assertEqual(levels.compute_target(3412.40, 3296.10, "2R"), 3645.00)
        self.assertEqual(levels.compute_target(3412.40, 3296.10, "1R"), 3528.70)
        self.assertEqual(levels.compute_target(3412.40, 3296.10, "price:3700.03"), 3700.0)
        with self.assertRaises(levels.PlanError):
            levels.compute_target(3412.40, 3296.10, "price:3400")

    def test_gtt_limit(self):
        self.assertEqual(levels.gtt_stop_limit(3296.10, 1.0), 3263.10)
        self.assertTrue(ticks.is_valid(levels.gtt_stop_limit(249.37, 1.0)))

    def test_time_stop_skips_holiday(self):
        self.assertEqual(levels.time_stop(date(2026, 11, 20), 2), date(2026, 11, 25))


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def cli(self, mod, args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = mod.main(args + ["--dir", self.tmp, "--offline", _load.INDIA_FIX, "--json",
                                    "--now", "2026-11-18 16:00"])
        return code, json.loads(buf.getvalue())

    def test_plan_offline_writes_plan_json(self):
        self.cli(entry, ["check", "ICICIBANK", "--setup", "breakout_20d", "--write"])
        code, p = self.cli(exit_, ["plan", "--stop", "swing-low", "--target", "2R", "--write"])
        self.assertEqual(code, 0, p)
        with open(os.path.join(self.tmp, "plan.json")) as fh:
            saved = json.load(fh)
        for k in ("symbol", "exchange", "setup", "entry", "entry_date", "stop", "stop_how", "gtt_stop_limit",
                  "target", "risk_per_share", "reward_risk", "max_hold_days", "time_stop_date", "atr14", "as_of"):
            self.assertIn(k, saved)
        self.assertEqual(saved["entry_date"], "2026-11-19")
        self.assertLess(saved["stop"], saved["entry"])
        self.assertEqual(saved["reward_risk"], 2.0)
        self.assertEqual(saved["max_hold_days"], 15)
        self.assertEqual((saved["stop_method"], saved["target_spec"]), ("swing-low", "2R"))

    def test_plan_refuses_without_entry(self):
        code, p = self.cli(exit_, ["plan"])
        self.assertEqual(code, 2)
        self.assertIn("swing-entry", p["error"])


if __name__ == "__main__":
    unittest.main()
