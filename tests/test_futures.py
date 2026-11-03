import csv
import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from _load import load, ROOT, FIX

sys.path.insert(0, os.path.join(ROOT, "trader-futures"))
fx = load("trader-futures", "futures")
sys.modules["futures"] = fx
at = load("trader-futures", "autotrader")

UTC = datetime.timezone.utc
BARS = os.path.join(FIX, "trader-futures", "mes-synthetic.csv")
NY = fx.tz("America/New_York")


def ny(day, hm):
    h, m = map(int, hm.split(":"))
    return datetime.datetime.combine(datetime.date.fromisoformat(day), datetime.time(h, m), tzinfo=NY).astimezone(UTC)


def bars():
    return fx.load_bars_csv(BARS)


def mirror(bs, pivot=13800.0):
    """Price-mirror the fixture: every up move becomes a down move."""
    out = []
    for b in bs:
        out.append({"t": b["t"], "o": pivot - b["o"], "h": pivot - b["l"], "l": pivot - b["h"],
                    "c": pivot - b["c"], "v": b["v"]})
    return out


MES = fx.spec_for("MES")


class TestBasics(unittest.TestCase):
    def test_specs_have_everything(self):
        for k, s in fx.SPECS.items():
            for f in ("symbol", "exchange", "currency", "multiplier", "tick", "tz", "open", "window", "flat_by"):
                self.assertIn(f, s, "%s misses %s" % (k, f))
            self.assertIn(s["currency"], ("USD", "EUR"))

    def test_round_tick(self):
        self.assertEqual(fx.round_tick(6915.13, 0.25), 6915.25)
        self.assertEqual(fx.round_tick(6915.13, 0.25, "down"), 6915.0)
        self.assertEqual(fx.round_tick(6915.01, 0.25, "up"), 6915.25)
        self.assertEqual(fx.round_tick(2200.06, 0.1, "down"), 2200.0)

    def test_spec_unknown(self):
        with self.assertRaises(fx.FuturesError):
            fx.spec_for("TSLA")

    def test_pick_contract_rolls_8_days_before_expiry(self):
        months = [{"expiry": "20261218"}, {"expiry": "20270319"}, {"expiry": "20260918"}]
        self.assertEqual(fx.pick_contract(months, datetime.date(2026, 11, 3), 8)["expiry"], "20261218")
        self.assertEqual(fx.pick_contract(months, datetime.date(2026, 12, 9), 8)["expiry"], "20261218")
        self.assertEqual(fx.pick_contract(months, datetime.date(2026, 12, 10), 8)["expiry"], "20270319")

    def test_dutch_numbers(self):
        self.assertEqual(fx.nl(48.63), "48,63")
        self.assertEqual(fx.nl(6917.0), "6917")
        self.assertEqual(fx.nl(None), "")


class TestSignal(unittest.TestCase):
    def test_surge_bar_fires(self):
        sig = fx.evaluate(bars(), ny("2026-10-30", "10:30"), MES)
        self.assertEqual(sig["status"], "signal")
        self.assertEqual(sig["direction"], "long")
        self.assertEqual(sig["slot"], "15:25")         # shown in Dutch time (NY is 5 hours behind that week)
        self.assertEqual(sig["session"], "us")
        self.assertEqual(sig["flat_by_utc"], ny("2026-10-30", "15:55").isoformat())
        self.assertGreaterEqual(sig["metrics"]["rvol"], 2.5)

    def test_quiet_bar_does_not_fire(self):
        sig = fx.evaluate(bars(), ny("2026-10-30", "10:25"), MES)
        self.assertEqual(sig["status"], "none")
        self.assertTrue(any(r.startswith("NO") for r in sig["reasons"]))

    def test_outside_window(self):
        self.assertEqual(fx.evaluate(bars(), ny("2026-10-30", "09:40"), MES)["status"], "outside-window")
        self.assertEqual(fx.evaluate(bars(), ny("2026-10-30", "15:35"), MES)["status"], "outside-window")

    def test_stale_data(self):
        bs = [b for b in bars() if b["t"] < ny("2026-10-30", "10:00")]
        self.assertEqual(fx.evaluate(bs, ny("2026-10-30", "10:30"), MES)["status"], "no-data")

    def test_forming_bar_is_ignored(self):
        # at 10:29 the surge bar (10:25-10:30) has not closed yet
        sig = fx.evaluate(bars(), ny("2026-10-30", "10:29"), MES)
        self.assertEqual(sig["slot"], "15:20")
        self.assertNotEqual(sig["status"], "signal")

    def test_short_off_by_default_on_by_config(self):
        m = mirror(bars())
        self.assertEqual(fx.evaluate(m, ny("2026-10-30", "10:30"), MES)["status"], "none")
        sig = fx.evaluate(m, ny("2026-10-30", "10:30"), MES, {"directions": ["long", "short"]})
        self.assertEqual(sig["status"], "signal")
        self.assertEqual(sig["direction"], "short")

    def test_volume_threshold(self):
        sig = fx.evaluate(bars(), ny("2026-10-30", "10:30"), MES, {"rvol_min": 5.0})
        self.assertEqual(sig["status"], "none")

    def test_thin_back_month_days_left_out(self):
        bs = bars()
        # make the first six sessions "back month": a tenth of the volume
        days = sorted({fx.session_day(b["t"], MES) for b in bs})
        thin = set(days[:6])
        for b in bs:
            if fx.session_day(b["t"], MES) in thin:
                b["v"] = b["v"] / 10.0
        sig = bs[[i for i, b in enumerate(bs) if b["t"] == ny("2026-10-30", "10:25")][0]]
        base, n = fx.baseline_volume(bs[:bs.index(sig) + 1], sig, MES, 10, 5, 0.5)
        self.assertEqual(n, 5)                          # only the five normal sessions
        self.assertGreater(base, 1200)
        base0, n0 = fx.baseline_volume(bs[:bs.index(sig) + 1], sig, MES, 10, 5, 0.0)
        self.assertEqual(n0, 10)
        self.assertLess(base0, base)                    # without the guard the baseline drops: false surges


