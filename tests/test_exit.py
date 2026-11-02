"""trader-exit tests. Bars for the ATR stop reuse tests/fixtures/trader-entry/
(TSLA's real Oct 19 2026 five-minute bars, see test_entry.py)."""

import calendar
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from decimal import Decimal

from _load import load, FIX, ROOT

exitp = load("trader-exit", "exit")
entry = load("trader-entry", "entry")

TSLA = os.path.join(FIX, "trader-entry", "TSLA-2026-10-19-5m.json")

# trader/plan.json for the reel, exactly as the contract writes it
REEL_PLAN = {"created_by": "trader-exit", "symbol": "TSLA", "side": "buy", "date": "2026-10-19", "setup": "orb",
             "entry": 364.18, "entry_time": "10:15 AM", "entry_bar": 8, "interval": "5m",
             "opening_range": {"high": 362.18, "low": 354.47, "minutes": 15},
             "stop": 358.32, "stop_rule": "or_mid", "stop_label": "opening-range midpoint",
             "target": 370.04, "target_r": 1.0, "target_label": "1R (one times the risk)",
             "risk_per_share": 5.86, "reward_risk": 1.0, "flat_by": "15:55"}
REEL_ENTRY = {"created_by": "trader-entry", "symbol": "TSLA", "setup": "orb", "side": "buy", "date": "2026-10-19",
              "status": "triggered", "time": "10:15 AM", "bar_start": "10:10", "bar_index": 8, "price": 364.18,
              "level": 362.18, "interval": "5m", "opening_range": {"high": 362.18, "low": 354.47, "minutes": 15},
              "source": "yahoo", "checked_at": "2026-10-19T14:15:00Z"}


