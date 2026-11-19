import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import _load
from india import data, symbols

tm = _load.load("swing-timemachine", "timemachine")

PLAN = {"symbol": "TCS", "exchange": "NSE", "setup": "breakout_20d", "entry": 2400.0, "entry_date": "2026-11-19",
        "stop": 2320.0, "stop_method": "swing-low", "target": 2560.0, "target_spec": "2R", "gtt_stop_limit": 2296.8,
        "risk_per_share": 80.0, "reward_risk": 2.0, "max_hold_days": 15, "time_stop_date": "2026-12-10"}


class Rules(unittest.TestCase):
    def test_gap_through_fills_at_open(self):
        self.assertEqual(tm.walk_day(100, 95, 110, o=90, h=92, l=89, c=91), ("stop", 90.0, True))

    def test_gap_over_target_fills_at_open(self):
        self.assertEqual(tm.walk_day(100, 95, 110, o=112, h=115, l=111, c=113), ("target", 112.0, False))

    def test_same_bar_both_counts_stop(self):
        self.assertEqual(tm.walk_day(100, 95, 110, o=100, h=111, l=94, c=105), ("stop", 95.0, False))

    def test_quiet_day_no_exit(self):
        self.assertIsNone(tm.walk_day(100, 95, 110, o=100, h=103, l=97, c=101))


class Simulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f = data.Fetcher(None, offline=_load.INDIA_FIX)
        bars = data.yahoo_daily(f, symbols.parse("TCS"), "5y")
        cls.tcs = [b for b in bars if b["d"] <= "2026-11-18"]

    def test_seeded_repeatable(self):
        a = tm.simulate(self.tcs, 2400.0, 2320.0, 2560.0, 15, n=2000)
        b = tm.simulate(self.tcs, 2400.0, 2320.0, 2560.0, 15, n=2000)
        self.assertEqual(a, b)
        self.assertAlmostEqual(a["target_pct"] + a["stop_pct"] + a["time_pct"], 100.0, places=6)
        self.assertLessEqual(a["gap_through_pct"], a["stop_pct"])
        self.assertEqual(len(a["fan"]), 15)
        c = tm.simulate(self.tcs, 2400.0, 2320.0, 2560.0, 15, n=2000, seed=7)
        self.assertNotEqual(a["target_pct"], c["target_pct"])

    def test_too_little_history_refuses(self):
        with self.assertRaises(tm.TooLittleHistory) as cm:
            tm.simulate(self.tcs[-200:], 2400.0, 2320.0, 2560.0, 15, n=100)
        self.assertIn("needs at least 378", str(cm.exception))

    def test_history_counts_add_up(self):
        h = tm.history(self.tcs, "breakout_20d", "swing-low", "2R", 15)
        self.assertGreater(h["fired"], 5)
        self.assertEqual(h["fired"], h["target"] + h["stop"] + h["time"])
        self.assertEqual(len(h["trades"]), h["fired"])
        t = h["trades"][0]
        self.assertEqual(set(t), {"date", "entry", "stop", "target", "exit", "r", "days", "outcome"})

    def test_verdict(self):
        self.assertEqual(tm.verdict(0.3, 0.25), "edge in its own history")
        self.assertEqual(tm.verdict(0.1, -0.1), "close to a coin flip")
        self.assertEqual(tm.verdict(-0.4, 0.1), "history is against it")


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "plan.json"), "w") as fh:
            json.dump(PLAN, fh)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def cli(self, args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = tm.main(args + ["--dir", self.tmp, "--offline", _load.INDIA_FIX, "--now", "2026-11-18 16:00"])
        return code, buf.getvalue()

    def test_run_offline_pinned_numbers(self):
        code, out = self.cli(["run", "--write", "--json"])
        self.assertEqual(code, 0)
        r = json.loads(out)
        got = (round(r["sim"]["target_pct"], 1), round(r["sim"]["stop_pct"], 1), round(r["sim"]["time_pct"], 1))
        self.assertEqual(got, PINNED)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "timemachine.json")))
        code, chart = self.cli(["chart"])
        self.assertEqual(code, 0)
        self.assertIn("day 15", chart)


PINNED = (21.9, 55.5, 22.7)   # TCS fixture plan, 10,000 replays, seed 19

if __name__ == "__main__":
    unittest.main()
