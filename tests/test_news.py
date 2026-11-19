import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import _load

news = _load.load("swing-news", "news")


def read(name):
    with open(os.path.join(_load.INDIA_FIX, name), "rb") as fh:
        return fh.read()


class Parse(unittest.TestCase):
    def test_parses_both_feeds(self):
        y = news.parse_rss(read("rss-yahoo-TCS.NS.xml"), "yahoo")
        g = news.parse_rss(read("rss-google-TCS.NS.xml"), "google")
        self.assertEqual(len(y), 13)
        self.assertEqual(len(g), 30)
        for it in y + g:
            self.assertEqual(set(it), {"time_ist", "source", "publisher", "title", "url"})
        self.assertFalse(any(it["title"].endswith(" - Livemint") for it in g))
        self.assertTrue(any(it["publisher"] == "Livemint" for it in g))

    def test_times_in_ist(self):
        self.assertEqual(news.to_ist("Wed, 18 Nov 2026 11:06:31 GMT"), "2026-11-18 16:36")
        self.assertEqual(news.to_ist("Mon, 16 Nov 2026 15:35:00 +0000"), "2026-11-16 21:05")

    def test_dedupes_same_headline_across_sources(self):
        a = {"time_ist": "2026-11-18 10:00", "source": "yahoo", "publisher": "", "title": "TCS Q2 results beat", "url": "u1"}
        b = dict(a, source="google", publisher="Mint", title="TCS Q2 Results Beat!", url="u2", time_ist="2026-11-18 10:05")
        self.assertEqual(len(news.dedupe([a, b])), 1)

    def test_tags_results_and_regulatory(self):
        self.assertIn("results", news.tags("TCS Q2 results: net profit up 8%"))
        self.assertIn("regulatory", news.tags("SEBI imposes penalty on promoter"))
        self.assertIn("order win", news.tags("L&T bags large order from NHAI"))
        self.assertIn("dividend", news.tags("Board recommends final dividend of Rs 24"))
        self.assertEqual(news.tags("Company to hold investor meet"), [])
        self.assertNotIn("results", news.tags("Stock Markets Today: Sensex, Nifty Down on Profit-taking"))
        self.assertIn("results", news.tags("Infosys profit rises 12% in Q2"))


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def cli(self, args, offline=_load.INDIA_FIX):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = news.main(args + ["--dir", self.tmp, "--offline", offline, "--now", "2026-11-19 09:00"])
        return code, buf.getvalue(), err.getvalue()

    def test_seen_items_not_repeated(self):
        code, out, _ = self.cli(["--tickers", "TCS", "--hours", "72", "--json"])
        first = json.loads(out)
        self.assertGreater(len(first["items"]), 3)
        self.assertTrue(all(i["time_ist"] >= "2026-11-16 09:00" for i in first["items"]))
        code, out, _ = self.cli(["--tickers", "TCS", "--hours", "72", "--json"])
        self.assertEqual(json.loads(out)["items"], [])
        code, out, _ = self.cli(["--tickers", "TCS", "--hours", "72", "--json", "--all"])
        self.assertEqual(len(json.loads(out)["items"]), len(first["items"]))

    def test_move_vs_previous_close(self):
        code, out, _ = self.cli(["--tickers", "TCS", "--json"])
        m = json.loads(out)["moves"]["TCS"]
        self.assertEqual(m["date"], "2026-11-18")
        self.assertIn("pct", m)

    def test_news_runs_without_nse(self):
        off = os.path.join(self.tmp, "offline")
        os.makedirs(off)
        for name in os.listdir(_load.INDIA_FIX):
            if name != "nse":
                shutil.copy(os.path.join(_load.INDIA_FIX, name), off)
        with mock.patch.dict(sys.modules, {"nse": None}):
            code, out, err = self.cli(["--tickers", "TCS", "--hours", "72"], offline=off)
        self.assertEqual(code, 0)
        self.assertEqual(err.count("NSE data off"), 1)
        self.assertIn("TCS", out)


if __name__ == "__main__":
    unittest.main()