class TestNikkei(unittest.TestCase):
    MNK = fx.spec_for("MNK")

    def test_spec(self):
        s = self.MNK
        self.assertEqual((s["exchange"], s["currency"], s["multiplier"], s["tick"], s["tz"]),
                         ("CME", "USD", 0.5, 5.0, "Asia/Tokyo"))

    def test_window_in_dutch_time(self):
        ams = fx.tz("Europe/Amsterdam")
        day = datetime.date(2026, 11, 4)                     # Dutch winter time: JST is 8 hours ahead
        w0 = fx.at_local(day, self.MNK["window"][0], self.MNK).astimezone(ams)
        flat = fx.at_local(day, self.MNK["flat_by"], self.MNK).astimezone(ams)
        self.assertEqual((w0.strftime("%H:%M"), flat.strftime("%H:%M")), ("01:15", "07:25"))
        summer = fx.at_local(datetime.date(2026, 7, 1), "09:15", self.MNK).astimezone(ams)
        self.assertEqual(summer.strftime("%H:%M"), "02:15")  # 7 hours ahead in summer

    def test_signal_in_the_tokyo_session(self):
        # the MES fixture moved to Tokyo wall-clock time (same HH:MM), 0.25 ticks kept
        tokyo = fx.tz("Asia/Tokyo")
        moved = []
        for b in bars():
            lt = b["t"].astimezone(NY).replace(tzinfo=tokyo)
            moved.append(dict(b, t=lt.astimezone(UTC)))
        spec = fx.spec_for("MNK", {"tick": 0.25})
        when = datetime.datetime(2026, 10, 30, 10, 30, tzinfo=tokyo).astimezone(UTC)
        self.assertEqual(fx.evaluate(moved, when, spec)["status"], "signal")
        early = datetime.datetime(2026, 10, 30, 9, 10, tzinfo=tokyo).astimezone(UTC)
        self.assertEqual(fx.evaluate(moved, early, spec)["status"], "outside-window")

    def test_size_with_a_five_point_tick(self):
        plan = {"risk_points": 40.0}                          # 8 ticks
        s = fx.size(plan, self.MNK, {"max_loss_per_trade_eur": 100, "max_contracts": 10}, eurusd=1.08)
        # (40 + 2 x 5 stop slippage) x $0.50 + 2 x 0.62 = $26.24 = EUR 24.30 per contract
        self.assertEqual(s["risk_per_contract_eur"], 24.3)
        self.assertEqual(s["qty"], 4)

    def test_plan_rounds_to_five_points(self):
        sig = {"bar": {"o": 51000.0, "h": 51120.0, "l": 51000.0, "c": 51110.0}, "direction": "long",
               "metrics": {"atr": 60.0}, "bar_time": "x"}
        plan, why = fx.make_plan(sig, self.MNK)
        for k in ("limit", "stop", "target"):
            self.assertEqual(plan[k] % 5.0, 0.0, k)
        self.assertEqual((plan["limit"], plan["stop"]), (51120.0, 51055.0))

    def test_three_sessions(self):
        mnk = self.MNK
        self.assertEqual([v["session"] for v in fx.sessions(mnk)], ["tokyo", "europe", "us"])

        def at(zone, hm, day="2026-11-04"):
            h, m = map(int, hm.split(":"))
            return datetime.datetime.combine(datetime.date.fromisoformat(day), datetime.time(h, m),
                                             tzinfo=fx.tz(zone)).astimezone(UTC)
        self.assertEqual(fx.session_for(mnk, at("Asia/Tokyo", "10:00"))["session"], "tokyo")
        self.assertEqual(fx.session_for(mnk, at("Europe/Berlin", "10:00"))["session"], "europe")
        self.assertEqual(fx.session_for(mnk, at("America/New_York", "10:00"))["session"], "us")
        self.assertIsNone(fx.session_for(mnk, at("Europe/Berlin", "08:00")))     # between Tokyo and Europe
        self.assertIsNone(fx.session_for(mnk, at("America/New_York", "16:00")))  # after the US session

    def test_windows_and_flat_times_do_not_overlap(self):
        # on ordinary days each session is flat before the next one opens
        for day in ("2026-01-14", "2026-07-15", "2026-11-04"):
            d = datetime.date.fromisoformat(day)
            vs = fx.sessions(self.MNK)
            spans = sorted((fx.at_local(d, v["window"][0], v), fx.at_local(d, v["flat_by"], v)) for v in vs)
            for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
                self.assertLessEqual(a1, b0, day)

    def test_sessions_from_config(self):
        cfg = fx.load_config(None)
        cfg["contract_overrides"] = {"MNK": {"sessions": ["tokyo", "us"]}}
        self.assertEqual([v["session"] for v in fx.sessions(fx.spec_for("MNK", cfg))], ["tokyo", "us"])
        cfg["contract_overrides"] = {"MNK": {"sessions": ["mars"]}}
        with self.assertRaises(fx.FuturesError):
            fx.sessions(fx.spec_for("MNK", cfg))
        self.assertEqual(fx.sessions(fx.spec_for("MES"))[0]["session"], "us")
        self.assertEqual(fx.sessions(fx.spec_for("FDXS"))[0]["session"], "europe")

    def test_backtest_finds_the_tokyo_trade_and_only_in_its_session(self):
        tokyo = fx.tz("Asia/Tokyo")
        moved = [dict(b, t=b["t"].astimezone(NY).replace(tzinfo=tokyo).astimezone(UTC)) for b in bars()]
        res = fx.backtest(moved, fx.spec_for("MNK", {"tick": 0.25, "multiplier": 5.0}), eurusd=1.08)
        self.assertEqual(len(res["trades"]), 1)
        t = res["trades"][0]
        self.assertEqual((t["session"], t["signal"], t["exit_reason"]), ("tokyo", "02:25", "target"))
        only_us = fx.spec_for("MNK", {"tick": 0.25, "multiplier": 5.0, "sessions": ["us"]})
        self.assertEqual(fx.backtest(moved, only_us, eurusd=1.08)["summary"]["trades"], 0)

    def test_symbol_override_from_config(self):
        cfg = fx.load_config(None)
        cfg["contract_overrides"] = {"MNK": {"symbol": "NKMICRO"}}
        self.assertEqual(fx.spec_for("MNK", cfg)["symbol"], "NKMICRO")
        self.assertEqual(fx.spec_for("MES", cfg)["symbol"], "MES")
        self.assertEqual(fx.spec_for("MNK", fx.load_config(None))["symbol"], "MNK")


