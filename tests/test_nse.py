"""The NSE port: clock and calendar, symbols, the trade chain end to end, Kite, results news,
quarterly numbers and bulk deals. Offline: fixtures are saved NSE feeds and a made-up session
(tests/_synth.py). Run: python3 -m unittest discover -s tests -v"""

import datetime
import gzip
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import _synth
from _load import FIX, ROOT, load

D = datetime.date


def run(folder, script, args, cwd, env=None):
    e = dict(os.environ, **(env or {}))
    p = subprocess.run([sys.executable, os.path.join(ROOT, folder, script)] + args, cwd=cwd, env=e,
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


class Clock(unittest.TestCase):
    MODULES = [("trader-entry", "entry"), ("trader-exit", "exit"), ("trader-scanner", "scan"),
               ("trader-timemachine", "timemachine"), ("trader-risk", "check"), ("trader-alerts", "alerts"),
               ("trader-budget", "size"), ("trader-broker", "ticket")]

    def test_ist_is_utc_plus_530_all_year(self):
        for folder, name in self.MODULES:
            m = load(folder, name)
            for utc in (datetime.datetime(2026, 1, 15, 3, 45), datetime.datetime(2026, 7, 15, 3, 45)):
                self.assertEqual(m.to_ist(utc), utc + datetime.timedelta(hours=5, minutes=30), name)
                self.assertEqual(m.ist_to_utc(m.to_ist(utc)), utc, name)

    def test_the_session_is_915_to_1530(self):
        entry = load("trader-entry", "entry")
        self.assertEqual(entry.session(D(2026, 11, 6)), (datetime.time(9, 15), datetime.time(15, 30)))

    def test_nse_holidays_close_the_market_and_weekends_too(self):
        for folder, name in (("trader-entry", "entry"), ("trader-scanner", "scan"), ("trader-risk", "check")):
            m = load(folder, name)
            ok, why = m.trading_day(D(2026, 11, 10))      # Diwali-Balipratipada
            self.assertFalse(ok, name)
            self.assertIn("NSE holiday", why)
            self.assertFalse(m.trading_day(D(2026, 11, 7))[0], name)    # Saturday
            self.assertTrue(m.trading_day(D(2026, 11, 6))[0], name)
            self.assertFalse(m.trading_day(D(2026, 3, 3))[0], name)     # Holi
            self.assertFalse(m.trading_day(D(2026, 1, 15))[0], name)    # Maharashtra civic election day

    def test_holiday_lists_agree_across_scripts(self):
        lists = [load(f, n).NSE_HOLIDAYS for f, n in self.MODULES if hasattr(load(f, n), "NSE_HOLIDAYS")]
        self.assertGreater(len(lists), 3)
        self.assertEqual(len(lists[0]), 16)
        for l in lists:
            self.assertEqual(l, lists[0])

    def test_nse_has_no_early_close(self):
        self.assertEqual(load("trader-entry", "entry").NSE_EARLY_CLOSE, {})

    def test_parse_now_reads_ist(self):
        entry = load("trader-entry", "entry")
        self.assertEqual(entry.parse_now("2026-11-06 10:15"), datetime.datetime(2026, 11, 6, 4, 45))
        self.assertEqual(entry.parse_now("2026-11-06 10:15 IST"), datetime.datetime(2026, 11, 6, 4, 45))


class Symbols(unittest.TestCase):
    def test_yahoo_symbols_get_ns_and_ampersands_are_quoted(self):
        entry = load("trader-entry", "entry")
        self.assertEqual(entry.yahoo_symbol("reliance"), "RELIANCE.NS")
        self.assertEqual(entry.nse_symbol("RELIANCE.NS"), "RELIANCE")
        self.assertIn("M%26M.NS", entry.chart_path("M&M", "1d", "5m"))
        scan = load("trader-scanner", "scan")
        self.assertEqual(scan.to_yahoo("BAJAJ-AUTO"), "BAJAJ-AUTO.NS")
        self.assertEqual(scan.from_yahoo("M&M.NS"), "M&M")
        self.assertIn("M%26M.NS", scan.spark_path(["M&M", "TCS"], "1d", "5m"))

    def test_universe_keeps_eq_series_only(self):
        scan = load("trader-scanner", "scan")
        with open(os.path.join(FIX, "trader-news", "EQUITY_L.csv"), encoding="utf-8") as fh:
            text = fh.read()
        kept, counts, _ = scan.build_universe({"EQUITY_L.csv": text})
        syms = dict(kept)
        self.assertIn("RELIANCE", syms)
        self.assertIn("M&M", syms)
        self.assertGreater(len(kept), 1500)
        self.assertTrue(any(k.startswith("series") for k in counts))
        self.assertEqual(scan.classify({"SYMBOL": "ABC", "SERIES": "BE"}), "series BE (not EQ)")
        with self.assertRaises(scan.ScanError):
            scan.parse_symdir("<html>maintenance</html>")


class Tick(unittest.TestCase):
    def test_stops_floor_and_targets_round_to_5_paise(self):
        exit_ = load("trader-exit", "exit")
        self.assertEqual(str(exit_.floor_tick("100.47")), "100.45")
        self.assertEqual(str(exit_.to_tick("100.48")), "100.50")
        self.assertEqual(str(exit_.to_tick("100.47")), "100.45")
        size = load("trader-budget", "size")
        self.assertEqual(size.round_cent(100.47), 100.45)
        self.assertEqual(size.round_cent(100.48), 100.5)


class Chain(unittest.TestCase):
    """entry -> exit -> budget -> risk -> broker, as the user would run them, on a made-up session."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        day = D(2026, 11, 6)
        self.off = os.path.join(self.cwd, "off")
        os.makedirs(self.off)
        with open(os.path.join(self.off, "RELIANCE.json"), "w") as fh:
            fh.write(_synth.chart("RELIANCE.NS", {day: _synth.orb_day(day)}))
        os.makedirs(os.path.join(self.cwd, "trader"))
        with open(os.path.join(ROOT, "trader-budget", "config.example.json")) as src, \
                open(os.path.join(self.cwd, "trader", "config.json"), "w") as dst:
            dst.write(src.read())
        self.now = "2026-11-06 10:00"

    def tearDown(self):
        self.tmp.cleanup()

    def step(self, folder, script, args, want=0):
        rc, out, err = run(folder, script, args, self.cwd)
        self.assertEqual(rc, want, "%s %s\n%s\n%s" % (script, args, out, err))
        return out

    def test_the_whole_chain(self):
        out = self.step("trader-entry", "entry.py", ["check", "RELIANCE", "--setup", "orb", "--now", self.now,
                                                    "--offline", self.off, "--write"])
        self.assertIn("TRIGGERED 9:40 AM at ₹101.45", out)
        self.assertIn("range high ₹101.20", out)
        plan = self.step("trader-exit", "exit.py", ["plan", "--from", "trader/entry.json", "--stop", "or-mid",
                                                   "--target", "1R", "--now", self.now, "--offline", self.off, "--write"])
        self.assertIn("Stop          ₹100.45", plan)
        self.assertIn("Target        ₹102.45", plan)
        self.assertIn("Flat by       15:10 IST", plan)
        with open(os.path.join(self.cwd, "trader", "plan.json")) as fh:
            self.assertEqual(json.load(fh)["symbol"], "RELIANCE")       # the NSE symbol, not RELIANCE.NS
        sized = self.step("trader-budget", "size.py", ["--now", self.now, "--write"])
        self.assertIn("Size: 500 shares of RELIANCE", sized)
        self.assertIn("bound by", sized.lower() + "bound by")
        with open(os.path.join(self.cwd, "trader", "orders.json")) as fh:
            order = json.load(fh)["orders"][0]
        self.assertEqual((order["symbol"], order["side"], order["qty"]), ("RELIANCE", "buy", "500"))
        self.assertEqual(order["stop_loss_stop_price"], "100.45")
        self.assertEqual(order["take_profit_limit_price"], "102.45")
        risk = self.step("trader-risk", "check.py", ["--now", self.now])
        self.assertIn("PASS  #1 buy RELIANCE 500 shares", risk)
        self.assertIn("max loss ₹500 (limit ₹500)", risk)
        shown = self.step("trader-broker", "ticket.py", ["show", "--now", self.now])
        self.assertIn("READY", shown)
        self.assertIn("exchange          NSE", shown)
        self.assertIn("product           MIS", shown)
        self.assertIn("order_type        SL-M", shown)
        self.assertIn("trigger_price     100.45", shown)
        self.assertIn("price             102.45", shown)
        self.assertNotIn("Alpaca", shown)
        j = json.loads(self.step("trader-broker", "ticket.py", ["show", "--index", "1", "--json", "--now", self.now]))
        self.assertEqual(j["kite_form"]["tradingsymbol"], "RELIANCE")
        self.assertEqual(len(j["exit_orders"]), 2)
        self.step("trader-broker", "ticket.py", ["placed", "--index", "1", "--broker-id", "2611060001",
                                                "--filled-qty", "500", "--filled-price", "101.45", "--now", self.now])
        again = self.step("trader-broker", "ticket.py", ["show", "--now", self.now], want=1)
        self.assertIn("DONE: placed", again)
        with open(os.path.join(self.cwd, "trader", "portfolio.json")) as fh:
            pf = json.load(fh)
        self.assertEqual(pf["positions"][0]["shares"], 500)
        self.assertAlmostEqual(pf["cash"], 100000 - 500 * 101.45)
        flat = self.step("trader-broker", "ticket.py", ["flatten", "--symbol", "RELIANCE", "--now", "2026-11-06 15:05"])
        self.assertIn("flat by 15:10 IST", flat)
        self.assertIn("Kite", flat)

    def test_risk_blocks_before_930_after_1500_and_on_a_holiday(self):
        self.step("trader-entry", "entry.py", ["check", "RELIANCE", "--setup", "orb", "--now", self.now,
                                              "--offline", self.off, "--write"])
        self.step("trader-exit", "exit.py", ["plan", "--from", "trader/entry.json", "--now", self.now,
                                            "--offline", self.off, "--write"])
        self.step("trader-budget", "size.py", ["--now", self.now, "--write"])
        for now in ("2026-11-06 09:20", "2026-11-06 15:05", "2026-11-10 10:00"):
            out = self.step("trader-risk", "check.py", ["--now", now], want=1)
            self.assertIn("BLOCK #1", out, now)

    def test_entry_waits_when_nothing_has_closed_above(self):
        out = self.step("trader-entry", "entry.py", ["check", "RELIANCE", "--setup", "orb", "--now", "2026-11-06 09:35",
                                                    "--offline", self.off], want=1)
        self.assertIn("WAITING", out)


class Kite(unittest.TestCase):
    CANDLES = [["2026-11-05T15:25:00+0530", 99.9, 100.2, 99.8, 100.0, 900],
               ["2026-11-06T09:15:00+0530", 100.0, 101.0, 99.8, 100.6, 5000],
               ["2026-11-06T09:20:00+0530", 100.6, 101.2, 100.2, 100.8, 4000]]

    def test_off_by_default_so_nothing_calls_kite(self):
        kf = load("trader-data", "kitefeed")
        os.environ.pop("TRADER_DATA_SOURCE", None)
        self.assertFalse(kf.enabled())
        self.assertIsNone(kf.maybe_get("/v8/finance/chart/RELIANCE.NS?range=1d&interval=5m"))

    def test_candles_become_yahoo_shaped_json(self):
        kf = load("trader-data", "kitefeed")
        doc = json.loads(kf.to_yahoo_json("RELIANCE", self.CANDLES, "5m", datetime.datetime(2026, 11, 6, 4, 0)))
        r = doc["chart"]["result"][0]
        self.assertEqual(r["meta"]["symbol"], "RELIANCE.NS")
        self.assertEqual(r["meta"]["currency"], "INR")
        self.assertEqual(r["meta"]["chartPreviousClose"], 100.0)           # the earlier session's last close
        self.assertEqual(r["meta"]["regularMarketVolume"], 9000)
        self.assertEqual(len(r["timestamp"]), 3)
        self.assertEqual(r["timestamp"][1], _synth.ts(D(2026, 11, 6), "09:15"))
        self.assertEqual(r["indicators"]["quote"][0]["high"], [100.2, 101.0, 101.2])

    def test_the_entry_parser_reads_it_unchanged(self):
        kf, entry = load("trader-data", "kitefeed"), load("trader-entry", "entry")
        text = kf.to_yahoo_json("RELIANCE", self.CANDLES, "5m", datetime.datetime(2026, 11, 6, 4, 0))
        ch = entry.parse_chart(text, "RELIANCE")
        self.assertEqual(ch["symbol"], "RELIANCE")
        self.assertEqual(ch["prev_close"], 100.0)

    def test_instruments_csv_and_missing_credentials(self):
        kf = load("trader-data", "kitefeed")
        text = ("instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,"
                "instrument_type,segment,exchange\n738561,2885,RELIANCE,RELIANCE INDUSTRIES,0,,0,0.05,1,EQ,NSE,NSE\n"
                "256265,1001,NIFTY 50,NIFTY 50,0,,0,0,1,EQ,INDICES,NSE\n")
        self.assertEqual(kf.parse_instruments(text), {"RELIANCE": 738561})
        os.environ.pop("KITE_API_KEY", None)
        os.environ.pop("KITE_ACCESS_TOKEN", None)
        with self.assertRaises(kf.KiteError):
            kf.chart("RELIANCE", "1d", "5m")

    def test_only_single_symbol_charts_are_answered(self):
        kf = load("trader-data", "kitefeed")
        os.environ["TRADER_DATA_SOURCE"] = "kite"
        try:
            self.assertIsNone(kf.maybe_get("/v7/finance/spark?symbols=TCS.NS&range=1d&interval=5m"))
        finally:
            os.environ.pop("TRADER_DATA_SOURCE", None)


class News(unittest.TestCase):
    def run_news(self, *extra):
        news = load("trader-news", "news")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = news.main(["--offline", os.path.join(FIX, "trader-news"), "--now", "2026-11-06 16:00", "--all",
                            "--no-chart", "--json"] + list(extra))
        return rc, json.loads(buf.getvalue())

    def test_results_are_matched_to_symbols_and_timed_against_the_session(self):
        rc, doc = self.run_news("--tickers", "SIEMENS", "KIOCL")
        self.assertEqual(rc, 0)
        by = {r["symbol"]: r for r in doc["results"]}
        self.assertEqual(set(by), {"SIEMENS", "KIOCL"})
        self.assertEqual(by["SIEMENS"]["when"], "after the close")      # filed 15:48, the session ends 15:30
        self.assertTrue(by["SIEMENS"]["link"].startswith("https://nsearchives.nseindia.com/"))

    def test_upcoming_board_meeting_for_results(self):
        rc, doc = self.run_news("--tickers", "ITDC", "--days", "10")
        up = doc["upcoming"]
        self.assertEqual([(u["symbol"], u["meeting"], u["days"], u["results"]) for u in up],
                         [("ITDC", "2026-11-12", 6, True)])

    def test_late_filings_are_marked_and_a_second_run_shows_nothing_new(self):
        news = load("trader-news", "news")
        facts = news.result_facts("RELATING TO:First Quarter |AUDITED/UNAUDITED:Unaudited |CUMULATIVE/NON-CUMULATIVE:Non-Cumulative "
                                  "|CONSOLIDATED/NON-CONSOLIDATED:Non-Consolidated |IND AS/ NON IND AS:Ind-AS New |PERIOD:Quarterly "
                                  "|PERIOD ENDED: 30-Jun-2024")
        self.assertEqual(facts["period_ended"], D(2024, 6, 30))
        self.assertEqual(facts["basis"], "Non-Consolidated")
        self.assertEqual(news.session_word(datetime.datetime(2026, 11, 6, 9, 0)), "before the open")
        self.assertEqual(news.session_word(datetime.datetime(2026, 11, 6, 12, 0)), "during the session")
        self.assertEqual(news.session_word(datetime.datetime(2026, 11, 7, 12, 0)), "on a weekend")

    def test_name_matching_handles_ampersands_and_suffixes(self):
        news = load("trader-news", "news")
        self.assertEqual(news.norm_name("Mahindra & Mahindra Limited"), news.norm_name("MAHINDRA AND MAHINDRA LTD"))

    def test_nothing_to_watch_is_an_error(self):
        news = load("trader-news", "news")
        with tempfile.TemporaryDirectory() as d:
            rc = news.main(["--offline", os.path.join(FIX, "trader-news"), "--watchlist", os.path.join(d, "none.json"),
                            "--plan", os.path.join(d, "none.json"), "--portfolio", os.path.join(d, "none.json")])
        self.assertEqual(rc, 1)


class Analyst(unittest.TestCase):
    def setUp(self):
        self.facts = load("trader-analyst", "facts")
        with open(os.path.join(FIX, "trader-analyst", "TCS.json")) as fh:
            self.q, self.cur = self.facts.parse(fh.read(), "TCS")

    def test_quarters_growth_and_gaps(self):
        self.assertEqual(self.cur, "INR")
        rows, ttm, gaps = self.facts.analyse(self.q, 6)
        by = {r["period_end"]: r for r in rows}
        self.assertEqual(by["2026-06-30"]["revenue"], 72275.0)
        self.assertAlmostEqual(by["2026-06-30"]["revenue_yoy"], (72275 / 63437 - 1) * 100, places=6)
        self.assertIsNone(by["2026-03-31"]["revenue_yoy"])          # no year-ago quarter: blank, never invented
        self.assertEqual(gaps, [("2025-06-30", "2025-12-31")])      # Yahoo skips a quarter: reported, not filled
        self.assertEqual(ttm["through"], "2026-09-30")
        self.assertEqual(ttm["revenue"], round((67087 + 70698 + 72275 + 73188), 2))

    def test_foreign_currency_is_labelled_not_converted(self):
        text = json.dumps({"timeseries": {"result": [{"quarterlyTotalRevenue": [
            {"asOfDate": "2026-09-30", "periodType": "3M", "currencyCode": "USD", "reportedValue": {"raw": 5.145e9}}]}]}})
        q, cur = self.facts.parse(text, "INFY")
        self.assertEqual(cur, "USD")

    def test_no_data_is_an_error(self):
        with self.assertRaises(self.facts.FactsError):
            self.facts.parse(json.dumps({"timeseries": {"result": []}}), "ZZZ")


class Deals(unittest.TestCase):
    def test_bulk_and_block_files(self):
        deals = load("trader-deals", "deals")
        rows = []
        for kind in ("bulk", "block"):
            with open(os.path.join(FIX, "trader-deals", kind + ".csv")) as fh:
                rows += deals.parse(fh.read(), kind)
        rel = [r for r in rows if r["symbol"] == "RELIANCE"]       # the block rows are made-up samples
        self.assertEqual(sum(r["value_cr"] for r in rel if r["side"] == "BUY"), round(1200000 * 1318.5 / 1e7, 2))
        net = {n["symbol"]: n for n in deals.net_by_symbol(rows)}
        self.assertAlmostEqual(net["RELIANCE"]["net_cr"], 158.22 - 52.76, places=2)

    def test_no_records_is_a_quiet_day_not_an_error(self):
        deals = load("trader-deals", "deals")
        text = "Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price\nNO RECORDS,,,,,,\n"
        self.assertEqual(deals.parse(text, "block"), [])


class Alerts(unittest.TestCase):
    def test_yahoo_url_and_quote(self):
        alerts = load("trader-alerts", "alerts")
        self.assertIn("M%26M.NS", alerts.yahoo_url("M&M"))
        q = alerts.parse_yahoo(_synth.chart("RELIANCE.NS", {D(2026, 11, 6): _synth.orb_day(D(2026, 11, 6))}), "RELIANCE")
        self.assertEqual(q["symbol"], "RELIANCE")
        self.assertEqual(q["currency"], "INR")
        self.assertEqual(q["prev_close"], 100.0)

    def test_the_clock_knows_the_nse(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, _ = run("trader-alerts", "alerts.py", ["clock", "--now", "2026-11-10 10:53"], d)
            self.assertIn("NSE holiday: Diwali-Balipratipada", out)
            self.assertIn("Next open: 2026-11-11 09:15 IST", out)
            rc, out, _ = run("trader-alerts", "alerts.py", ["clock", "--now", "2026-11-06 10:53"], d)
            self.assertIn("NSE OPEN", out)
            self.assertIn("09:15 to 15:30", out)


class Engines(unittest.TestCase):
    """The Time Machine and the scanner on the made-up session."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        hol = load("trader-entry", "entry").NSE_HOLIDAYS
        days, d = {}, D(2026, 10, 1)
        while d <= D(2026, 11, 6):
            if d.weekday() < 5 and d.isoformat() not in hol:
                days[d] = _synth.orb_day(d)
            d += datetime.timedelta(days=1)
        self.days = days
        self.file = os.path.join(self.tmp.name, "RELIANCE.json")
        with open(self.file, "w") as fh:
            fh.write(_synth.chart("RELIANCE.NS", days))

    def tearDown(self):
        self.tmp.cleanup()

    def test_timemachine_replays_full_sessions_and_is_repeatable(self):
        args = ["run", "--symbol", "RELIANCE", "--date", "2026-11-06", "--entry", "101.45", "--stop", "100.45",
                "--target", "102.45", "--entry-time", "9:40 AM", "--offline", self.file, "--until", "15:10",
                "--now", "2026-11-06 16:00"]
        rc, out, err = run("trader-timemachine", "timemachine.py", args, self.tmp.name)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("10,000 replays", out)
        self.assertIn("full sessions", out)
        rc2, out2, _ = run("trader-timemachine", "timemachine.py", args, self.tmp.name)
        self.assertEqual(out, out2)                                  # same seed, same numbers

    def test_the_session_is_72_bars_because_yahoo_lacks_the_last_two(self):
        tm = load("trader-timemachine", "timemachine")
        self.assertEqual(tm.SESSION_BARS, 72)
        self.assertEqual(tm.OPEN_MIN, 9 * 60 + 15)
        self.assertEqual(tm.OPEN_MIN + tm.SESSION_BARS * 5, 15 * 60 + 15)

    def test_orb_scan_finds_the_breakout_at_9_40(self):
        with open(self.file, "w") as fh:
            fh.write(_synth.chart("RELIANCE.NS", {D(2026, 11, 6): self.days[D(2026, 11, 6)]}))
        rc, out, err = run("trader-scanner", "scan.py", ["orb", "--offline", self.file, "--now", "2026-11-06 10:15",
                                                        "--min-price", "0", "--no-write"], self.tmp.name)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("9:40 AM  RELIANCE", out)
        self.assertIn("range 99.70 to 101.20", out)


if __name__ == "__main__":
    unittest.main()
