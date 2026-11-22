"""Deterministic, fail-closed risk proposal evaluator.

This module does not calculate position size or execute trades. A PASS only means
that supplied proposal data passed these checks; execution is never authorized here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Optional, Tuple


@dataclass(frozen=True)
class RiskLimits:
    account_currency: str
    max_quote_age_seconds: float
    max_spread_points: float
    max_trade_loss_account: float
    max_daily_loss_account: float
    max_open_positions: int


@dataclass(frozen=True)
class RiskContext:
    mode: str
    connected: bool
    now_utc: Optional[datetime]
    quote_time_utc: Optional[datetime]
    account_currency: Optional[str]
    spread_points: Optional[float]
    loss_at_stop_account: Optional[float]
    daily_pnl_account: Optional[float]
    open_positions: Optional[int]
    broker_specs_valid: bool
    duplicate: bool = False


@dataclass(frozen=True)
class TradeProposal:
    symbol: str
    side: str
    entry_price: Optional[float]
    stop_loss: Optional[float]
    volume: Optional[float]


@dataclass(frozen=True)
class RiskDecision:
    verdict: str
    reasons: Tuple[str, ...]
    execution_authorized: bool = False


def _finite_number(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _positive(value: object) -> bool:
    return _finite_number(value) and float(value) > 0


def _aware(value: Optional[datetime]) -> bool:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return False
    try:
        return value.utcoffset() is not None
    except (OverflowError, TypeError, ValueError):
        return False


def evaluate_trade(
    proposal: TradeProposal, context: RiskContext, limits: RiskLimits
) -> RiskDecision:
    """Evaluate a proposal against supplied local data; never authorize execution."""
    reasons = []

    if context.mode != "DEMO_PROPOSAL":
        reasons.append("mode_not_demo_proposal")
    if not context.connected:
        reasons.append("terminal_disconnected")
    if not context.broker_specs_valid:
        reasons.append("broker_specs_invalid")
    if context.duplicate:
        reasons.append("duplicate_intent")

    if not isinstance(proposal.symbol, str) or not proposal.symbol.strip():
        reasons.append("symbol_missing")
    side = proposal.side.upper() if isinstance(proposal.side, str) else ""
    if side not in ("BUY", "SELL"):
        reasons.append("side_invalid")

    for name, value in (
        ("entry_price", proposal.entry_price),
        ("stop_loss", proposal.stop_loss),
        ("volume", proposal.volume),
    ):
        if not _positive(value):
            reasons.append(name + "_invalid")

    if _positive(proposal.entry_price) and _positive(proposal.stop_loss):
        if side == "BUY" and float(proposal.stop_loss) >= float(proposal.entry_price):
            reasons.append("buy_stop_not_below_entry")
        elif side == "SELL" and float(proposal.stop_loss) <= float(proposal.entry_price):
            reasons.append("sell_stop_not_above_entry")

    if not isinstance(limits.account_currency, str) or not limits.account_currency.strip():
        reasons.append("limit_account_currency_missing")
    if not isinstance(context.account_currency, str) or not context.account_currency.strip():
        reasons.append("account_currency_missing")
    elif isinstance(limits.account_currency, str) and context.account_currency.upper() != limits.account_currency.upper():
        reasons.append("account_currency_mismatch")

    for name, value in (
        ("max_quote_age_seconds", limits.max_quote_age_seconds),
        ("max_spread_points", limits.max_spread_points),
        ("max_trade_loss_account", limits.max_trade_loss_account),
        ("max_daily_loss_account", limits.max_daily_loss_account),
    ):
        if not _positive(value):
            reasons.append(name + "_invalid")
    if not isinstance(limits.max_open_positions, int) or isinstance(limits.max_open_positions, bool) or limits.max_open_positions <= 0:
        reasons.append("max_open_positions_invalid")

    if not _aware(context.now_utc) or not _aware(context.quote_time_utc):
        reasons.append("quote_timestamp_missing_or_naive")
    elif _positive(limits.max_quote_age_seconds):
        age = (context.now_utc - context.quote_time_utc).total_seconds()
        if age < 0:
            reasons.append("quote_timestamp_in_future")
        elif age > float(limits.max_quote_age_seconds):
            reasons.append("quote_stale")

    if not _finite_number(context.spread_points) or float(context.spread_points) < 0:
        reasons.append("spread_missing_or_invalid")
    elif _positive(limits.max_spread_points) and float(context.spread_points) > float(limits.max_spread_points):
        reasons.append("spread_limit_exceeded")

    if not _positive(context.loss_at_stop_account):
        reasons.append("account_currency_stop_loss_missing_or_invalid")
    elif _positive(limits.max_trade_loss_account) and float(context.loss_at_stop_account) > float(limits.max_trade_loss_account):
        reasons.append("trade_loss_limit_exceeded")

    if not _finite_number(context.daily_pnl_account):
        reasons.append("daily_pnl_missing_or_invalid")
    elif _positive(limits.max_daily_loss_account) and float(context.daily_pnl_account) <= -float(limits.max_daily_loss_account):
        reasons.append("daily_loss_limit_reached")

    if not isinstance(context.open_positions, int) or isinstance(context.open_positions, bool) or context.open_positions < 0:
        reasons.append("open_positions_missing_or_invalid")
    elif isinstance(limits.max_open_positions, int) and not isinstance(limits.max_open_positions, bool) and limits.max_open_positions > 0 and context.open_positions >= limits.max_open_positions:
        reasons.append("open_position_limit_reached")

    return RiskDecision(
        verdict="BLOCK" if reasons else "PASS",
        reasons=tuple(reasons),
        execution_authorized=False,
    )
