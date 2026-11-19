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
from india import config

risk = _load.load("swing-risk", "check")
CFG = config.load("/nonexistent")
PROP = {"id": "TCS-2026-11-19", "symbol": "TCS", "exchange": "NSE", "product": "CNC", "side": "BUY", "qty": 29,
        "entry_style": "limit", "entry_price": 3412.40, "entry_trigger": None, "valid_for": "2026-11-19",
        "gtt": {"type": "OCO", "stop_trigger": 3296.10, "stop_limit": 3263.10, "target_trigger": 3645.00,
                "target_limit": 3645.00},
        "cost": 98959.60, "risk_at_stop": 3372.70, "risk_at_gtt_limit": 4329.70, "charges_est": 230.0,
        "reward_risk": 2.0, "time_stop_date": "2026-12-10", "setup": "breakout_20d"}
BANDS = {"TCS": "-", "M&M": "-", "SMALL": "5", "MID": "10"}


def prop(**kw):
    p = json.loads(json.dumps(PROP))
    p.update(kw)
    return p


def check(p=None, cfg=CFG, positions=(), bands=BANDS, results=None, avg_volume=2_000_000):
    return risk.check(p or prop(), cfg, list(positions), bands, {} if results is None else results, avg_volume)


class Check(unittest.TestCase):
    def test_pass_clean_proposal(self):
        r = check()
        self.assertEqual(r["verdict"], "PASS", r["reasons"])

    def test_block_band_5(self):
        r = check(prop(symbol="SMALL"))
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("5% price band" in x for x in r["reasons"]))

    def test_warn_band_10(self):
        r = check(prop(symbol="MID"))
        self.assertEqual(r["verdict"], "WARN")

    def test_block_heat(self):
        held = [{"symbol": "X%d" % k, "qty": 100, "entry": 1000.0, "stop": 940.0} for k in range(4)]   # 6,000 each
        r = check(positions=held, cfg=dict(CFG, cash=400000))
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("heat" in x for x in r["reasons"]), r["reasons"])

    def test_block_max_open_positions(self):
        held = [{"symbol": "X%d" % k, "qty": 1, "entry": 100.0, "stop": 99.0} for k in range(5)]
        r = check(positions=held)
        self.assertTrue(any("open positions" in x for x in r["reasons"]))
        self.assertEqual(r["verdict"], "BLOCK")

    def test_results_inside_hold_warns_and_blocks_when_configured(self):
        res = {"TCS": ["2026-12-04"]}
        self.assertEqual(check(results=res)["verdict"], "WARN")
        self.assertEqual(check(results=res, cfg=dict(CFG, block_on_results=True))["verdict"], "BLOCK")
        self.assertEqual(check(results={"TCS": ["2027-01-09"]})["verdict"], "PASS")

    def test_block_off_tick_price(self):
        p = prop()
        p["gtt"]["stop_limit"] = 3263.15
        r = check(p)
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("tick" in x for x in r["reasons"]))

    def test_ampersand_symbol_passes(self):
        r = check(prop(symbol="M&M"))
        self.assertEqual(r["verdict"], "PASS", r["reasons"])

    def test_block_bad_product_short_and_no_stop(self):
        self.assertEqual(check(prop(product="MIS"))["verdict"], "BLOCK")
        self.assertEqual(check(prop(side="SELL"))["verdict"], "BLOCK")
        p = prop()
        del p["gtt"]["stop_trigger"]
        self.assertEqual(check(p)["verdict"], "BLOCK")

    def test_block_risk_and_rr_and_blocked_list(self):
        self.assertEqual(check(prop(risk_at_stop=6000.0))["verdict"], "BLOCK")
        self.assertEqual(check(prop(reward_risk=1.2))["verdict"], "BLOCK")
        self.assertEqual(check(cfg=dict(CFG, blocked=["TCS"]))["verdict"], "BLOCK")

    def test_block_position_cap_and_cash(self):
        self.assertEqual(check(prop(cost=120000.0))["verdict"], "BLOCK")
        r = check(cfg=dict(CFG, cash=120000))
        self.assertTrue(any("cash" in x for x in r["reasons"]))

    def test_liquidity_warn(self):
        r = check(avg_volume=1000)
        self.assertEqual(r["verdict"], "WARN")
        self.assertTrue(any("average volume" in x for x in r["reasons"]))

    def test_unknown_band_and_results_warn(self):
        r = risk.check(prop(), CFG, [], {}, None, 2_000_000)
        self.assertEqual(r["verdict"], "WARN")
        self.assertTrue(any("results data unavailable" in x for x in r["reasons"]))
        self.assertTrue(any("price band unknown" in x for x in r["reasons"]))

    def test_recomputes_cost_and_risk_from_prices(self):
        # qty edited, derived fields left stale: must not pass on the stale numbers
        r = check(prop(qty=290))
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("does not match" in x for x in r["reasons"]), r["reasons"])
        p = prop(qty=290)
        del p["risk_at_stop"], p["cost"]
        r = check(p)
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertTrue(any("per trade" in x for x in r["reasons"]), r["reasons"])

    def test_block_stop_or_target_on_wrong_side(self):
        p = prop()
        p["gtt"]["stop_trigger"] = 3420.0
        self.assertEqual(check(p)["verdict"], "BLOCK")
        p = prop()
        p["gtt"]["target_trigger"] = 3400.0
        self.assertEqual(check(p)["verdict"], "BLOCK")

    def test_fingerprint_changes_with_qty(self):
        self.assertNotEqual(check()["fingerprint"], check(prop(qty=30))["fingerprint"])
        self.assertEqual(check()["fingerprint"], config.fingerprint(prop()))


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "orders.json"), "w") as fh:
            json.dump({"proposals": [PROP]}, fh)
        # offline data without an nse/ folder: NSE data is off
        self.off = os.path.join(self.tmp, "offline")
        os.makedirs(self.off)
        for name in ("sec_list.csv", "chart-TCS.NS-1y.json.gz"):
            shutil.copy(os.path.join(_load.INDIA_FIX, name), self.off)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_risk_runs_without_nse(self):
        buf, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(sys.modules, {"nse": None}), contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = risk.main(["--dir", self.tmp, "--now", "2026-11-18 16:00", "--offline", self.off])
        self.assertEqual(code, 0)
        self.assertIn("WARN", buf.getvalue())
        self.assertIn("results data unavailable", buf.getvalue())
        with open(os.path.join(self.tmp, "state", "risk.json")) as fh:
            v = json.load(fh)["verdicts"][0]
        self.assertEqual((v["id"], v["verdict"]), ("TCS-2026-11-19", "WARN"))

    def test_manual_results_file(self):
        with open(os.path.join(self.tmp, "results.json"), "w") as fh:
            json.dump({"TCS": ["2026-12-04"]}, fh)
        buf = io.StringIO()
        with mock.patch.dict(sys.modules, {"nse": None}), contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            risk.main(["--dir", self.tmp, "--now", "2026-11-18 16:00", "--offline", self.off, "--json"])
        v = json.loads(buf.getvalue())["verdicts"][0]
        self.assertTrue(any("2026-12-04" in x for x in v["reasons"]), v["reasons"])


if __name__ == "__main__":
    unittest.main()
