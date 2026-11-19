"""Stop, target and time-stop rules for a long swing trade, on NSE ticks.

Stops round DOWN to a valid tick, targets to the nearest tick. A stop must
sit below the entry and at least 0.5 x ATR(14) away (closer than that is
inside one day's normal noise).
"""

import datetime
from typing import Dict, List, Optional, Tuple

from india import indicators, market, ticks

NOISE_ATR = 0.5


class PlanError(ValueError):
    pass


def compute_stop(bars: List[Dict], i: int, entry: float, method: str, schedule=None) -> Tuple[float, str]:
    if i < 0:
        i += len(bars)
    a = indicators.atr(bars[:i + 1], 14)[i] if i >= 13 else None
    name, _, param = method.partition(":")
    try:
        if name == "swing-low":
            n = int(param or 10)
            raw = min(b["l"] for b in bars[max(0, i - n + 1):i + 1])
            how = "lowest low of the last %d sessions" % n
        elif name == "setup-low":
            raw, how = bars[i]["l"], "the trigger day's low"
        elif name == "atr":
            if a is None:
                raise PlanError("an ATR stop needs 14 daily bars")
            k = float(param or 2)
            raw, how = entry - k * a, "%g x ATR(14) %.2f below the entry" % (k, a)
        elif name == "pct":
            raw, how = entry * (1 - float(param) / 100), "%s%% below the entry" % param
        elif name == "price":
            raw, how = float(param), "your price"
        else:
            raise PlanError("unknown stop method %r (swing-low[:N], setup-low, atr:K, pct:X, price:X)" % method)
    except (TypeError, ValueError) as e:
        if isinstance(e, PlanError):
            raise
        raise PlanError("bad stop %r: %s" % (method, e))
    stop = ticks.round_down(raw, schedule)
    if stop >= entry:
        raise PlanError("the stop %.2f (%s) is not below the entry %.2f" % (stop, how, entry))
    if a is not None and entry - stop < NOISE_ATR * a:
        raise PlanError("the stop %.2f is %.2f below the entry, under 0.5 x ATR(14) = %.2f: inside one day's "
                        "normal noise. Use a wider stop (swing-low, atr:2)." % (stop, entry - stop, NOISE_ATR * a))
    return stop, how


def compute_target(entry: float, stop: float, spec: str, schedule=None) -> float:
    s = spec.strip()
    if s.upper().endswith("R"):
        try:
            k = float(s[:-1])
        except ValueError:
            raise PlanError("bad target %r (1R, 2R, 3R or price:X)" % spec)
        raw = entry + k * (entry - stop)
    elif s.startswith("price:"):
        raw = float(s[6:])
    else:
        raise PlanError("bad target %r (1R, 2R, 3R or price:X)" % spec)
    t = ticks.round_nearest(raw, schedule)
    if t <= entry:
        raise PlanError("the target %.2f is not above the entry %.2f" % (t, entry))
    return t


def gtt_stop_limit(stop: float, slippage_pct: float, schedule=None) -> float:
    return ticks.round_down(stop * (1 - slippage_pct / 100), schedule)


def time_stop(entry_date: datetime.date, max_hold: int) -> datetime.date:
    return market.add_trading_days(entry_date, max_hold)