def run(mod, argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = mod.main(argv)
    return code, out.getvalue(), err.getvalue()


def c(entry_px, stop, target="2R", oh=362.18, ol=354.47, atr=None, n=None):
    sr, sp = exitp.parse_stop(stop)
    tr, tp = exitp.parse_target(target)
    return exitp.compute(entry_px, sr, sp, tr, tp, oh, ol, atr, n)


class Math(unittest.TestCase):
    def test_the_reel_or_mid_1r(self):
        p = c(364.18, "or-mid", "1R")
        self.assertEqual(p["stop"], Decimal("358.32"))           # floor(358.325)
        self.assertEqual(p["risk"], Decimal("5.86"))
        self.assertEqual(p["target"], Decimal("370.04"))
        self.assertEqual(p["reward_risk"], Decimal("1.00"))
        self.assertEqual(p["target_label"], "1R (one times the risk)")
        self.assertIn("rounded down", p["stop_detail"])

    def test_the_default_2r(self):
        p = c(364.18, "or-mid")
        self.assertEqual(p["target"], Decimal("375.90"))
        self.assertEqual(p["target_label"], "2R (two times the risk)")

    def test_raw_yahoo_floats_give_the_same_cents(self):
        p = c(364.1759948730469, "or-mid", "1R", 362.17999267578125, 354.4700012207031)
        self.assertEqual((p["entry"], p["stop"], p["target"]), (Decimal("364.18"), Decimal("358.32"), Decimal("370.04")))

    def test_other_stops(self):
        p = c(364.18, "or-low")
        self.assertEqual((p["stop"], p["risk"], p["target"]), (Decimal("354.47"), Decimal("9.71"), Decimal("383.60")))
        p = c(364.18, "price:358.329")
        self.assertEqual(p["stop"], Decimal("358.32"))              # rounds away from the entry
        p = c(364.18, "pct:1")
        self.assertEqual((p["stop"], p["risk"], p["target"]), (Decimal("360.53"), Decimal("3.65"), Decimal("371.48")))
        p = c(364.18, "atr:1.5", atr=3.2181, n=9)
        self.assertEqual(p["stop"], Decimal("359.35"))              # 364.18 - 4.82715 = 359.35285
        self.assertEqual(p["stop_label"], "1.5 x ATR(9) under the entry")

    def test_target_rounds_half_up_and_price_targets(self):
        p = c(100, "price:99.01", "1.5R", None, None)
        self.assertEqual(p["target"], Decimal("101.49"))            # 100 + 1.485
        self.assertEqual(p["target_label"], "1.5R (1.5 times the risk)")
        p = c(364.18, "or-mid", "price:372")
        self.assertEqual(p["reward_risk"], Decimal("1.33"))
        self.assertEqual(p["target_label"], "your price (1.33R)")
        self.assertEqual(p["target_r"], Decimal("1.33"))

    def test_refusals_say_why(self):
        cases = [("price:364.18", "2R", "at or above the entry"),
                 ("price:365", "2R", "at or above the entry"),
                 ("or-mid", "price:364", "at or below the entry"),
                 ("price:364.01", "2R", "too tight to survive the spread"),
                 ("pct:0.04", "2R", "too tight to survive the spread")]
        for stop, target, why in cases:
            with self.assertRaises(exitp.PlanError) as cm:
                c(364.18, stop, target)
            self.assertIn(why, str(cm.exception), stop)
        # 0.05% of 364.18 is 0.182: a $0.19 risk is allowed, $0.18 is not
        self.assertEqual(c(364.18, "price:363.99")["risk"], Decimal("0.19"))
        with self.assertRaises(exitp.PlanError):
            c(364.18, "price:364.00")
        with self.assertRaises(exitp.PlanError):
            c(358.00, "or-mid")                                     # the midpoint is above this entry
        for bad in ("mid-ish", "pct:100", "price:0", "atr:-1"):
            with self.assertRaises(exitp.PlanError):
                exitp.parse_stop(bad)
        for bad in ("0R", "R", "lots", "price:x"):
            with self.assertRaises(exitp.PlanError):
                exitp.parse_target(bad)
        with self.assertRaises(exitp.PlanError):
            c(364.18, "or-mid", oh=None, ol=None)
        with self.assertRaises(exitp.PlanError):
            c(364.18, "or-mid", oh=354.47, ol=362.18)

    def test_atr_on_the_session_bars(self):
        ch = exitp.load_chart("TSLA", "5m", None, TSLA)
        day = exitp.datetime.date(2026, 10, 19)
        bars = exitp.session_bars(ch, day, "5m", upto_slot=8)
        self.assertEqual(len(bars), 9)                              # 9:30 ... the 10:10 entry bar
        # by hand: the true range of each bar, the first one without the overnight gap
        trs, prev = [], None
        for b in bars:
            r = b["h"] - b["l"]
            if prev is not None:
                r = max(r, abs(b["h"] - prev), abs(b["l"] - prev))
            trs.append(r)
            prev = b["c"]
        self.assertAlmostEqual(trs[0], 362.18 - 354.47, places=4)
        atr, n = exitp.atr_of(bars)
        self.assertEqual(n, 9)
        self.assertAlmostEqual(atr, sum(trs) / 9, places=9)
        self.assertAlmostEqual(atr, 3.2182, places=4)
        # later in the day it uses the last 14 bars; the file's in-progress 10:45 bar and tick never count
        all_bars = exitp.session_bars(ch, day, "5m")
        self.assertEqual(len(all_bars), 15)
        self.assertEqual(exitp.atr_of(all_bars)[1], 14)


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.d)
        os.mkdir("trader")

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def write(self, path, doc):
        with open(path, "w") as fh:
            json.dump(doc, fh)

    def plan(self, *args):
        return run(exitp, ["plan", "--now", "2026-10-19 10:16"] + list(args))

    def read_plan(self):
        with open(os.path.join("trader", "plan.json")) as fh:
            return json.load(fh)

    def test_entry_to_plan_end_to_end(self):
        code, _, _ = run(entry, ["check", "TSLA", "--offline", TSLA, "--now", "2026-10-19 10:15", "--write"])
        self.assertEqual(code, 0)
        code, text, err = self.plan("--stop", "or-mid", "--target", "1R", "--write")
        self.assertEqual(code, 0, err)
        p = self.read_plan()
        for k, v in REEL_PLAN.items():
            self.assertEqual(p[k], v, k)
        self.assertIn("Stop          $358.32  opening-range midpoint", text)
        self.assertIn("Target        $370.04  1R (one times the risk)", text)
        self.assertIn("Risk a share  $5.86 (1.61% of the entry)", text)
        self.assertIn("Reward:risk   1.0", text)
        self.assertIn("Flat by       15:55", text)
        self.assertIn("not a guarantee", text)
        self.assertIn("/trader-timemachine", text)
        self.assertNotIn("pro" + "fit", text.lower())   # never on screen
        code, text, _ = self.plan("--write")                       # the defaults: or-mid, 2R
        self.assertEqual(self.read_plan()["target"], 375.90)
        self.assertEqual(self.read_plan()["target_r"], 2.0)
        code, text, _ = run(exitp, ["show", "--now", "2026-10-19 10:20"])
        self.assertEqual(code, 0)
        self.assertIn("$375.90", text)
        self.assertNotIn("not today", text)
        code, text, _ = run(exitp, ["show", "--now", "2026-10-20 10:20"])
        self.assertIn("not today", text)

    def test_manual_flags_and_json(self):
        code, text, _ = self.plan("--symbol", "tsla", "--entry", "364.18", "--or-high", "362.18", "--or-low", "354.47",
                                  "--time", "10:15", "--entry-bar", "8", "--date", "2026-10-19", "--target", "1R",
                                  "--json")
        self.assertEqual(code, 0)
        p = json.loads(text)
        for k, v in REEL_PLAN.items():
            self.assertEqual(p[k], v, k)
        self.assertEqual(p["warnings"], [])

    def test_atr_stop_reads_bars(self):
        self.write(os.path.join("trader", "entry.json"), REEL_ENTRY)
        code, text, err = self.plan("--stop", "atr:1.5", "--offline", TSLA, "--json")
        self.assertEqual(code, 0, err)
        p = json.loads(text)
        self.assertEqual((p["stop"], p["risk_per_share"], p["target"]), (359.35, 4.83, 373.84))
        self.assertEqual((p["stop_rule"], p["atr_bars"]), ("atr", 9))
        self.assertAlmostEqual(p["atr"], 3.2182, places=4)
        code, _, err = self.plan("--stop", "atr:1.5", "--offline", TSLA, "--entry-bar", "1", "--time", "9:40 AM")
        self.assertEqual(code, 1)
        self.assertIn("at least 3 closed", err)
        code, _, err = self.plan("--stop", "atr:1.5", "--offline", TSLA, "--entry-bar", "1")
        self.assertEqual(code, 1)                    # entry.json says 10:15 AM, which closes bar 8
        self.assertIn("entry_bar 1 but the entry time 10:15 AM closes bar 8", err)

    def test_refusals_from_the_cli(self):
        self.write(os.path.join("trader", "entry.json"), dict(REEL_ENTRY, status="waiting", time=None, price=None,
                                                              bar_index=None, bar_start=None))
        code, _, err = self.plan()
        self.assertEqual(code, 1)
        self.assertIn("TSLA is waiting, not triggered", err)
        code, text, _ = self.plan("--entry", "362.19", "--json")    # plan ahead at the level
        self.assertEqual(code, 0)
        p = json.loads(text)
        self.assertEqual((p["entry"], p["stop"], p["entry_time"]), (362.19, 358.32, None))

        self.write(os.path.join("trader", "entry.json"), dict(REEL_ENTRY, setup="level", level=362.0))
        code, _, err = self.plan()
        self.assertIn("level setup has no opening-range stop", err)
        self.assertEqual(self.plan("--stop", "pct:1")[0], 0)

        code, _, err = self.plan("--side", "sell")
        self.assertIn("v2 plans longs only", err)
        self.write(os.path.join("trader", "entry.json"), dict(REEL_ENTRY, side="sell"))
        code, _, err = self.plan()
        self.assertIn("longs only", err)
        code, _, err = self.plan("--stop", "price:364.10")
        self.assertIn("longs only", err)
        os.remove(os.path.join("trader", "entry.json"))
        code, _, err = self.plan()
        self.assertIn("no entry", err)
        code, _, err = self.plan("--symbol", "TSLA")
        self.assertIn("needs --entry", err)
        code, _, err = self.plan("--symbol", "TSLA", "--from", "x.json", "--entry", "1")
        self.assertIn("not both", err)
        code, _, err = self.plan("--symbol", "TSLA", "--entry", "364.18", "--or-high", "362.18")
        self.assertIn("both --or-high and --or-low", err)
        self.assertNotIn("Traceback", err)

    def test_flat_by_config_half_day_and_late_entries(self):
        self.write(os.path.join("trader", "entry.json"), REEL_ENTRY)
        self.write(os.path.join("trader", "config.json"), {"flat_by": "15:45", "min_reward_risk": 1.5})
        code, text, _ = self.plan("--target", "1R", "--json")
        p = json.loads(text)
        self.assertEqual(p["flat_by"], "15:45")
        self.assertIn("under your min_reward_risk 1.5", p["warnings"][0])
        os.remove(os.path.join("trader", "config.json"))

        half = dict(REEL_ENTRY, date="2026-11-27")
        self.write(os.path.join("trader", "entry.json"), half)
        code, text, _ = run(exitp, ["plan", "--now", "2026-11-27 10:16"])
        self.assertEqual(code, 0)
        self.assertIn("Flat by       12:55 ET", text)
        self.assertIn("early close", text)
        code, _, err = run(exitp, ["plan", "--now", "2026-11-27 10:16", "--flat-by", "14:00"])
        self.assertEqual(code, 1)
        self.assertIn("after the 1:00 PM close", err)

        self.write(os.path.join("trader", "entry.json"), REEL_ENTRY)
        code, _, err = self.plan("--flat-by", "16:30")
        self.assertIn("after the 4:00 PM close", err)
        self.write(os.path.join("trader", "entry.json"), dict(REEL_ENTRY, time="3:58 PM"))
        code, _, err = self.plan()
        self.assertEqual(code, 1)
        self.assertIn("no time left to hold it", err)

    def test_show_without_a_plan(self):
        code, text, _ = run(exitp, ["show"])
        self.assertEqual(code, 1)
        self.assertIn("No plan", text)


