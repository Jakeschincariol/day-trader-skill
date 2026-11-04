"""Unknown risk in today's placed-entry log must not count as zero."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from test_risk import at, bracket, cfg, check, NOW, placed, tsla, verdicts


class DailyRiskLedger(unittest.TestCase):
    def test_missing_loss_blocks_new_entries_until_the_log_is_reconciled(self):
        record = placed("AAPL", max_loss=None)
        state = {"orders": [record, placed("AMD", max_loss=20)]}
        result = check.check([tsla()], cfg(), state=state, now=at(NOW))
        self.assertEqual(verdicts(result), ["BLOCK"])
        self.assertIn("daily loss: total risk from today's entries is unknown (buy AAPL)",
                      " | ".join(result["results"][0]["reasons"]))
        self.assertIsNone(result["today"]["loss_at_risk"])
        self.assertEqual(result["today"]["known_loss_at_risk"], 20)
        self.assertEqual(result["today"]["entries_with_unknown_loss"], 1)
        self.assertIn("unknown ($20 known) of $150 daily loss", result["results"][0]["info"][-1])
        self.assertIn("reconcile the trade log", " | ".join(result["results"][0]["reasons"]))

        record["max_loss"] = 50
        reconciled = check.check([tsla()], cfg(), state=state, now=at(NOW))
        self.assertEqual(verdicts(reconciled), ["PASS"])
        self.assertEqual(reconciled["today"]["loss_at_risk"], 70)

    def test_invalid_recorded_losses_cannot_bypass_the_daily_limit(self):
        for bad in (None, "bad", "NaN", float("nan"), "Infinity", float("inf"),
                    float("-inf"), -100, "-100", True, False, 10 ** 400):
            with self.subTest(max_loss=repr(bad)):
                record = dict(placed("AAPL"), max_loss=bad)
                result = check.check([tsla()], cfg(), state={"orders": [record]}, now=at(NOW))
                self.assertEqual(verdicts(result), ["BLOCK"])
                self.assertIsNone(result["today"]["loss_at_risk"])
                self.assertEqual(result["today"]["entries_with_unknown_loss"], 1)
                json.dumps(result, allow_nan=False)

    def test_zero_and_numeric_string_losses_remain_usable(self):
        state = {"orders": [placed("AAPL", max_loss=0), placed("AMD", max_loss="50")]}
        result = check.check([tsla()], cfg(), state=state, now=at(NOW))
        self.assertEqual(verdicts(result), ["PASS"])
        self.assertEqual(result["today"]["loss_at_risk"], 50)
        self.assertEqual(result["today"]["entries_with_unknown_loss"], 0)

    def test_unknown_loss_blocks_every_new_entry_in_a_batch(self):
        state = {"orders": [placed("AAPL", max_loss=None)]}
        orders = [bracket(sym, 1, 50, 49, 52) for sym in ("AAA", "BBB")]
        result = check.check(orders, cfg(), state=state, now=at(NOW))
        self.assertEqual(verdicts(result), ["BLOCK", "BLOCK"])

    def test_unknown_entry_loss_does_not_prevent_a_closing_sell(self):
        state = {"orders": [placed("AAPL", max_loss=None)]}
        portfolio = {"cash": 2000, "positions": [{"ticker": "TSLA", "shares": 8}]}
        closing = {"symbol": "TSLA", "side": "sell", "qty": "8", "type": "market", "time_in_force": "day"}
        result = check.check([closing, tsla()], cfg(), portfolio=portfolio, state=state,
                             prices={"TSLA": 364.18}, now=at(NOW))
        self.assertEqual(verdicts(result), ["PASS", "BLOCK"])
        self.assertEqual(result["results"][0]["kind"], "exit")

    def test_old_failed_declined_and_exit_records_do_not_create_unknown_entry_risk(self):
        state = {"orders": [placed("AAPL", max_loss=None, day="2026-10-16"),
                            placed("AMD", max_loss=None, status="failed"),
                            placed("NVDA", max_loss=None, status="declined"),
                            placed("KO", max_loss=None, side="sell", kind="exit")]}
        result = check.check([tsla()], cfg(), state=state, now=at(NOW))
        self.assertEqual(verdicts(result), ["PASS"])
        self.assertEqual(result["today"]["loss_at_risk"], 0)
        self.assertEqual(result["today"]["entries_with_unknown_loss"], 0)

    def test_an_explicitly_disabled_daily_limit_does_not_block(self):
        state = {"orders": [placed("AAPL", max_loss=None)]}
        result = check.check([tsla()], cfg(max_daily_loss_usd=0), state=state, now=at(NOW))
        self.assertEqual(verdicts(result), ["PASS"])
        self.assertIsNone(result["today"]["loss_at_risk"])
        self.assertTrue(any("total daily risk is unknown" in w for w in result["warnings"]))

    def test_cli_returns_block_and_saves_an_unknown_total_as_null(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = {name: os.path.join(folder, name + ".json") for name in ("orders", "config", "state", "risk")}
            for name, value in (("orders", {"orders": [tsla()]}), ("config", cfg()),
                                ("state", {"orders": [placed("AAPL", max_loss=None)]})):
                with open(paths[name], "w", encoding="utf-8") as fh:
                    json.dump(value, fh)
            absent = os.path.join(folder, "absent.json")
            output = io.StringIO()
            with redirect_stdout(output):
                code = check.main(["--orders", paths["orders"], "--config", paths["config"],
                                   "--state", paths["state"], "--portfolio", absent, "--prices", absent,
                                   "--out", paths["risk"], "--now", NOW, "--json"])
            self.assertEqual(code, 1)
            result = json.loads(output.getvalue())
            self.assertEqual(verdicts(result), ["BLOCK"])
            with open(paths["risk"], encoding="utf-8") as fh:
                recorded = json.load(fh)
            self.assertIsNone(recorded["today"]["loss_at_risk"])
            self.assertEqual(recorded["today"]["entries_with_unknown_loss"], 1)


if __name__ == "__main__":
    unittest.main()
