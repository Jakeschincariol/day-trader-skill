"""Indicators and the swing setups, on daily bars (oldest first).

A setup "fires" on bar i when its rule is true at that bar's close. Each
setup comes with the level a later daily CLOSE must clear to trigger an
entry (None for oversold, which is a watch-only flag).

    breakout_20d     close above every close of the 20 sessions before it   level: that highest close
    breakout_52w     close above every high of the 250 sessions before it   level: that highest high
    bull_flag        up > 10 % from 15 to 5 sessions ago, then the last 5 closes inside a 5 % range
                                                                            level: the flag's highest high
    reclaim_ma20     closed under the 20-day average, then closed above it  level: today's high
    pullback_ma50    50-day average rising (vs 10 sessions ago), today's low within 2 % of it and the
                     close above it                                         level: today's high
    oversold         RSI 14 (Wilder) under 30                               level: none (watch only)
    oversold_bounce  RSI 14 under 30 yesterday and today closed up          level: today's high
"""

from typing import Dict, List, Optional

SETUPS = ("breakout_20d", "breakout_52w", "bull_flag", "reclaim_ma20", "pullback_ma50",
          "oversold", "oversold_bounce")


def sma(values: List[float], n: int) -> List[Optional[float]]:
    out, run = [], 0.0
    for i, v in enumerate(values):
        run += v
        if i >= n:
            run -= values[i - n]
        out.append(run / n if i >= n - 1 else None)
    return out


def rsi_wilder(closes: List[float], n: int = 14) -> List[Optional[float]]:
    out = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    g = [max(0.0, closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    lo = [max(0.0, closes[i - 1] - closes[i]) for i in range(1, len(closes))]
    ag, al = sum(g[:n]) / n, sum(lo[:n]) / n

    def val(a, b):
        return 100 - 100 / (1 + a / b) if b else 100.0
    out[n] = val(ag, al)
    for i in range(n, len(g)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + lo[i]) / n
        out[i + 1] = val(ag, al)
    return out


def atr(bars: List[Dict], n: int = 14) -> List[Optional[float]]:
    """Wilder's average true range."""
    out = [None] * len(bars)
    if len(bars) < n:
        return out
    tr = []
    for i, b in enumerate(bars):
        pc = bars[i - 1]["c"] if i else b["c"]
        tr.append(max(b["h"] - b["l"], abs(b["h"] - pc), abs(b["l"] - pc)))
    a = sum(tr[:n]) / n
    out[n - 1] = a
    for i in range(n, len(bars)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


def avg_traded_value(bars: List[Dict], n: int = 20, i: int = -1) -> Optional[float]:
    end = len(bars) if i == -1 else i + 1
    if end < n:
        return None
    window = bars[end - n:end]
    return sum(b["c"] * b["v"] for b in window) / n


def setups_at(bars: List[Dict], i: int, rsi: Optional[List[Optional[float]]] = None) -> Dict[str, Optional[float]]:
    """Setups firing on bar i -> trigger level. rsi: a precomputed
    rsi_wilder(closes) to reuse across many i (the Time Machine's history)."""
    if i < 0:
        i += len(bars)
    c = [b["c"] for b in bars[:i + 1]]
    b = bars[i]
    out = {}
    if i >= 20 and c[i] > max(c[i - 20:i]):
        out["breakout_20d"] = max(c[i - 20:i])
    if i >= 250:
        hi = max(x["h"] for x in bars[i - 250:i])
        if c[i] > hi:
            out["breakout_52w"] = hi
    if i >= 15 and c[i - 15] > 0:
        last5 = c[i - 4:i + 1]
        if c[i - 5] / c[i - 15] - 1 > 0.10 and max(last5) / min(last5) - 1 <= 0.05:
            out["bull_flag"] = max(x["h"] for x in bars[i - 4:i + 1])
    if i >= 20:
        m_now = sum(c[i - 19:i + 1]) / 20
        m_prev = sum(c[i - 20:i]) / 20
        if c[i - 1] < m_prev and c[i] > m_now:
            out["reclaim_ma20"] = b["h"]
    if i >= 59:
        m50 = sum(c[i - 49:i + 1]) / 50
        m50_then = sum(c[i - 59:i - 9]) / 50
        if m50 > m50_then and b["l"] <= m50 * 1.02 and c[i] > m50:
            out["pullback_ma50"] = b["h"]
    r = rsi if rsi is not None else rsi_wilder(c)
    if r[i] is not None and r[i] < 30:
        out["oversold"] = None
    if i >= 1 and r[i - 1] is not None and r[i - 1] < 30 and c[i] > c[i - 1]:
        out["oversold_bounce"] = b["h"]
    return out