def ts(hhmm):
    """2026-10-19 New York time HH:MM -> the Yahoo timestamp (EDT, UTC-4)."""
    h, m = map(int, hhmm.split(":"))
    return calendar.timegm((2026, 10, 19, h + 4, m, 0))


class NoLookAhead(unittest.TestCase):
    """Fix 5: the ATR uses closed bars up to the entry and nothing after it."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(TSLA) as fh:
            self.chart = json.load(fh)

    def tearDown(self):
        shutil.rmtree(self.d)

    def quote(self):
        return self.chart["chart"]["result"][0]["indicators"]["quote"][0]

    def stamps(self):
        return self.chart["chart"]["result"][0]["timestamp"]

    def save(self, name="chart.json"):
        path = os.path.join(self.d, name)
        with open(path, "w") as fh:
            json.dump(self.chart, fh)
        return path

    def plan(self, path, *extra):
        argv = ["plan", "--symbol", "TSLA", "--entry", "364.18", "--date", "2026-10-19", "--stop", "atr:1.5",
                "--offline", path, "--now", "2026-10-19 10:16", "--json"] + list(extra)
        return run(exitp, argv)

    def test_later_bars_do_not_change_the_atr_or_the_stop(self):
        code, text, err = self.plan(TSLA, "--entry-bar", "8")
        self.assertEqual(code, 0, err)
        base = json.loads(text)
        self.assertEqual((base["stop"], base["atr_bars"]), (359.35, 9))
        # make every bar after the entry wildly volatile, then replay with the clock long after them
        q = self.quote()
        for i, t in enumerate(self.stamps()):
            if t > ts("10:10"):
                q["high"][i], q["low"][i], q["close"][i] = 999.0, 1.0, 500.0
        wild = self.save()
        for extra in (["--entry-bar", "8"], ["--time", "10:15 AM"], ["--entry-bar", "8", "--now", "2026-10-19 15:00"]):
            argv = list(extra)
            code, text, err = run(exitp, ["plan", "--symbol", "TSLA", "--entry", "364.18", "--date", "2026-10-19",
                                          "--stop", "atr:1.5", "--offline", wild, "--json"] + argv)
            self.assertEqual(code, 0, (extra, err))
            p = json.loads(text)
            self.assertEqual((p["stop"], p["atr"], p["atr_bars"], p["entry_bar"]),
                             (base["stop"], base["atr"], base["atr_bars"], 8), extra)

    def test_the_entry_bar_is_required(self):
        code, _, err = self.plan(TSLA)
        self.assertEqual(code, 1)
        self.assertIn("an atr stop needs the entry bar", err)
        self.assertFalse(os.path.exists(os.path.join(self.d, "plan.json")))

    def test_a_bad_entry_bar(self):
        for bad in ("-1", "78", "500"):
            code, _, err = self.plan(TSLA, "--entry-bar=" + bad)
            self.assertEqual(code, 1, bad)
            self.assertIn("outside the 5m session", err)
        for bad in ("eight", 8.5, True, "8"):
            info = {"entry_bar": bad, "entry_time": None}
            with self.assertRaises(exitp.PlanError, msg=repr(bad)):
                exitp.entry_slot(info, exitp.datetime.date(2026, 10, 19), "5m")
        code, _, err = self.plan(TSLA, "--time", "10:17 AM")
        self.assertIn("is not the close of a 5m bar", err)

    def test_an_entry_bar_that_has_not_closed(self):
        code, _, err = self.plan(TSLA, "--entry-bar", "8", "--now", "2026-10-19 10:12")
        self.assertEqual(code, 1)
        self.assertIn("is not a closed bar in the data by --now", err)

    def test_repeated_or_out_of_order_timestamps(self):
        st = self.stamps()
        i = st.index(ts("09:45"))
        st[i] = st[i - 1]
        code, _, err = self.plan(self.save(), "--entry-bar", "8")
        self.assertEqual(code, 1)
        self.assertIn("out of order or repeated", err)

    def test_a_missing_bar_up_to_the_entry(self):
        i = self.stamps().index(ts("09:50"))
        self.quote()["close"][i] = None              # Yahoo's null bar: dropped, which leaves a gap
        code, _, err = self.plan(self.save(), "--entry-bar", "8")
        self.assertEqual(code, 1)
        self.assertIn("missing 1 of the 9 bars up to the entry (first gap at 09:50)", err)

    def test_bad_ohlc(self):
        i = self.stamps().index(ts("09:40"))
        for field, bad, why in (("high", float("nan"), "not a finite number"),
                                ("low", float("inf"), "not a finite number"),
                                ("close", -1.0, "not a finite number above 0"),
                                ("high", 1.0, "not coherent")):
            with open(TSLA) as fh:
                self.chart = json.load(fh)
            self.quote()[field][i] = bad
            code, _, err = self.plan(self.save(), "--entry-bar", "8")
            self.assertEqual(code, 1, (field, bad))
            self.assertIn(why, err)
            self.assertNotIn("Traceback", err)

    def test_nan_and_infinite_prices_from_the_flags(self):
        for bad in ("nan", "inf", "-inf"):
            code, _, err = run(exitp, ["plan", "--symbol", "TSLA", "--entry=" + bad, "--stop", "pct:1",
                                       "--now", "2026-10-19 10:16"])
            self.assertEqual(code, 1, bad)
            self.assertIn("finite", err)
        code, _, err = run(exitp, ["plan", "--symbol", "TSLA", "--entry", "364.18", "--or-high", "nan",
                                   "--or-low", "354.47", "--now", "2026-10-19 10:16"])
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)


class SkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(ROOT, "trader-exit", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        with open(os.path.join(ROOT, "trader-risk", "SKILL.md"), encoding="utf-8") as fh:
            risk = fh.read()
        self.assertTrue(text.startswith("---\nname: trader-exit\n"))
        self.assertGreater(len(text.splitlines()), 60)
        self.assertEqual(text[text.index("## Safety"):], risk[risk.index("## Safety"):])
        low = " ".join(text.lower().split())
        for must in ("before the entry", "a stop is a plan, not a guarantee", "day trading loses most people money", "/trader-timemachine", "/trader-budget", "longs only", "$358.32", "$370.04", "$5.86", "375.90", "too tight to survive the spread"):
            self.assertIn(must, low)
        for never in ("\u2014", "tick " + "by tick", "real " + "time", "pro" + "fit"):
            self.assertNotIn(never, low)


if __name__ == "__main__":
    unittest.main()
