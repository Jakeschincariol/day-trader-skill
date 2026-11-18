import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

import _load
from india import market, nse_source

NSE_FIX = os.path.join(_load.INDIA_FIX, "nse")


def sample(name):
    with open(os.path.join(NSE_FIX, name + ".json")) as fh:
        return json.load(fh)


class FakeNSE:
    calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def holidays(self, type="trading"):
        FakeNSE.calls += 1
        return sample("holidays")

    def board_meetings(self, index="equities", symbol=None, fno=False, from_date=None, to_date=None):
        FakeNSE.calls += 1
        rows = sample("board_meetings")
        return [dict(r, bm_symbol=symbol or r["bm_symbol"]) for r in rows] + [
            {"bm_symbol": symbol, "bm_date": "05-Dec-2026", "bm_purpose": "Fund raising by QIP", "bm_desc": "Fund Raising"}]

    def actions(self, segment="equities", symbol=None, from_date=None, to_date=None):
        FakeNSE.calls += 1
        return [dict(r, symbol=symbol or r["symbol"]) for r in sample("actions")]

    def announcements(self, index="equities", symbol=None, fno=False, from_date=None, to_date=None):
        FakeNSE.calls += 1
        return sample("announcements")


class BrokenNSE(FakeNSE):
    def __enter__(self):
        raise RuntimeError("401 from NSE")


class NseSource(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        FakeNSE.calls = 0

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_missing_package_is_soft(self):
        with mock.patch.dict(sys.modules, {"nse": None}):
            src = nse_source.NseSource(self.tmp)
        self.assertFalse(src.available)
        self.assertEqual(src.results_dates(["TCS"], date(2026, 11, 1), date(2026, 12, 31)), {})
        self.assertIn("pip install", nse_source.soft_notice(src))

    def test_results_dates_filters_purpose(self):
        src = nse_source.NseSource(self.tmp, client_factory=FakeNSE)
        out = src.results_dates(["TCS"], date(2023, 1, 1), date(2026, 12, 31))
        self.assertEqual(out, {"TCS": ["2023-10-30"]})          # the QIP meeting is not results
        self.assertIsNone(nse_source.soft_notice(src))

    def test_corporate_actions(self):
        src = nse_source.NseSource(self.tmp, client_factory=FakeNSE)
        out = src.corporate_actions(["IDEA"], date(2023, 1, 1), date(2026, 12, 31))
        self.assertEqual(out["IDEA"][0], {"ex_date": "2023-10-17", "purpose": "Bonus 2:1"})

    def test_announcements(self):
        src = nse_source.NseSource(self.tmp, client_factory=FakeNSE)
        a = src.announcements("IDEA", date(2023, 1, 1), date(2026, 12, 31))[0]
        self.assertEqual(a["time_ist"], "2023-10-18 22:11")
        self.assertTrue(a["url"].startswith("https://nsearchives.nseindia.com/"))
        self.assertEqual(set(a), {"time_ist", "subject", "text", "url"})

    def test_cached_second_call(self):
        src = nse_source.NseSource(self.tmp, client_factory=FakeNSE)
        src.trading_holidays()
        src.trading_holidays()
        self.assertEqual(FakeNSE.calls, 1)

    def test_client_error_returns_empty(self):
        src = nse_source.NseSource(self.tmp, client_factory=BrokenNSE)
        self.assertEqual(src.trading_holidays(), {})
        self.assertIn("401", src.last_error)

    def test_refresh_holidays_writes_file(self):
        path = os.path.join(self.tmp, "holidays.json")
        n = market.refresh_holidays(nse_source.NseSource(self.tmp, client_factory=FakeNSE), path=path)
        self.assertEqual(n, 1)          # the package sample lists one CM holiday
        with open(path) as fh:
            years = json.load(fh)["years"]
        self.assertEqual(years["2023"]["2023-01-26"], "Republic Day")


if __name__ == "__main__":
    unittest.main()
