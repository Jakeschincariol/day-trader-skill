import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date

import _load

alerts = _load.load("swing-alerts", "alerts")
POS = {"id": "TCS-2026-11-19", "symbol": "TCS", "exchange": "NSE", "qty": 29, "entry": 3412.40,
       "entry_date": "2026-11-19", "stop": 3296.10, "gtt_stop_limit": 3263.10, "target": 3645.00,
       "time_stop_date": "2026-12-10", "setup": "breakout_20d"}


def bar(d, o, h, l, c):
    return {"d": d, "o": o, "h": h, "l": l, "c": c, "v": 1}


def kinds(got):
    return sorted(a["kind"] for a in got)


class Daily(unittest.TestCase):
    def test_quiet_day(self):
        got = alerts.daily_alerts(POS, bar("2026-11-20", 3420, 3450, 3400, 3440), 3412, date(2026, 11, 20), [], [], "-", "-")
        self.assertEqual(got, [])

    def test_gap_through_and_gtt_limit(self):
        got = alerts.daily_alerts(POS, bar("2026-11-20", 3250, 3260, 3200, 3240), 3400, date(2026, 11, 20), [], [], "-", "-")
        self.assertEqual(kinds(got), ["below_gtt_limit", "gap_through", "stop_touched"])
        self.assertIn("may not have filled", [a for a in got if a["kind"] == "below_gtt_limit"][0]["message"])
        self.assertEqual(got[0]["id"].split(":")[0], "TCS")

    def test_target(self):
        got = alerts.daily_alerts(POS, bar("2026-11-20", 3500, 3650, 3490, 3600), 3500, date(2026, 11, 20), [], [], "-", "-")
        self.assertEqual(kinds(got), ["target_touched"])

    def test_time_stop(self):
        got = alerts.daily_alerts(POS, bar("2026-12-10", 3420, 3450, 3400, 3440), 3420, date(2026, 12, 10), [], [], "-", "-")
        self.assertEqual(kinds(got), ["time_stop"])

    def test_results_tomorrow(self):
        got = alerts.daily_alerts(POS, bar("2026-11-23", 3420, 3450, 3400, 3440), 3420, date(2026, 11, 23),
                                  ["2026-11-25"], [], "-", "-")        # 24th is a holiday: the 25th is tomorrow
        self.assertEqual(kinds(got), ["results_tomorrow"])

    def test_ex_date_tomorrow(self):
        got = alerts.daily_alerts(POS, bar("2026-11-20", 3420, 3450, 3400, 3440), 3420, date(2026, 11, 20), [],
                                  [{"ex_date": "2026-11-23", "purpose": "Bonus 1:1"}], "-", "-")
        self.assertEqual(kinds(got), ["ex_date_tomorrow"])
        self.assertIn("Bonus 1:1", got[0]["message"])

    def test_band_changed(self):
        got = alerts.daily_alerts(POS, bar("2026-11-20", 3420, 3450, 3400, 3440), 3420, date(2026, 11, 20), [], [], "10", "-")
        self.assertEqual(kinds(got), ["band_changed"])


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "positions.json"), "w") as fh:
            json.dump({"positions": [dict(POS, stop=2390.0, gtt_stop_limit=2366.10, target=2700.0,
                                          entry=2420.0, time_stop_date="2026-11-18")]}, fh)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def cli(self, args, now="2026-11-18 16:00"):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = alerts.main(args + ["--dir", self.tmp, "--offline", _load.INDIA_FIX, "--now", now])
        return code, buf.getvalue()

    def test_time_stop_rings_once(self):
        code, out = self.cli(["check"])
        self.assertEqual(code, 0)
        self.assertIn("time stop", out)
        code, out = self.cli(["check"])
        self.assertEqual(code, 1)
        self.assertNotIn("time stop", out)

    def test_check_before_bar_final_uses_previous_day(self):
        code, out = self.cli(["check"], now="2026-11-18 14:00")
        self.assertIn("as of the 2026-11-17 close", out)

    def test_clock_holiday(self):
        code, out = self.cli(["clock"], now="2026-11-24 10:00")
        self.assertIn("CLOSED", out)
        self.assertIn("Guru Nanak Jayanti", out)

    def test_quote_write(self):
        code, out = self.cli(["quote", "TCS", "M&M", "--write"])
        with open(os.path.join(self.tmp, "prices.json")) as fh:
            doc = json.load(fh)
        self.assertEqual(set(doc["prices"]), {"TCS", "M&M"})
        self.assertEqual(doc["prices"]["TCS"]["currency"], "INR")


if __name__ == "__main__":
    unittest.main()
