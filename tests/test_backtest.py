import gzip
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

bt = load("trader-timemachine", "backtest")
tm = bt.tm   # the same module backtest.py uses, so its TMError is the one it catches

TSLA = os.path.join(FIX, "trader-timemachine", "TSLA-60d5m.json.gz")
with gzip.open(TSLA, "rt", encoding="utf-8") as _fh:
    TEXT = _fh.read()
NOW = "2026-10-19 16:30"
RULE = {"setup": "orb", "or_minutes": 15, "stop_rule": "or_mid", "target_r": 1.0}


def copy_as(sym, scale=1.0):
    """The TSLA fixture under another ticker, prices times scale (volume unchanged)."""
    d = json.loads(TEXT)
    r = d["chart"]["result"][0]
    r["meta"]["symbol"] = sym
    q = r["indicators"]["quote"][0]
    for f in ("open", "high", "low", "close"):
        q[f] = [None if x is None else x * scale for x in q[f]]
    return json.dumps(d)


def days_of(text, sym="TSLA"):
    _, bars, _ = tm.parse_bars(tm.chart_result(text, sym), tm.parse_now(NOW))
    return tm.split_sessions(bars)


DAYS = days_of(TEXT)


def loader(extra=None):
    data = {"TSLA": DAYS}
    data.update(extra or {})

    def load_(sym):
        if sym not in data:
            raise tm.TMError("no data for %s" % sym)
        return data[sym]
    return load_


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = bt.main(argv)
    return code, out.getvalue(), err.getvalue()


class Rule(unittest.TestCase):
    def test_same_trades_as_the_time_machine_history(self):
        # entries up to the last bar and out at 16:00: the same trades the Time Machine's history finds
        trades = bt.symbol_trades("TSLA", DAYS, RULE, 16 * 60, 16 * 60)
        sessions, _ = tm.full_sessions(DAYS, "2026-10-19")
        h = tm.history_replay(sessions, RULE, tm.SESSION_BARS - 1)
        self.assertEqual([(t["date"], t["entry"], t["outcome"]) for t in trades],
                         [(t["date"], t["entry"], t["outcome"]) for t in h["trades"]])
        # R only differs where a stop gapped: the backtest fills those at the bar's open
        for a, b in zip(trades, h["trades"]):
            if not a["gapped"]:
                self.assertAlmostEqual(a["R_gross"], b["R"], places=1)
            else:
                self.assertLess(a["R_gross"], -1.0)

    def test_slippage_lowers_r_and_scales_with_price(self):
        gross = bt.symbol_trades("TSLA", DAYS, RULE, 955, 930)
        net = bt.symbol_trades("TSLA", DAYS, RULE, 955, 930, slip_frac=0.0005)
        cheap = bt.symbol_trades("AAA", days_of(copy_as("AAA", 0.25), "AAA"), RULE, 955, 930, slip_frac=0.0005)
        self.assertEqual(len(gross), len(net))
        self.assertTrue(all(n["R"] < g["R"] for n, g in zip(net, gross)))
        self.assertEqual(len(net), len(cheap))
        for a, b in zip(net, cheap):      # same trades; only cent rounding at a quarter of the price differs
            self.assertEqual(a["outcome"], b["outcome"])
            self.assertAlmostEqual(a["R"], b["R"], delta=0.06)

    def test_features(self):
        trades = bt.symbol_trades("TSLA", DAYS, RULE, 955, 930)
        first = trades[0]["features"]
        self.assertIsNone(first["rvol"])                      # no history yet
        self.assertIsNone(first["gap"] if trades[0]["date"] == "2026-07-27" else None)
        later = [t for t in trades if t["features"]["rvol"] is not None]
        self.assertTrue(later and all(t["features"]["rvol"] > 0 for t in later))
        self.assertTrue(all(t["features"]["or_pct"] > 0 for t in trades))
        self.assertTrue(all(t["features"]["time"] <= 930 for t in trades))
        self.assertTrue(all(t["features"]["market"] is None for t in trades))   # no market data given


