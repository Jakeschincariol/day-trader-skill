"""A deterministic NSE session in Yahoo's chart shape, so the tests need no network.

The session is made up (it is not a real stock's day): 9:15 to 15:25, 75 five-minute bars, IST.
The opening range (9:15, 9:20, 9:25) is high 101.20, low 99.70; the 9:30 bar closes under the
high; the 9:35 bar is the first to close above it (101.45).
"""

import datetime
import json

EPOCH = datetime.datetime(1970, 1, 1)
IST = datetime.timedelta(hours=5, minutes=30)


def ts(day, hhmm):
    h, m = [int(x) for x in hhmm.split(":")]
    local = datetime.datetime.combine(day, datetime.time(h, m))
    return int((local - IST - EPOCH).total_seconds())


def slot_times():
    t, out = 9 * 60 + 15, []
    while t < 15 * 60 + 30:
        out.append("%02d:%02d" % divmod(t, 60))
        t += 5
    return out


def orb_day(day):
    """75 (open, high, low, close, volume) tuples."""
    bars = [(100.0, 101.0, 99.8, 100.6, 5000), (100.6, 101.2, 100.2, 100.8, 4000),
            (100.8, 101.1, 99.7, 100.4, 3000),                      # the opening range
            (100.4, 101.0, 100.3, 100.9, 3500),                     # 9:30 closes under 101.20
            (100.9, 101.6, 100.8, 101.45, 6000)]                    # 9:35 closes above: the trigger
    px = 101.45
    while len(bars) < 75:
        n = len(bars)
        c = round(px + (0.05 if n % 2 else -0.05), 2)
        bars.append((px, max(px, c) + 0.1, min(px, c) - 0.1, c, 2000))
        px = c
    return bars


def chart(symbol, days, prev_close=100.0, regular_time=None):
    """days: {date: bars}. Returns Yahoo v8 chart JSON text (symbol is the Yahoo one, RELIANCE.NS)."""
    stamps, cols = [], {"open": [], "high": [], "low": [], "close": [], "volume": []}
    for day in sorted(days):
        for hhmm, (o, h, l, c, v) in zip(slot_times(), days[day]):
            stamps.append(ts(day, hhmm))
            for k, x in zip(("open", "high", "low", "close", "volume"), (o, h, l, c, v)):
                cols[k].append(x)
    meta = {"currency": "INR", "symbol": symbol, "exchangeName": "NSI", "timezone": "IST", "gmtoffset": 19800,
            "dataGranularity": "5m", "chartPreviousClose": prev_close, "previousClose": prev_close,
            "regularMarketPrice": cols["close"][-1], "regularMarketTime": regular_time or stamps[-1] + 300}
    return json.dumps({"chart": {"result": [{"meta": meta, "timestamp": stamps,
                                             "indicators": {"quote": [cols]}}], "error": None}})
