"""NSE clock and trading calendar, in India Standard Time.

IST is UTC+05:30 all year (India has no daylight saving), so no timezone
database is needed. The regular equity session runs 09:15 to 15:30 IST,
Monday to Friday, minus the trading holidays in india/holidays.json.

A daily bar for a date is treated as final from 15:50 IST (the 15:30 close
plus the delay of free data feeds).

    python3 -m india.market clock
    python3 -m india.market refresh-holidays      # needs the optional nse package
"""

import datetime
import json
import os
import sys
from typing import Dict, Optional, Tuple

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")
OPEN = datetime.time(9, 15)
CLOSE = datetime.time(15, 30)
BAR_FINAL = datetime.time(15, 50)

HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED = os.path.join(HERE, "holidays.json")

_cache = {}   # path -> years dict
_warned = set()


def _reset():
    """Forget cached holiday lists and warnings (tests)."""
    _cache.clear()
    _warned.clear()


def holidays_path() -> str:
    return os.environ.get("INDIA_HOLIDAYS") or SHIPPED


def load_holidays(path: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """year -> {iso date: holiday name}."""
    path = path or holidays_path()
    if path not in _cache:
        try:
            with open(path, encoding="utf-8") as fh:
                _cache[path] = json.load(fh).get("years", {}) or {}
        except (OSError, ValueError):
            _cache[path] = {}
    return _cache[path]


def _year(d: datetime.date) -> Optional[Dict[str, str]]:
    years = load_holidays()
    got = years.get(str(d.year))
    if got is None and d.year not in _warned:
        _warned.add(d.year)
        print("warning: no NSE holiday list for %d in india/holidays.json; treating only weekends "
              "as closed (run: python3 -m india.market refresh-holidays)" % d.year, file=sys.stderr)
    return got


def holiday_name(d: datetime.date) -> Optional[str]:
    return (_year(d) or {}).get(d.isoformat())


def is_trading_day(d: datetime.date) -> bool:
    if d.weekday() >= 5:
        return False
    return holiday_name(d) is None


def session(d: datetime.date) -> Optional[Tuple[datetime.time, datetime.time]]:
    return (OPEN, CLOSE) if is_trading_day(d) else None


def next_trading_day(d: datetime.date) -> datetime.date:
    d += datetime.timedelta(days=1)
    while not is_trading_day(d):
        d += datetime.timedelta(days=1)
    return d


def prev_trading_day(d: datetime.date) -> datetime.date:
    d -= datetime.timedelta(days=1)
    while not is_trading_day(d):
        d -= datetime.timedelta(days=1)
    return d


def add_trading_days(d: datetime.date, n: int) -> datetime.date:
    for _ in range(n):
        d = next_trading_day(d)
    return d


def trading_days_between(a: datetime.date, b: datetime.date) -> int:
    """Trading days after a, up to and including b."""
    n, d = 0, a
    while d < b:
        d += datetime.timedelta(days=1)
        if is_trading_day(d):
            n += 1
    return n


def now_ist(pinned: Optional[str] = None) -> datetime.datetime:
    """Naive datetime in IST. pinned: "YYYY-MM-DD HH:MM" (IST)."""
    if pinned:
        return datetime.datetime.strptime(pinned.strip(), "%Y-%m-%d %H:%M")
    return datetime.datetime.now(IST).replace(tzinfo=None)


def _closed_reason(d: datetime.date) -> str:
    if d.weekday() >= 5:
        return "weekend"
    name = holiday_name(d)
    return "NSE holiday: %s" % name if name else ""


def market_status(now: datetime.datetime) -> Dict:
    d, t = now.date(), now.time()
    if is_trading_day(d) and OPEN <= t < CLOSE:
        return {"open": True, "reason": "regular session 09:15-15:30 IST",
                "next_open": None, "closes": "%sT15:30" % d.isoformat()}
    if is_trading_day(d) and t < OPEN:
        nxt, reason = d, "before the open"
    else:
        nxt = next_trading_day(d)
        reason = _closed_reason(d) or "after the close"
    return {"open": False, "reason": reason, "next_open": "%sT09:15" % nxt.isoformat(), "closes": None}


def last_final_bar_date(now: datetime.datetime) -> datetime.date:
    d = now.date()
    if is_trading_day(d) and now.time() >= BAR_FINAL:
        return d
    return prev_trading_day(d)


def refresh_holidays(source, path: Optional[str] = None) -> int:
    """Write NSE trading holidays from source.trading_holidays() into
    holidays.json (merged by year). Returns how many dates were written."""
    path = path or SHIPPED
    got = source.trading_holidays()
    if not got:
        raise RuntimeError("no holidays returned%s" % (
            ": " + source.last_error if getattr(source, "last_error", "") else ""))
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    years = doc.get("years") or {}
    fresh = {}
    for iso, name in got.items():
        fresh.setdefault(iso[:4], {})[iso] = name
    years.update(fresh)
    doc.update({"source": "NSE trading holidays, CM segment (via the nse package)",
                "updated": now_ist().date().isoformat(),
                "years": {y: dict(sorted(v.items())) for y, v in sorted(years.items())}})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    _cache.pop(path, None)
    return len(got)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m india.market")
    ap.add_argument("command", choices=["clock", "refresh-holidays"])
    ap.add_argument("--now", help='pin the clock, "YYYY-MM-DD HH:MM" IST')
    a = ap.parse_args(argv)
    if a.command == "clock":
        s = market_status(now_ist(a.now))
        print("NSE %s (%s)%s" % ("OPEN" if s["open"] else "CLOSED", s["reason"],
                                 "" if s["open"] else ", next open %s IST" % s["next_open"].replace("T", " ")))
        return 0
    from india.nse_source import NseSource
    cache = os.path.join(os.getcwd(), "trader", "cache")
    src = NseSource(cache)
    if not src.available:
        print(src.why_unavailable, file=sys.stderr)
        return 1
    n = refresh_holidays(src)
    print("wrote %d NSE trading holidays to %s" % (n, SHIPPED))
    return 0


if __name__ == "__main__":
    sys.exit(main())
