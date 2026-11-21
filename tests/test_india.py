import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from _load import FIX, ROOT, load

scanner = load("trader-scanner", "scan")
entry = load("trader-entry", "entry")
risk = load("trader-risk", "check")
news = load("trader-news", "news")
analyst = load("trader-analyst", "facts")
pelosi = load("trader-pelosi", "ptr")
tm = load("trader-timemachine", "timemachine")


class IndiaSymbols(unittest.TestCase):
    def test_nse_and_bse_suffixes_are_preserved_for_yahoo(self):
        self.assertEqual(scanner.to_yahoo("RELIANCE.NS"), "RELIANCE.NS")
        self.assertEqual(scanner.to_yahoo("TCS.BO"), "TCS.BO")
        self.assertEqual(entry.yahoo_symbol("RELIANCE.NS"), "RELIANCE.NS")
        self.assertEqual(tm.chart_url("TCS.BO", "query2").split("/")[-1],
                         "TCS.BO?range=60d&interval=5m")

    def test_indian_symbol_validation_accepts_exchange_suffix(self):
        self.assertIsNotNone(scanner.TICKER.match("RELIANCE.NS"))
        self.assertIsNotNone(scanner.TICKER.match("TCS.BO"))
        self.assertIsNotNone(risk.TICKER.match("RELIANCE.NS"))


class IndiaNews(unittest.TestCase):
    def test_news_is_global_and_accepts_indian_region(self):
        url = news.yahoo_rss_url("RELIANCE.NS", "IN", "en-IN")
        self.assertIn("region=IN", url)
        self.assertIn("lang=en-IN", url)
        self.assertIn("RELIANCE.NS", url)


class IndiaDisabledUsModules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = os.path.join(self.tmp.name, "config.json")
        with open(self.cfg, "w", encoding="utf-8") as fh:
            json.dump({"market": "india", "currency": "INR", "timezone": "Asia/Kolkata"}, fh)

    def tearDown(self):
        self.tmp.cleanup()

    def test_analyst_refuses_sec_analysis_for_india(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = analyst.main(["RELIANCE.NS", "--config", self.cfg])
        self.assertEqual(code, 2)
        self.assertIn("US-only", err.getvalue())

    def test_pelosi_refuses_us_congress_tracking_for_india(self):
        old = os.getcwd()
        try:
            os.chdir(self.tmp.name)
            with open("trader", ""):
                pass
        except Exception:
            pass
        finally:
            os.chdir(old)
        os.makedirs(os.path.join(self.tmp.name, "trader"), exist_ok=True)
        with open(os.path.join(self.tmp.name, "trader", "config.json"), "w", encoding="utf-8") as fh:
            json.dump({"market": "india"}, fh)
        out, err = io.StringIO(), io.StringIO()
        old = os.getcwd()
        os.chdir(self.tmp.name)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = pelosi.main(["index"])
        finally:
            os.chdir(old)
        self.assertEqual(code, 2)
        self.assertIn("Congress tracking is US-only", err.getvalue())


class IndiaCalendar(unittest.TestCase):
    def test_india_profile_has_nse_hours_and_holiday(self):
        profile = load("trader-budget", "market_profile")
        cfg = dict(profile.INDIA)
        day = __import__("datetime").date(2026, 1, 26)
        ok, reason = profile.trading_day(day, cfg)
        self.assertFalse(ok)
        self.assertIn("Republic Day", reason)
        self.assertIsNone(profile.session(day, cfg))

    def test_regular_nse_hours(self):
        profile = load("trader-budget", "market_profile")
        cfg = dict(profile.INDIA)
        day = __import__("datetime").date(2026, 10, 19)
        session = profile.session(day, cfg)
        self.assertEqual(str(session[0]), "09:15:00")
        self.assertEqual(str(session[1]), "15:30:00")


class IndiaFixtures(unittest.TestCase):
    def test_reliance_fixture_is_inr_and_uses_nse_suffix(self):
        path = os.path.join(FIX, "trader-india", "RELIANCE.NS.json")
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        meta = doc["chart"]["result"][0]["meta"]
        self.assertEqual(meta["symbol"], "RELIANCE.NS")
        self.assertEqual(meta["currency"], "INR")

    def test_tcs_fixture_is_inr_and_uses_bse_suffix(self):
        path = os.path.join(FIX, "trader-india", "TCS.BO.json")
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        meta = doc["chart"]["result"][0]["meta"]
        self.assertEqual(meta["symbol"], "TCS.BO")
        self.assertEqual(meta["currency"], "INR")


if __name__ == "__main__":
    unittest.main()
