import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

ticket = load("trader-broker", "ticket")
journal = load("trader-broker", "journal")

PLAN_PATH = os.path.join(FIX, "trader-budget", "plan-tsla.json")


def run(mod, argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = mod.main(argv)
    return code, out.getvalue(), err.getvalue()


class Journal(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.state = os.path.join(self.d, "broker.json")
        self.notes = os.path.join(self.d, "journal.json")
        self.pf = os.path.join(self.d, "portfolio.json")
        self.cfg = os.path.join(self.d, "config.json")
        with open(self.cfg, "w") as fh:
            json.dump({"budget": 50000}, fh)

    def tearDown(self):
        shutil.rmtree(self.d)

    def fill(self, date, time, *extra):
        code, _, err = run(ticket, ["fill", "--date", date, "--now", "%s %s" % (date, time), "--portfolio", self.pf,
                                    "--config", self.cfg, "--state", self.state, "--plan", PLAN_PATH] + list(extra))
        self.assertEqual(code, 0, err)

    def show(self, *extra):
        return run(journal, ["show", "--state", self.state, "--notes", self.notes] + list(extra))

    def two_trades(self):
        # a win at the target, then a stop that slipped past -1R
        self.fill("2026-10-19", "10:15", "--symbol", "TSLA", "--side", "buy", "--qty", "8", "--price", "364.18")
        self.fill("2026-10-19", "11:40", "--symbol", "TSLA", "--side", "sell", "--qty", "8", "--price", "370.04",
                  "--kind", "target")
        self.fill("2026-10-19", "13:05", "--symbol", "TSLA", "--side", "buy", "--qty", "8", "--price", "364.18",
                  "--expected", "364.18")
        self.fill("2026-10-19", "13:30", "--symbol", "TSLA", "--side", "sell", "--qty", "8", "--price", "357.50",
                  "--kind", "stop", "--expected", "358.32")

    def test_the_entry_fill_keeps_its_plan(self):
        self.fill("2026-10-19", "10:15", "--symbol", "TSLA", "--side", "buy", "--qty", "8", "--price", "364.31")
        with open(self.state) as fh:
            rec = json.load(fh)["orders"][0]
        self.assertEqual((rec["stop"], rec["target"], rec["risk_per_share"], rec["setup"]),
                         (358.32, 370.04, 5.86, "orb"))

    def test_trades_in_r(self):
        self.two_trades()
        with open(self.state) as fh:
            trades, still_open = journal.build_trades(json.load(fh))
        self.assertEqual(still_open, [])
        self.assertEqual([(t["date"], t["exit_kind"], t["R"]) for t in trades],
                         [("2026-10-19", "target", 1.0), ("2026-10-19", "stop", -1.14)])
        self.assertEqual((trades[0]["entry_time"], trades[0]["hour"], trades[0]["weekday"]), ("10:15", "10:00", "Mon"))
        self.assertEqual(trades[1]["hour"], "13:00")
        s = journal.summarize(trades)
        self.assertEqual((s["n"], s["wins"], s["total_R"], s["beyond_stop"]), (2, 1, -0.14, 1))
        self.assertEqual(s["slippage_cost"], 6.56)

    def test_show_and_by(self):
        self.two_trades()
        code, text, _ = self.show("--by", "tag")
        self.assertIn("(no tag)", text)
        run(journal, ["note", "--notes", self.notes, "--symbol", "tsla", "--date", "2026-10-19", "--tag", "Chased",
                      "--text", "entered late"])
        code, text, err = self.show("--by", "exit", "--by", "tag")
        self.assertEqual(code, 0, err)
        self.assertIn("All trades: 2, won 1 (50 %; 95 % range", text)
        self.assertIn("1 loss went past -1R", text)
        self.assertIn("too few to know", text)
        self.assertIn("By exit:", text)
        self.assertIn("chased", text)
        code, text, _ = self.show("--json", "--from", "2026-10-20")
        self.assertEqual(code, 1)
        code, text, _ = self.show("--json", "--by", "hour")
        doc = json.loads(text)
        self.assertEqual([t["tags"] for t in doc["trades"]], [["chased"], ["chased"]])
        self.assertEqual(sorted(doc["by"]["hour"]), ["10:00", "13:00"])

    def test_partial_exits_and_open_positions(self):
        self.fill("2026-10-19", "10:15", "--symbol", "TSLA", "--side", "buy", "--qty", "8", "--price", "364.18")
        self.fill("2026-10-19", "11:00", "--symbol", "TSLA", "--side", "sell", "--qty", "4", "--price", "370.04",
                  "--kind", "target")
        with open(self.state) as fh:
            trades, still_open = journal.build_trades(json.load(fh))
        self.assertEqual((trades, still_open[0]["shares_open"]), ([], 4))
        self.fill("2026-10-19", "15:55", "--symbol", "TSLA", "--side", "sell", "--qty", "4", "--price", "366.11",
                  "--kind", "flatten", "--expected", "366.20")
        with open(self.state) as fh:
            trades, still_open = journal.build_trades(json.load(fh))
        self.assertEqual(still_open, [])
        self.assertEqual((trades[0]["exit"], trades[0]["exit_kind"]), (368.075, "mixed"))
        self.assertEqual(trades[0]["R"], 0.665)

    def test_csv_and_empty(self):
        code, text, _ = self.show()
        self.assertEqual(code, 1)
        self.assertIn("No closed trades", text)
        self.two_trades()
        path = os.path.join(self.d, "j.csv")
        code, text, _ = self.show("--csv", path)
        self.assertEqual(code, 0)
        with open(path) as fh:
            rows = fh.read().splitlines()
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].startswith("date,symbol,setup"))

    def test_note_needs_something(self):
        code, _, err = run(journal, ["note", "--notes", self.notes, "--symbol", "TSLA", "--date", "2026-10-19"])
        self.assertEqual(code, 1)
        self.assertIn("--tag or --text", err)

    def test_wilson(self):
        lo, hi = journal.wilson(10, 20)
        self.assertTrue(0.29 < lo < 0.30 and 0.70 < hi < 0.71)


if __name__ == "__main__":
    unittest.main()