class TestPlanSizeRisk(unittest.TestCase):
    def setUp(self):
        self.sig = fx.evaluate(bars(), ny("2026-10-30", "10:30"), MES)
        self.plan, why = fx.make_plan(self.sig, MES)

    def test_plan(self):
        p = self.plan
        self.assertEqual(p["action"], "BUY")
        self.assertEqual(p["limit"], 6917.75)           # close 6917.25 + 2 ticks
        self.assertEqual(p["stop"], 6915.0)             # bar midpoint 6915.375 - tick, rounded down
        self.assertEqual(p["risk_points"], 2.75)
        self.assertEqual(p["target"], 6922.75)          # 6917.25 + 2 x 2.75

    def test_plan_refuses_wide_stop(self):
        plan, why = fx.make_plan(self.sig, MES, {"max_stop_atr": 0.5})
        self.assertIsNone(plan)
        self.assertIn("ATR", why)

    def test_size_in_eur(self):
        s = fx.size(self.plan, MES, {"max_loss_per_trade_eur": 100, "max_contracts": 10}, eurusd=1.08)
        # (2.75 + 0.5 stop slippage) x $5 + 2 x 0.62 = $17.49 = EUR 16.19 per contract
        self.assertEqual(s["risk_per_contract_eur"], 16.19)
        self.assertEqual(s["qty"], 6)
        self.assertEqual(s["bound_by"], "max loss per trade")
        s2 = fx.size(self.plan, MES, {"max_loss_per_trade_eur": 100, "max_contracts": 2}, eurusd=1.08)
        self.assertEqual((s2["qty"], s2["bound_by"]), (2, "max contracts"))
        s3 = fx.size(self.plan, MES, {"max_loss_per_trade_eur": 10}, eurusd=1.08)
        self.assertEqual(s3["qty"], 0)
        self.assertIn("more than your max loss", s3["reason"])

    def test_eur_contract_no_conversion(self):
        dax = fx.spec_for("FDXS")
        plan = {"risk_points": 20.0}
        s = fx.size(plan, dax, {"max_loss_per_trade_eur": 100, "commission_per_side": 0.5}, eurusd=1.5)
        self.assertEqual(s["risk_per_contract_eur"], 23.0)   # (20 + 2) x EUR 1 + 1.00

    def risk(self, state, **over):
        sized = fx.size(self.plan, MES, None, 1.08)
        r = dict(fx.RISK)
        r.update(over)
        return fx.risk_check(self.plan, sized, MES, state, ny("2026-10-30", "10:30"), r)

    def test_risk_pass(self):
        ok, reasons = self.risk({"trades": 0, "pnl_eur": 0, "open": {}})
        self.assertTrue(ok, reasons)

    def test_risk_rules(self):
        self.assertFalse(self.risk({"trades": 3})[0])
        self.assertFalse(self.risk({"open": {"MES": 1}})[0])
        self.assertFalse(self.risk({"open": {"MNQ": 1}})[0])          # max one open position
        self.assertFalse(self.risk({"pnl_eur": -250})[0])
        ok, why = self.risk({"pnl_eur": -230})                         # a stop-out would cross the limit
        self.assertFalse(ok)
        self.assertIn("past the daily loss limit", why[0])
        self.assertFalse(self.risk({"halted": "x"})[0])
        self.assertFalse(self.risk({"last_loss": {"MES": ny("2026-10-30", "10:10").isoformat()}})[0])
        self.assertTrue(self.risk({"last_loss": {"MES": ny("2026-10-30", "09:50").isoformat()}})[0])

    def test_margin_rule(self):
        sized = fx.size(self.plan, MES, None, 1.08)
        ok, why = fx.risk_check(self.plan, sized, MES, {}, ny("2026-10-30", "10:30"), None,
                                {"init_eur": 3000, "available_eur": 5000})
        self.assertFalse(ok)
        ok, _ = fx.risk_check(self.plan, sized, MES, {}, ny("2026-10-30", "10:30"), None,
                              {"init_eur": 2000, "available_eur": 5000})
        self.assertTrue(ok)


