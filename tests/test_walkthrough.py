"""The README walkthrough, end to end on the offline fixtures: RELIANCE, 17 November 2026."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import _load

entry = _load.load("swing-entry", "entry")
exit_ = _load.load("swing-exit", "exit")
tm = _load.load("swing-timemachine", "timemachine")
size = _load.load("swing-budget", "size")
risk = _load.load("swing-risk", "check")
card = _load.load("swing-card", "card")


class Walkthrough(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_tool(self, mod, args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = mod.main(args + ["--dir", self.tmp, "--offline", _load.INDIA_FIX, "--now", "2026-11-17 16:00"])
        self.assertEqual(code, 0, buf.getvalue())
        return buf.getvalue()

    def read(self, name):
        with open(os.path.join(self.tmp, name)) as fh:
            return json.load(fh)

    def test_readme_numbers(self):
        self.run_tool(entry, ["check", "RELIANCE", "--setup", "breakout_20d", "--write"])
        e = self.read("entry.json")
        self.assertEqual((e["state"], e["trigger_close"], e["level"], e["order"]["price"]),
                         ("triggered", 1367.0, 1344.8, 1373.9))
        self.run_tool(exit_, ["plan", "--write"])
        p = self.read("plan.json")
        self.assertEqual((p["stop"], p["gtt_stop_limit"], p["target"], p["time_stop_date"]),
                         (1282.0, 1269.1, 1557.7, "2026-12-10"))
        self.run_tool(tm, ["run", "--write"])
        t = self.read("timemachine.json")
        self.assertEqual((round(t["sim"]["target_pct"], 1), round(t["sim"]["stop_pct"], 1),
                          round(t["sim"]["time_pct"], 1)), (2.8, 16.9, 80.3))
        self.assertEqual((t["history"]["fired"], t["history"]["target"], t["history"]["stop"]), (141, 6, 30))
        self.assertEqual(t["verdict"], "close to a coin flip")
        self.run_tool(size, ["--write"])
        o = self.read("orders.json")["proposals"][0]
        self.assertEqual((o["qty"], o["cost"], o["risk_at_stop"]), (54, 74190.6, 4962.6))
        out = self.run_tool(risk, [])
        self.assertIn("PASS  RELIANCE-2026-11-18", out)
        out = self.run_tool(card, ["show"])
        self.assertIn("BUY RELIANCE (NSE) · CNC · 54 shares · LIMIT ₹1,373.90 · valid 2026-11-18", out)


if __name__ == "__main__":
    unittest.main()
