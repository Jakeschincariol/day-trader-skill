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
tm = bt.tm

TSLA = os.path.join(FIX, "trader-timemachine", "TSLA-60d5m.json.gz")
NOW = "2026-10-19 10:50"


class Backtest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        shutil.copy(TSLA, os.path.join(self.d, "TSLA.json.gz"))
        with open(os.path.join(self.d, "symbols.json"), "w") as fh:
            json.dump({"symbols": ["TSLA", "MISSING"], "source": "test"}, fh)

    def tearDown(self):
        shutil.rmtree(self.d)

    def run_json(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = bt.main(["run", "--cache", self.d, "--now", NOW, "--json", "--draws", "200"] + list(extra))
        self.assertEqual(code, 0, err.getvalue())
        return json.loads(out.getvalue())

    def test_the_trades_are_the_time_machines_history(self):
        doc = self.run_json("--until", "16:00")
        self.assertEqual((doc["stocks"], doc["until"]), (1, "16:00"))
        old = [v for v in doc["variants"] if v["label"].endswith("(old)")][0]
        self.assertEqual(old["trades"], 33)   # the reel's 33, every one with a blind control
        self.assertAlmostEqual(old["avg_R"], -0.062, places=3)
        new = doc["variants"][0]
        self.assertEqual((new["label"], new["trades"]), ("1R, next open, 2 bps", 33))
        self.assertAlmostEqual(new["avg_R"], -0.113, places=3)
        for v in doc["variants"]:
            self.assertLessEqual(v["R_ci"][0], v["avg_R"])
            self.assertLessEqual(v["avg_R"], v["R_ci"][1])
            self.assertAlmostEqual(v["edge_R"], v["avg_R"] - v["control_R"], places=9)
            self.assertEqual(v["first_half"]["trades"] + v["second_half"]["trades"], v["trades"])

    def test_the_text_report_and_the_universe_file(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(bt.main(["run", "--cache", self.d, "--now", NOW, "--draws", "100"]), 0)
        text = out.getvalue()
        for line in ("on 1 S&P 500 stocks", "resampling whole days", "breakout adds", "not a verdict"):
            self.assertIn(line, text)
        path = os.path.join(self.d, "list.csv")
        with open(path, "w") as fh:
            fh.write("Symbol,Security\nAAPL,Apple\n\"brk.b\",Berkshire\nAAPL,again\n")
        self.assertEqual(bt.universe(path)[0], ["AAPL", "BRK.B"])

    def test_an_empty_cache_is_one_plain_line(self):
        os.remove(os.path.join(self.d, "TSLA.json.gz"))
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            self.assertEqual(bt.main(["run", "--cache", self.d, "--now", NOW]), 1)
        self.assertIn("run backtest.py fetch first", err.getvalue())


if __name__ == "__main__":
    unittest.main()
