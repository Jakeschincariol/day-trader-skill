import unittest
from datetime import datetime, timedelta, timezone

from alpha_mt5.risk import RiskContext, RiskLimits, TradeProposal, evaluate_trade


class RiskGateTests(unittest.TestCase):
    def setUp(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        self.proposal = TradeProposal("EURUSD", "BUY", 1.1, 1.09, 0.1)
        self.context = RiskContext(
            mode="DEMO_PROPOSAL",
            connected=True,
            now_utc=now,
            quote_time_utc=now - timedelta(seconds=2),
            account_currency="USD",
            spread_points=2.0,
            loss_at_stop_account=25.0,
            daily_pnl_account=-10.0,
            open_positions=1,
            broker_specs_valid=True,
            duplicate=False,
        )
        self.limits = RiskLimits(
            account_currency="USD",
            max_quote_age_seconds=5.0,
            max_spread_points=3.0,
            max_trade_loss_account=50.0,
            max_daily_loss_account=200.0,
            max_open_positions=3,
        )

    def test_valid_proposal_passes_risk_check_but_never_authorizes_execution(self):
        result = evaluate_trade(self.proposal, self.context, self.limits)
        self.assertEqual(result.verdict, "PASS")
        self.assertFalse(result.execution_authorized)

    def test_read_only_mode_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "mode": "READ_ONLY"})
        result = evaluate_trade(self.proposal, context, self.limits)
        self.assertEqual(result.verdict, "BLOCK")
        self.assertIn("mode_not_demo_proposal", result.reasons)

    def test_disconnected_terminal_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "connected": False})
        self.assertIn("terminal_disconnected", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_missing_broker_specs_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "broker_specs_valid": False})
        self.assertIn("broker_specs_invalid", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_stale_quote_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "quote_time_utc": self.context.now_utc - timedelta(seconds=10)})
        self.assertIn("quote_stale", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_future_quote_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "quote_time_utc": self.context.now_utc + timedelta(seconds=1)})
        self.assertIn("quote_timestamp_in_future", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_naive_timestamp_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "quote_time_utc": datetime(2026, 1, 1, 11, 59)})
        self.assertIn("quote_timestamp_missing_or_naive", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_malformed_timestamp_blocks_without_crashing(self):
        context = self.context.__class__(**{**self.context.__dict__, "now_utc": "not-a-datetime"})
        self.assertIn("quote_timestamp_missing_or_naive", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_zero_spread_is_valid(self):
        context = self.context.__class__(**{**self.context.__dict__, "spread_points": 0.0})
        self.assertEqual(evaluate_trade(self.proposal, context, self.limits).verdict, "PASS")

    def test_invalid_stop_direction_blocks(self):
        proposal = self.proposal.__class__("EURUSD", "BUY", 1.1, 1.11, 0.1)
        self.assertIn("buy_stop_not_below_entry", evaluate_trade(proposal, self.context, self.limits).reasons)

    def test_trade_loss_limit_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "loss_at_stop_account": 60.0})
        self.assertIn("trade_loss_limit_exceeded", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_daily_loss_limit_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "daily_pnl_account": -200.0})
        self.assertIn("daily_loss_limit_reached", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_spread_limit_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "spread_points": 4.0})
        self.assertIn("spread_limit_exceeded", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_duplicate_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "duplicate": True})
        self.assertIn("duplicate_intent", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_account_currency_mismatch_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "account_currency": "EUR"})
        self.assertIn("account_currency_mismatch", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_position_limit_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "open_positions": 3})
        self.assertIn("open_position_limit_reached", evaluate_trade(self.proposal, context, self.limits).reasons)

    def test_non_finite_loss_blocks(self):
        context = self.context.__class__(**{**self.context.__dict__, "loss_at_stop_account": float("nan")})
        self.assertIn("account_currency_stop_loss_missing_or_invalid", evaluate_trade(self.proposal, context, self.limits).reasons)


if __name__ == "__main__":
    unittest.main()