class TestBacktest(unittest.TestCase):
    def test_one_winning_trade(self):
        res = fx.backtest(bars(), MES, eurusd=1.08)
        self.assertEqual(len(res["trades"]), 1)
        t = res["trades"][0]
        self.assertEqual((t["date"], t["signal"], t["entry_time"], t["exit_reason"]),
                         ("2026-10-30", "15:25", "15:30", "target"))
        self.assertEqual(t["session"], "us")
        self.assertEqual(t["qty"], 2)
        self.assertEqual(t["entry"], 6917.25)
        self.assertEqual(t["exit"], 6922.75)
        # 5.5 points x $5 x 2 = $55 - 4 x $0.62 = $52.52 / 1.08
        self.assertEqual(t["pnl_eur"], 48.63)

    def test_missed_when_it_gaps_past_the_limit(self):
        bs = bars()
        nxt = [b for b in bs if b["t"] == ny("2026-10-30", "10:30")][0]
        nxt["o"] = 6918.5
        nxt["h"] = max(nxt["h"], 6918.5)
        res = fx.backtest(bs, MES, eurusd=1.08)
        self.assertEqual(res["summary"]["trades"], 0)
        self.assertEqual(res["summary"]["missed_entries"], 1)

    def test_stop_counts_first_when_bar_hits_both(self):
        bs = bars()
        b = [x for x in bs if x["t"] == ny("2026-10-30", "10:35")][0]
        b["l"], b["h"] = 6900.0, 6930.0
        res = fx.backtest(bs, MES, eurusd=1.08)
        t = res["trades"][0]
        self.assertEqual(t["exit_reason"], "stop")
        self.assertEqual(t["exit"], 6914.5)              # stop 6915 - 2 ticks slippage
        self.assertLess(t["pnl_eur"], 0)

    def test_csv_for_excel(self):
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "t.csv")
            fx.write_trades_csv(path, fx.backtest(bars(), MES, eurusd=1.08)["trades"])
            with open(path, encoding="utf-8-sig") as fh:
                rows = list(csv.reader(fh, delimiter=";"))
            self.assertEqual(rows[0][0], "date")
            self.assertIn("48,63", rows[1])
        finally:
            shutil.rmtree(d)


