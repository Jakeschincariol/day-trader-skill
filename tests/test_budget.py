import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import _load
from india import config, ticks

size = _load.load("swing-budget", "size")
CFG = config.load("/nonexistent")
PLAN = {"symbol": "TCS", "exchange": "NSE", "setup": "breakout_20d", "entry": 3412.40, "entry_style": "limit",
        "entry_trigger": None, "entry_date": "2026-11-19", "stop": 3296.10, "gtt_stop_limit": 3263.10,
        "target": 3645.00, "risk_per_share": 116.30, "reward_risk": 2.0, "max_hold_days": 15,
        "time_stop_date": "2026-12-10"}


def plan(**kw):
    p = dict(PLAN)
    p.update(kw)
    return p


class Size(unittest.TestCase):
    def test_risk_decides(self):
        r = size.size(plan(stop=3100.00, gtt_stop_limit=3069.0), CFG, [])
        self.assertEqual((r["qty"], r["decided_by"]), (16, "risk"))
        self.assertEqual(r["risk_at_stop"], 4998.40)

    def test_position_cap_decides(self):
        r = size.size(plan(), CFG, [])
        self.assertEqual((r["qty"], r["decided_by"]), (29, "position cap"))
        self.assertEqual(r["cost"], 98959.60)
        self.assertEqual(r["risk_at_stop"], 3372.70)
        self.assertEqual(r["risk_at_gtt_limit"], 4329.70)

    def test_cash_after_open_positions(self):
        held = [{"symbol": "INFY", "qty": 100, "entry": 4000.0, "stop": 3800.0}]
        r = size.size(plan(), CFG, held)
        self.assertEqual((r["qty"], r["decided_by"]), (14, "cash"))

    def test_cash_from_config(self):
        r = size.size(plan(), dict(CFG, cash=60000), [])
        self.assertEqual((r["qty"], r["decided_by"]), (2, "cash"))      # 60000 - 50000 buffer = 10000

    def test_refuses_when_one_share_breaks_risk(self):
        with self.assertRaises(size.SizeError) as cm:
            size.size(plan(stop=2000.0), dict(CFG, capital=100000), [])
        self.assertIn("one share", str(cm.exception))

    def test_refuses_under_min_order(self):
        with self.assertRaises(size.SizeError) as cm:
            size.size(plan(entry=60.0, stop=50.0, gtt_stop_limit=49.5, target=80.0), dict(CFG, capital=1500), [])
        self.assertIn("minimum order", str(cm.exception))

    def test_charges_included(self):
        r = size.size(plan(), CFG, [])
        self.assertGreater(r["charges"]["total"], 0)
        self.assertAlmostEqual(r["max_loss_incl_charges"], r["risk_at_stop"] + r["charges"]["total"], places=2)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "plan.json"), "w") as fh:
            json.dump(PLAN, fh)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_orders_json_shape(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = size.main(["--write", "--json", "--dir", self.tmp, "--now", "2026-11-18 16:00"])
        self.assertEqual(code, 0)
        with open(os.path.join(self.tmp, "orders.json")) as fh:
            doc = json.load(fh)
        p = doc["proposals"][0]
        self.assertEqual(p["id"], "TCS-2026-11-19")
        self.assertEqual((p["product"], p["side"], p["qty"]), ("CNC", "BUY", 29))
        g = p["gtt"]
        self.assertEqual(g["type"], "OCO")
        for k in ("stop_trigger", "stop_limit", "target_trigger", "target_limit"):
            self.assertTrue(ticks.is_valid(g[k]), k)
        self.assertTrue(ticks.is_valid(p["entry_price"]))

    def test_example_config_has_every_default(self):
        with open(os.path.join(_load.ROOT, "swing-budget", "config.example.json")) as fh:
            ex = json.load(fh)
        self.assertEqual(set(ex), set(config.DEFAULTS))
        self.assertEqual(ex["capital"], 500000)


if __name__ == "__main__":
    unittest.main()
