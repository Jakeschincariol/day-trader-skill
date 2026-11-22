"""Read-only adapter around the MetaTrader 5 Python API.

The adapter deliberately exposes no order placement, modification, or close methods.
The MetaTrader5 package is injected by the caller so this module remains importable
and testable on systems without a terminal or the proprietary Python package.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Optional, Tuple


class MT5ReadOnlyError(RuntimeError):
    """Base error for safe read-only MT5 access."""


class MT5ConnectionError(MT5ReadOnlyError):
    """The terminal could not be initialized or is not connected."""


class MT5DataUnavailable(MT5ReadOnlyError):
    """Required terminal data is missing or unavailable."""


@dataclass(frozen=True)
class ConnectionHealth:
    connected: bool
    terminal_name: Optional[str] = None
    terminal_build: Optional[int] = None
    account_currency: Optional[str] = None
    account_balance: Optional[float] = None
    account_equity: Optional[float] = None


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    digits: Optional[int]
    point: Optional[float]
    tick_size: Optional[float]
    tick_value_profit: Optional[float]
    tick_value_loss: Optional[float]
    contract_size: Optional[float]
    volume_min: Optional[float]
    volume_max: Optional[float]
    volume_step: Optional[float]
    stops_level: Optional[int]
    freeze_level: Optional[int]
    trade_mode: Optional[int]
    currency_base: Optional[str]
    currency_profit: Optional[str]
    currency_margin: Optional[str]


@dataclass(frozen=True)
class Quote:
    symbol: str
    time_utc: datetime
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    volume: Optional[float]
    time_msc: Optional[int]


@dataclass(frozen=True)
class Bar:
    symbol: str
    time_utc: datetime
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    tick_volume: Optional[int]
    spread: Optional[int]
    real_volume: Optional[int]


def _field(record: Any, name: str, default: Any = None) -> Any:
    """Read a field from a mapping, NumPy structured row, or object."""
    try:
        return record[name]
    except (TypeError, KeyError, IndexError, ValueError):
        return getattr(record, name, default)


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _utc_from_epoch(seconds: Any) -> datetime:
    try:
        return datetime.fromtimestamp(float(seconds), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        raise MT5DataUnavailable("MT5 returned an invalid timestamp") from exc


class ReadOnlyMT5Adapter:
    """Read terminal/account status, symbol metadata, ticks, and historical bars."""

    def __init__(self, mt5_api: Any) -> None:
        self._mt5 = mt5_api
        self._initialized = False

    def connect(self) -> None:
        """Initialize the existing terminal session; accepts no credentials."""
        initialize = getattr(self._mt5, "initialize", None)
        if not callable(initialize):
            raise MT5ConnectionError("MT5 API does not expose initialize()")
        if not initialize():
            last_error = getattr(self._mt5, "last_error", None)
            detail = last_error() if callable(last_error) else "unavailable"
            raise MT5ConnectionError("MT5 initialize failed: {}".format(detail))
        self._initialized = True

    def close(self) -> None:
        """Shut down this API session without changing orders or positions."""
        if self._initialized:
            shutdown = getattr(self._mt5, "shutdown", None)
            if callable(shutdown):
                shutdown()
        self._initialized = False

    def health(self) -> ConnectionHealth:
        """Return a minimal terminal/account health snapshot."""
        if not self._initialized:
            return ConnectionHealth(connected=False)
        terminal = self._mt5.terminal_info()
        account = self._mt5.account_info()
        connected = terminal is not None and bool(_field(terminal, "connected", False))
        return ConnectionHealth(
            connected=connected and account is not None,
            terminal_name=_optional_text(_field(terminal, "name")) if terminal is not None else None,
            terminal_build=_optional_int(_field(terminal, "build")) if terminal is not None else None,
            account_currency=_optional_text(_field(account, "currency")) if account is not None else None,
            account_balance=_optional_float(_field(account, "balance")) if account is not None else None,
            account_equity=_optional_float(_field(account, "equity")) if account is not None else None,
        )

    def _require_connected_terminal(self) -> None:
        if not self._initialized:
            raise MT5ConnectionError("Call connect() before reading MT5 data")
        terminal = self._mt5.terminal_info()
        if terminal is None or not bool(_field(terminal, "connected", False)):
            raise MT5ConnectionError("MT5 terminal is not connected")

    @staticmethod
    def _validate_symbol(symbol: str) -> None:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        """Read broker-provided symbol metadata without inferring missing values."""
        self._validate_symbol(symbol)
        self._require_connected_terminal()
        info = self._mt5.symbol_info(symbol)
        if info is None:
            raise MT5DataUnavailable("Symbol metadata unavailable for {!r}".format(symbol))
        return SymbolSpec(
            symbol=str(_field(info, "name", symbol)),
            digits=_optional_int(_field(info, "digits")),
            point=_optional_float(_field(info, "point")),
            tick_size=_optional_float(_field(info, "trade_tick_size")),
            tick_value_profit=_optional_float(_field(info, "trade_tick_value_profit")),
            tick_value_loss=_optional_float(_field(info, "trade_tick_value_loss")),
            contract_size=_optional_float(_field(info, "trade_contract_size")),
            volume_min=_optional_float(_field(info, "volume_min")),
            volume_max=_optional_float(_field(info, "volume_max")),
            volume_step=_optional_float(_field(info, "volume_step")),
            stops_level=_optional_int(_field(info, "trade_stops_level")),
            freeze_level=_optional_int(_field(info, "trade_freeze_level")),
            trade_mode=_optional_int(_field(info, "trade_mode")),
            currency_base=_optional_text(_field(info, "currency_base")),
            currency_profit=_optional_text(_field(info, "currency_profit")),
            currency_margin=_optional_text(_field(info, "currency_margin")),
        )

    def quote(self, symbol: str) -> Quote:
        """Read the latest tick. A missing timestamp or tick fails closed."""
        self._validate_symbol(symbol)
        self._require_connected_terminal()
        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            raise MT5DataUnavailable("Tick unavailable for {!r}".format(symbol))
        time_msc = _optional_int(_field(tick, "time_msc"))
        if time_msc is not None:
            timestamp = _utc_from_epoch(time_msc / 1000.0)
        else:
            epoch = _field(tick, "time")
            if epoch is None:
                raise MT5DataUnavailable("MT5 tick has no timestamp")
            timestamp = _utc_from_epoch(epoch)
        return Quote(
            symbol=symbol,
            time_utc=timestamp,
            bid=_optional_float(_field(tick, "bid")),
            ask=_optional_float(_field(tick, "ask")),
            last=_optional_float(_field(tick, "last")),
            volume=_optional_float(_field(tick, "volume")),
            time_msc=time_msc,
        )

    def bars(self, symbol: str, timeframe: Any, count: int) -> Tuple[Bar, ...]:
        """Read bars from the terminal; an empty history is returned as an empty tuple."""
        self._validate_symbol(symbol)
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError("count must be a positive integer")
        self._require_connected_terminal()
        rates = self._mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None:
            raise MT5DataUnavailable("Bar history unavailable for {!r}".format(symbol))
        result = []
        for row in rates:
            epoch = _field(row, "time")
            if epoch is None:
                raise MT5DataUnavailable("MT5 bar has no timestamp")
            result.append(
                Bar(
                    symbol=symbol,
                    time_utc=_utc_from_epoch(epoch),
                    open=_optional_float(_field(row, "open")),
                    high=_optional_float(_field(row, "high")),
                    low=_optional_float(_field(row, "low")),
                    close=_optional_float(_field(row, "close")),
                    tick_volume=_optional_int(_field(row, "tick_volume")),
                    spread=_optional_int(_field(row, "spread")),
                    real_volume=_optional_int(_field(row, "real_volume")),
                )
            )
        return tuple(result)
