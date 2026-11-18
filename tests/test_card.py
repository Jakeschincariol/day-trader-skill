import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import _load
from india import config

card = _load.load("swing-card", "card")
PROP = {"id": "TCS-2026-11-19", "symbol": "TCS", "exchange": "NSE", "product": "CNC", "side": "BUY", "qty": 29,
        "entry_style": "limit", "entry_price": 3412.40, "entry_trigger": None, "valid_for": "2026-11-19",
        "gtt": {"type": "OCO", "stop_trigger": 3296.10, "stop_limit": 3263.10, "target_trigger": 3645.00,
                "target_limit": 3645.00},
        "cost": 98959.60, "risk_at_stop": 3372.70, "risk_at_gtt_limit": 4329.70, "charges_est": 230.4,
        "reward_risk": 2.0, "time_stop_date": "2026-12-10", "setup": "breakout_20d"}
EXPECTED = (
    "BUY TCS (NSE) · CNC · 29 shares · LIMIT ₹3,412.40 · valid 2026-11-19\n"
    "GTT OCO  stop trigger ₹3,296.10 / limit ₹3,263.10\n"
    "         target trigger ₹3,645.00 / limit ₹3,645.00\n"
    "Risk at stop ₹3,372.70 + charges ~₹230 · R:R 2.0 · time stop 2026-12-10\n"
    "Place the GTT after the buy fills: most brokers need the shares in your holdings first.")


class Render(unittest.TestCase):
    def test_card_layout_exact(self):
        self.assertEqual(card.render(PROP, {"verdict": "PASS", "reasons": []}), EXPECTED)

    def test_sl_buy_layout(self):
        p = dict(PROP, entry_style="sl-buy", entry_trigger=3420.40, entry_price=3437.60)
        first = card.render(p, {"verdict": "PASS", "reasons": []}).splitlines()[0]
        self.assertEqual(first, "BUY TCS (NSE) · CNC · 29 shares · SL-BUY trigger ₹3,420.40 / limit ₹3,437.60 · valid 2026-11-19")

    def test_warn_reasons_above_card(self):
        out = card.render(PROP, {"verdict": "WARN", "reasons": ["results due 2026-12-04, inside the hold"]})
        self.assertTrue(out.startswith("WARNING: results due 2026-12-04"))

    def test_no_network_or_broker_imports(self):
        with open(os.path.join(_load.ROOT, "swing-card", "card.py")) as fh:
            src = fh.read()
        for bad in ("urllib", "http", "requests", "import nse", "from nse", "socket"):
            self.assertNotIn(bad, src, bad)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "orders.json"), "w") as fh:
            json.dump({"proposals": [PROP]}, fh)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def verdict(self, verdict, prop=PROP, date="2026-11-18"):
        os.makedirs(os.path.join(self.tmp, "state"), exist_ok=True)
        with open(os.path.join(self.tmp, "state", "risk.json"), "w") as fh:
            json.dump({"date": date, "verdicts": [{"id": prop["id"], "verdict": verdict, "reasons": [],
                                                   "fingerprint": config.fingerprint(prop)}]}, fh)

    def cli(self, args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = card.main(args + ["--dir", self.tmp, "--now", "2026-11-18 16:30"])
        return code, buf.getvalue()

    def test_pass_shown(self):
        self.verdict("PASS")
        code, out = self.cli(["show"])
        self.assertIn(EXPECTED, out)

    def test_blocked_proposal_not_shown(self):
        self.verdict("BLOCK")
        code, out = self.cli(["show"])
        self.assertNotIn("BUY TCS", out)
        self.assertIn("No card", out)

    def test_stale_fingerprint_not_shown(self):
        self.verdict("PASS", prop=dict(PROP, qty=30))
        code, out = self.cli(["show"])
        self.assertNotIn("BUY TCS", out)
        self.verdict("PASS", date="2026-11-17")
        code, out = self.cli(["show"])
        self.assertNotIn("BUY TCS", out)

    def test_record_then_close_computes_r(self):
        self.cli(["record", "--id", "TCS-2026-11-19", "--qty", "29", "--price", "3412.40", "--date", "2026-11-19"])
        with open(os.path.join(self.tmp, "positions.json")) as fh:
            pos = json.load(fh)["positions"]
        self.assertEqual((pos[0]["symbol"], pos[0]["qty"], pos[0]["stop"], pos[0]["target"]), ("TCS", 29, 3296.10, 3645.0))
        code, out = self.cli(["close", "--symbol", "TCS", "--price", "3645.00", "--date", "2026-12-01", "--reason", "target"])
        with open(os.path.join(self.tmp, "journal.json")) as fh:
            t = json.load(fh)["trades"][0]
        self.assertEqual(t["r"], 2.0)
        self.assertEqual(t["exit_reason"], "target")
        self.assertAlmostEqual(t["pnl"], 29 * (3645.00 - 3412.40) - t["charges"], places=2)
        with open(os.path.join(self.tmp, "positions.json")) as fh:
            self.assertEqual(json.load(fh)["positions"], [])
        code, out = self.cli(["log"])
        self.assertIn("1 trade", out)
        self.assertIn("+2.00 R", out)

    def test_close_unknown_symbol(self):
        code, out = self.cli(["close", "--symbol", "INFY", "--price", "1500"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