# ---------------------------------------------------------------- the autotrader

class FakeBroker(object):
    """Behaves like ibkr.Broker on the synthetic MES fixture."""

    def __init__(self, account="DU1234567", pnl=0.0):
        self.acct = account
        self.all = bars()
        self.pos = 0
        self.orders, self.flattens = [], []
        self.pnl = pnl
        self.now = None
        self.exit_px = None

    def account_info(self):
        return {"account": self.acct, "paper": self.acct.startswith("DU"), "base": "EUR",
                "net_liq": 10000.0, "available": 10000.0}

    def resolve(self, spec, today, roll):
        return "MESZ6", {"multiplier": 5.0, "tick": 0.25, "local_symbol": "MESZ6", "expiry": "20261218"}

    def bars(self, c):
        return [b for b in self.all if b["t"] <= self.now]

    def eurusd(self):
        return 1.08

    def daily_pnl_eur(self):
        return self.pnl

    def available_eur(self):
        return 10000.0

    def margin_eur(self, c, action, qty):
        return 1500.0 * qty

    def position(self, c):
        return self.pos

    def place_bracket(self, c, plan, qty, timeout):
        self.orders.append((plan, qty))
        self.pos = qty if plan["action"] == "BUY" else -qty
        return {"status": "filled", "qty": qty, "avg": plan["limit"] - 0.5}

    def flatten(self, c):
        self.flattens.append(self.pos)
        closed, self.pos = self.pos, 0
        return {"closed": closed, "avg": 6920.0}

    def exit_fill(self, c, since):
        return {"avg": self.exit_px, "qty": 2, "commission": 1.24} if self.exit_px else None

    def connected(self):
        return True

    def sleep(self, s):
        pass