class Filters(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(bt.parse_filter("rvol >= 2")["value"], 2.0)
        self.assertEqual(bt.parse_filter("time<=10:30")["value"], 630)
        self.assertEqual(bt.parse_filter("VWAP")["op"], "is")
        self.assertEqual(bt.parse_filter("gap>=-1.5")["value"], -1.5)
        for bad in ("rvol", "volume>3", "rvol>=x", ""):
            with self.assertRaises(bt.BTError):
                bt.parse_filter(bad)

    def test_unknown_values_are_left_out_and_counted(self):
        t1 = {"features": {"rvol": None}}
        t2 = {"features": {"rvol": 3.0}}
        t3 = {"features": {"rvol": 1.0}}
        kept, unknown = bt.apply_filters([t1, t2, t3], [bt.parse_filter("rvol>=2")])
        self.assertEqual((kept, unknown), ([t2], 1))

    def test_judge(self):
        def s(n, r):
            return {"n": n, "avg_R": r}
        base = {"in": s(100, 0.0), "out": s(100, 0.0)}
        self.assertTrue(bt.judge(base, {"in": s(40, 0.2), "out": s(40, 0.1)}).startswith(
            "held up: better than the baseline and positive after costs in both halves"))
        sure = {"in": s(40, 0.2), "out": dict(s(40, 0.1), avg_R_range=[0.02, 0.18])}
        self.assertIn("95 % range is above zero", bt.judge(base, sure))
        losing = {"in": s(100, -0.17), "out": s(100, -0.16)}
        self.assertEqual(bt.judge(losing, {"in": s(40, -0.14), "out": s(40, -0.14)}),
                         "less bad than the baseline in both halves, but still loses after costs")
        self.assertEqual(bt.sign_words(losing), "loses after costs in both halves")
        self.assertEqual(bt.sign_words({"in": s(40, 0.1), "out": s(40, -0.1)}),
                         "mixed: one half above zero, one below")
        self.assertIn("noise", bt.judge(base, {"in": s(40, 0.2), "out": s(40, -0.1)}))
        self.assertIn("too few", bt.judge(base, {"in": s(40, 0.2), "out": s(12, 0.5)}))
        self.assertEqual(bt.judge(base, {"in": s(40, -0.2), "out": s(40, -0.1)}), "did not help")

    def test_wilson(self):
        lo, hi = bt.wilson(10, 20)
        self.assertTrue(0.29 < lo < 0.30 and 0.70 < hi < 0.71)
        self.assertIsNone(bt.wilson(0, 0))


class Backtest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        aaa = days_of(copy_as("AAA", 0.25), "AAA")
        spy = days_of(copy_as("SPY"), "SPY")
        cls.doc = bt.backtest(["TSLA", "AAA", "NOPE"], loader({"AAA": aaa, "SPY": spy}), RULE, 955, 930,
                              [bt.parse_filter("time<=10:30"), bt.parse_filter("market")],
                              slippage={"bps": 5.0, "source": "test", "mode": "bps"}, market="SPY",
                              bys=("time", "symbol"))

    def test_the_split_is_by_date_and_adds_up(self):
        d = self.doc
        self.assertEqual(d["sessions"], 59)
        self.assertLess(d["in_sample"][1], d["out_of_sample"][0])
        base = d["variants"][0]
        self.assertEqual(base["in"]["n"] + base["out"]["n"], base["all"]["n"])
        self.assertEqual(base["all"]["symbols"], 2)
        self.assertTrue(all(t["date"] < d["split_date"] or t["date"] >= d["split_date"] for t in d["trades"]))

    def test_variants(self):
        names = [v["name"] for v in self.doc["variants"]]
        self.assertEqual(names, ["baseline", "time<=10:30", "market", "all filters"])
        t = self.doc["variants"][1]
        self.assertLessEqual(t["all"]["n"], self.doc["variants"][0]["all"]["n"])
        self.assertIn("verdict", t)
        self.assertIn("after costs", self.doc["variants"][0]["verdict"])

    def test_failed_tickers_are_reported_not_fatal(self):
        self.assertIn("NOPE", self.doc["failed"])
        text = "\n".join(bt.report(self.doc))
        self.assertIn("Skipped: NOPE", text)
        self.assertIn("IN SAMPLE", text)
        self.assertIn("Slippage 5.0 bps", text)
        self.assertIn("By symbol", text)
        self.assertIn("not a prediction", text)

    def test_nothing_usable_is_one_error(self):
        with self.assertRaises(bt.BTError):
            bt.backtest(["NOPE"], loader(), RULE, 955, 930, [])


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        shutil.copy(TSLA, self.d)
        with open(os.path.join(self.d, "AAA-60d5m.json"), "w") as fh:
            fh.write(copy_as("AAA", 0.5))
        self.wl = os.path.join(self.d, "watchlist.json")
        with open(self.wl, "w") as fh:
            json.dump({"hits": [{"symbol": "TSLA"}, {"symbol": "AAA"}, {"symbol": "TSLA"}]}, fh)

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_run_from_a_watchlist(self):
        out = os.path.join(self.d, "bt.json")
        code, text, err = run(["run", "--watchlist", self.wl, "--offline", self.d, "--now", NOW,
                               "--filter", "rvol>=1", "--by", "rvol", "--market", "none", "--write", out])
        self.assertEqual(code, 0, err)
        self.assertIn("2 tickers, 59 sessions", text)
        self.assertIn("rvol>=1", text)
        with open(out) as fh:
            doc = json.load(fh)
        self.assertEqual(doc["symbols"], ["TSLA", "AAA"])
        self.assertTrue(all(":" in t["features"]["time"] for t in doc["trades"]))

    def test_json_and_errors(self):
        code, text, _ = run(["run", "--symbols", "tsla", "--offline", self.d, "--now", NOW, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["variants"][0]["name"], "baseline")
        for argv in (["run"], ["run", "--symbols", "TSLA", "--filter", "nonsense", "--offline", self.d],
                     ["run", "--symbols", "TSLA", "--offline", self.d, "--slippage", "0.03"],
                     ["run", "--symbols", "TSLA", "--offline", self.d, "--stop-rule", "pct"],
                     ["run", "--symbols", "TSLA", "--offline", self.d, "--last-entry", "16:00"]):
            code, _, err = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertTrue(err.startswith("backtest.py: "), err)
            self.assertEqual(len(err.strip().splitlines()), 1, err)


if __name__ == "__main__":
    unittest.main()
