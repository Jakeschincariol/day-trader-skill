"""India mode ("market": "IN" in trader/config.json, or TRADER_MARKET=IN): the NSE clock,
the NSE holiday list, flat by 15:15, and .NS symbols left as they are."""
import datetime
import os
import unittest

from _load import load

DT = datetime.datetime
TOOLS = [("trader-alerts", "alerts"), ("trader-entry", "entry"), ("trader-exit", "exit"),
         ("trader-budget", "size"), ("trader-broker", "ticket"), ("trader-risk", "check"),
         ("trader-scanner", "scan"), ("trader-timemachine", "timemachine"), ("trader-news", "news")]


def india(folder, name):
    os.environ["TRADER_MARKET"] = "IN"
    try:
        return load(folder, name)
    finally:
        os.environ["TRADER_MARKET"] = "US"


class India(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = {name: india(folder, name) for folder, name in TOOLS}

    def test_every_tool_is_on_india_time(self):
        utc = DT(2026, 11, 11, 3, 45)                      # 9:15 in India, all year (no daylight saving)
        for name, mod in self.m.items():
            self.assertEqual(mod.MARKET, "IN", name)
            self.assertEqual(mod.to_eastern(utc), DT(2026, 11, 11, 9, 15), name)
            self.assertEqual(mod.to_eastern(DT(2026, 6, 1, 3, 45)), DT(2026, 6, 1, 9, 15), name)
            if hasattr(mod, "eastern_to_utc"):
                self.assertEqual(mod.eastern_to_utc(DT(2026, 11, 11, 9, 15)), utc, name)

    def test_the_us_market_is_still_the_default(self):
        us = load("trader-alerts", "alerts")
        self.assertEqual((us.MARKET, us.OPEN, us.CLOSE), ("US", datetime.time(9, 30), datetime.time(16, 0)))

    def test_session_is_9_15_to_15_30_with_no_early_close(self):
        for name in ("alerts", "entry", "exit", "scan"):
            mod = self.m[name]
            self.assertEqual(mod.session(datetime.date(2026, 11, 11)),
                             (datetime.time(9, 15), datetime.time(15, 30)), name)
            self.assertEqual(mod.NYSE_EARLY_CLOSE, {}, name)
        a = self.m["alerts"]
        ist = a.eastern_to_utc
        self.assertFalse(a.market_status(ist(DT(2026, 11, 11, 9, 14)))["open"])
        self.assertTrue(a.market_status(ist(DT(2026, 11, 11, 9, 15)))["open"])
        self.assertTrue(a.market_status(ist(DT(2026, 11, 11, 15, 29)))["open"])
        after = a.market_status(ist(DT(2026, 11, 11, 15, 30)))
        self.assertEqual((after["open"], after["next_open"]), (False, "2026-11-12 09:15"))

    def test_nse_holidays(self):
        for name in ("alerts", "entry", "exit", "check", "scan"):
            mod = self.m[name]
            self.assertEqual(len(mod.NSE_HOLIDAYS), 16, name)
            self.assertIs(mod.NYSE_HOLIDAYS, mod.NSE_HOLIDAYS, name)
            for d in mod.NSE_HOLIDAYS:
                self.assertLess(datetime.date.fromisoformat(d).weekday(), 5, d)
        a = self.m["alerts"]
        self.assertEqual(a.trading_day(datetime.date(2026, 11, 10)), (False, "NYSE holiday: Diwali Balipratipada"))
        self.assertEqual(a.trading_day(datetime.date(2026, 1, 26))[0], False)       # Republic Day
        self.assertEqual(a.trading_day(datetime.date(2026, 11, 26)), (True, ""))    # Thanksgiving: the NSE trades
        st = a.market_status(a.eastern_to_utc(DT(2026, 11, 9, 16, 0)))
        self.assertEqual(st["next_open"], "2026-11-11 09:15")                       # over the Diwali holiday

    def test_day_trades_are_flat_by_15_15(self):
        self.assertEqual(self.m["exit"].DEFAULTS["flat_by"], "15:15")
        self.assertEqual(self.m["size"].DEFAULTS["flat_by"], "15:15")
        self.assertEqual(self.m["check"].DEFAULTS["flat_by"], "15:15")
        self.assertEqual((self.m["alerts"].FLAT_BY, self.m["ticket"].FLAT_BY), ("15:15", "15:15"))
        ex = self.m["exit"]
        self.assertEqual(ex.resolve_flat_by(datetime.date(2026, 11, 11), None, {}, datetime.time(9, 35)), ("15:15", ""))
        rules = self.m["alerts"].rules_from_plan({"symbol": "RELIANCE.NS", "stop": 1335.75, "target": 1356.9})
        self.assertEqual((rules[2]["at"], rules[2]["symbol"]), ("15:15", "RELIANCE.NS"))
        for name in ("entry", "size", "check"):
            d = self.m[name].DEFAULTS
            self.assertEqual((d["no_entries_before"], d["no_entries_after"]), ("09:30", "15:00"), name)

    def test_ns_symbols_stay_as_they_are(self):
        for sym in ("RELIANCE.NS", "BAJAJ-AUTO.NS", "M&M.NS"):
            for name, mod in self.m.items():
                self.assertEqual(mod._ysym(sym), sym, name)
            self.assertTrue(self.m["check"].TICKER.match(sym), sym)
            self.assertIn("/" + sym + "?", self.m["alerts"].yahoo_url(sym))
            self.assertEqual(self.m["entry"].yahoo_symbol(sym), sym)
            self.assertEqual(self.m["scan"].to_yahoo(sym), sym)
            self.assertEqual(self.m["news"].yahoo_symbol(sym), sym)
        self.assertEqual(self.m["entry"].yahoo_symbol("BRK.B"), "BRK-B")             # US class shares as before
        us = load("trader-scanner", "scan")
        self.assertEqual((us.to_yahoo("reliance.ns"), us.to_yahoo("BRK.B")), ("RELIANCE.NS", "BRK-B"))
        plan = self.m["timemachine"].normalize_plan({
            "symbol": "BAJAJ-AUTO.NS", "date": "2026-11-11", "entry": 11092.0, "stop": 11022.0,
            "target": 11232.0, "entry_time": "9:40 AM"})
        self.assertEqual((plan["symbol"], plan["entry_bar"]), ("BAJAJ-AUTO.NS", 4))

    def test_time_machine_replays_9_15_to_15_15(self):
        tm = self.m["timemachine"]
        self.assertEqual((tm.SESSION_BARS, tm.clock24(tm.OPEN_MIN), tm.clock24(tm.CLOSE_MIN)), (72, "09:15", "15:15"))
        start = 1794368700                                   # 2026-11-11 09:15 in India
        stamps = [start + 300 * i for i in range(75)]
        col = [100.0] * 75
        res = {"meta": {}, "timestamp": stamps,
               "indicators": {"quote": [{"open": col, "high": col, "low": col, "close": col, "volume": [1] * 75}]}}
        _, bars, dropped = tm.parse_bars(res, DT(2026, 11, 12))
        self.assertEqual((len(bars), bars[0]["start"], bars[-1]["start"], dropped["outside_hours"]),
                         (72, "09:15", "15:10", 3))

    def test_printed_text_says_ist_nse_and_rupees(self):
        out = []

        class Sink(object):
            def write(self, text):
                out.append(text)

        self.m["alerts"]._Say(Sink()).write("NYSE OPEN (10:15 New York). Stop $1,335.75, flat by 15:15 ET.")
        self.assertEqual(out, ["NSE OPEN (10:15 IST). Stop ₹1,335.75, flat by 15:15 IST."])
        self.assertEqual(self.m["ticket"].ny_iso(DT(2026, 11, 11, 3, 45)), "2026-11-11T09:15:00+05:30")


if __name__ == "__main__":
    unittest.main()