class TestAutotrader(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cfg = fx.load_config(None)
        self.cfg["contracts"] = ["MES"]
        self.msgs = []

    def tearDown(self):
        shutil.rmtree(self.dir)

    def engine(self, broker, mode="paper", cfg=None):
        clock = {"t": ny("2026-10-30", "09:00")}

        def notify(title, text="", priority="default", push=True):
            self.msgs.append(title + " | " + text)

        e = at.Engine(broker, cfg or self.cfg, mode, self.dir, notify, clock=lambda: clock["t"])
        e._clock = clock
        return e

    def step(self, e, b, when):
        e._clock["t"] = b.now = when
        return e.tick()

    def test_paper_mode_refuses_live_account(self):
        e = self.engine(FakeBroker("U7654321"), "paper")
        with self.assertRaises(SystemExit) as cm:
            e.setup()
        self.assertIn("not a paper account", str(cm.exception))

    def test_live_mode_needs_the_sentence(self):
        cfg = fx.load_config(None)
        e = self.engine(FakeBroker("U7654321"), "live", cfg)
        with self.assertRaises(SystemExit):
            e.setup()
        cfg["paper"] = False
        cfg["live_confirm"] = "ja"
        with self.assertRaises(SystemExit):
            self.engine(FakeBroker("U7654321"), "live", cfg).setup()
        cfg["live_confirm"] = at.LIVE_SENTENCE
        self.engine(FakeBroker("U7654321"), "live", cfg).setup()          # passes
        with self.assertRaises(SystemExit):
            self.engine(FakeBroker("DU1"), "live", cfg).setup()            # paper account in live mode

    def test_observe_never_orders(self):
        b = FakeBroker()
        e = self.engine(b, "observe")
        e.setup()
        self.step(e, b, ny("2026-10-30", "10:30") + datetime.timedelta(seconds=5))
        self.assertEqual(b.orders, [])
        self.assertTrue(any("observe: no order" in m for m in self.msgs))

    def test_paper_trade_lifecycle(self):
        b = FakeBroker()
        e = self.engine(b, "paper")
        e.setup()
        t = ny("2026-10-30", "10:30") + datetime.timedelta(seconds=5)
        self.step(e, b, t)
        self.assertEqual(len(b.orders), 1)
        plan, qty = b.orders[0]
        self.assertEqual((plan["action"], qty, plan["stop"], plan["target"]), ("BUY", 2, 6915.0, 6922.75))
        # the same bar never orders twice
        self.step(e, b, t + datetime.timedelta(seconds=30))
        self.assertEqual(len(b.orders), 1)
        # target hit at the broker: position gone -> journal row
        b.pos, b.exit_px = 0, 6922.75
        self.step(e, b, ny("2026-10-30", "10:50") + datetime.timedelta(seconds=5))
        with open(os.path.join(self.dir, "journal.csv"), encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        self.assertEqual(rows[1][rows[0].index("exit_reason")], "target")
        self.assertEqual(rows[1][rows[0].index("contract")], "MESZ6")
        self.assertEqual(rows[1][rows[0].index("session")], "us")
        self.assertEqual(rows[1][rows[0].index("entry_time")], "15:30")
        with open(e.state.path) as fh:
            st = json.load(fh)
        self.assertEqual(st["trades"], 1)
        self.assertEqual(st["open_trades"], {})

    def test_flat_by_close(self):
        b = FakeBroker()
        e = self.engine(b, "paper")
        e.setup()
        self.step(e, b, ny("2026-10-30", "10:30") + datetime.timedelta(seconds=5))
        self.assertEqual(b.pos, 2)
        self.step(e, b, ny("2026-10-30", "15:55") + datetime.timedelta(seconds=1))
        self.assertEqual(b.flattens, [2])
        self.assertEqual(b.pos, 0)

    def test_manual_position_is_not_touched_but_blocks_entries(self):
        b = FakeBroker()
        b.pos = 1                                # you bought 1 MES yourself
        e = self.engine(b, "paper")
        e.setup()
        self.step(e, b, ny("2026-10-30", "10:30") + datetime.timedelta(seconds=5))
        self.assertEqual(b.orders, [])
        self.assertTrue(any("BLOCKED" in m for m in self.msgs))
        self.step(e, b, ny("2026-10-30", "15:56"))
        self.assertEqual(b.flattens, [])         # not ours: not flattened

    def test_daily_loss_halts_and_flattens(self):
        b = FakeBroker(pnl=-260.0)
        b.pos = 0
        e = self.engine(b, "paper")
        e.setup()
        self.step(e, b, ny("2026-10-30", "10:30") + datetime.timedelta(seconds=5))
        self.assertEqual(b.orders, [])
        with open(e.state.path) as fh:
            self.assertIn("daily loss limit", json.load(fh)["halted"])

    def test_stop_file(self):
        b = FakeBroker()
        e = self.engine(b, "paper")
        e.setup()
        self.step(e, b, ny("2026-10-30", "10:30") + datetime.timedelta(seconds=5))
        open(os.path.join(self.dir, "STOP"), "w").close()
        self.assertEqual(self.step(e, b, ny("2026-10-30", "10:31")), "stop")
        self.assertEqual(b.flattens, [2])

    def test_max_trades_per_day(self):
        b = FakeBroker()
        cfg = fx.load_config(None)
        cfg["risk"]["max_trades_per_day"] = 0
        e = self.engine(b, "paper", cfg)
        e.setup()
        self.step(e, b, ny("2026-10-30", "10:30") + datetime.timedelta(seconds=5))
        self.assertEqual(b.orders, [])


class TestCli(unittest.TestCase):
    def test_backtest_cli(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = fx.main(["--config", "nope.json", "backtest", "--contract", "MES", "--bars", BARS,
                            "--eurusd", "1.08"])
        self.assertEqual(code, 0)
        self.assertIn("result EUR 48.63", out.getvalue())

    def test_config_example_loads(self):
        cfg = fx.load_config(os.path.join(ROOT, "trader-futures", "config.example.json"))
        self.assertEqual(cfg["contracts"], ["MES"])
        self.assertIs(cfg["paper"], True)
        self.assertEqual(cfg["live_confirm"], "")
        self.assertEqual(cfg["risk"]["max_daily_loss_eur"], 250)


if __name__ == "__main__":
    unittest.main()
