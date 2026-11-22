"""ALPHA TRADER AI MT5 read-only foundation."""

from .readonly import (
    Bar,
    ConnectionHealth,
    MT5ConnectionError,
    MT5DataUnavailable,
    MT5ReadOnlyError,
    Quote,
    ReadOnlyMT5Adapter,
    SymbolSpec,
)
from .risk import RiskContext, RiskDecision, RiskLimits, TradeProposal, evaluate_trade

__all__ = [
    "Bar",
    "ConnectionHealth",
    "MT5ConnectionError",
    "MT5DataUnavailable",
    "MT5ReadOnlyError",
    "Quote",
    "ReadOnlyMT5Adapter",
    "RiskContext",
    "RiskDecision",
    "RiskLimits",
    "SymbolSpec",
    "TradeProposal",
    "evaluate_trade",
]
