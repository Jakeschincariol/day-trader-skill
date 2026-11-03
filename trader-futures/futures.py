#!/usr/bin/env python3
"""trader-futures: the strategy, the sizing, the risk rules and the backtest for
index futures. Pure Python, standard library only, no broker and no network:
everything here works on lists of 5-minute bars, so it is testable offline and
the same code runs in the backtest and in the live autotrader.

The strategy: VOLUME SURGE BREAKOUT on 5-minute bars.

A completed 5-minute bar is a long signal when all of these hold:
  1. it is inside the entry window (US index futures 09:45-15:30 New York,
     Eurex 09:15-17:00 Frankfurt), and the day has an open session;
  2. its volume is at least `rvol_min` (2.5) times the average volume of the
     same 5-minute slot over the previous `baseline_days` (10) sessions;
  3. it closes above the highest high of the previous `breakout_bars` (12)
     bars, so it breaks the last hour's range;
  4. it is a strong bar: closes above its open, in the top 30 % of its range;
  5. it closes above the session VWAP (volume-weighted average price);
  6. it is not a blow-off: its range is at most `max_bar_atr` (2.5) x ATR(14).

Shorts are the mirror image and are OFF unless "short" is in `directions`.

The plan: entry = a limit `slippage_ticks` above the signal close; stop = one
tick under the signal bar's midpoint ("stop_at": "mid", or "low" for its low) (at least `min_stop_ticks`, at most
`max_stop_atr` x ATR, otherwise no trade); target = `target_r` x the risk;
flat by the flat-by time whatever happens.

Commands (offline, on a CSV of 5-minute bars):
  python3 futures.py specs
  python3 futures.py backtest --contract MES --bars bars.csv [--out trades.csv]
  python3 futures.py signal   --contract MES --bars bars.csv [--now "2026-11-03 10:15"]

Not financial advice. Futures are leveraged: a loss can be larger than what
you deposited. Paper trading first.
"""

import argparse
import csv
import datetime
import json
import math
import os
import sys

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

UTC = datetime.timezone.utc
EPS = 1e-9
BAR = datetime.timedelta(minutes=5)

# Fallback contract specs. The autotrader replaces multiplier and tick with
# what IBKR's contract details say, so these only matter offline.
SPECS = {
    "MES": {"name": "Micro E-mini S&P 500", "symbol": "MES", "exchange": "CME", "currency": "USD",
            "multiplier": 5.0, "tick": 0.25, "tz": "America/New_York", "open": "09:30",
            "window": ["09:45", "15:30"], "flat_by": "15:55"},
    "ES": {"name": "E-mini S&P 500", "symbol": "ES", "exchange": "CME", "currency": "USD",
           "multiplier": 50.0, "tick": 0.25, "tz": "America/New_York", "open": "09:30",
           "window": ["09:45", "15:30"], "flat_by": "15:55"},
    "MNQ": {"name": "Micro E-mini Nasdaq-100", "symbol": "MNQ", "exchange": "CME", "currency": "USD",
            "multiplier": 2.0, "tick": 0.25, "tz": "America/New_York", "open": "09:30",
            "window": ["09:45", "15:30"], "flat_by": "15:55"},
    "NQ": {"name": "E-mini Nasdaq-100", "symbol": "NQ", "exchange": "CME", "currency": "USD",
           "multiplier": 20.0, "tick": 0.25, "tz": "America/New_York", "open": "09:30",
           "window": ["09:45", "15:30"], "flat_by": "15:55"},
    "MYM": {"name": "Micro E-mini Dow", "symbol": "MYM", "exchange": "CBOT", "currency": "USD",
            "multiplier": 0.5, "tick": 1.0, "tz": "America/New_York", "open": "09:30",
            "window": ["09:45", "15:30"], "flat_by": "15:55"},
    "M2K": {"name": "Micro E-mini Russell 2000", "symbol": "M2K", "exchange": "CME", "currency": "USD",
            "multiplier": 5.0, "tick": 0.1, "tz": "America/New_York", "open": "09:30",
            "window": ["09:45", "15:30"], "flat_by": "15:55"},
    "FDXS": {"name": "Micro-DAX", "symbol": "DAX", "trading_class": "FDXS", "exchange": "EUREX",
             "currency": "EUR", "multiplier": 1.0, "tick": 1.0, "tz": "Europe/Berlin", "open": "09:00",
             "window": ["09:15", "17:00"], "flat_by": "17:25"},
    "FDXM": {"name": "Mini-DAX", "symbol": "DAX", "trading_class": "FDXM", "exchange": "EUREX",
             "currency": "EUR", "multiplier": 5.0, "tick": 1.0, "tz": "Europe/Berlin", "open": "09:00",
             "window": ["09:15", "17:00"], "flat_by": "17:25"},
    "FSXE": {"name": "Micro Euro Stoxx 50", "symbol": "ESTX50", "trading_class": "FSXE",
             "exchange": "EUREX", "currency": "EUR", "multiplier": 1.0, "tick": 1.0, "tz": "Europe/Berlin",
             "open": "09:00", "window": ["09:15", "17:00"], "flat_by": "17:25"},
    "FESX": {"name": "Euro Stoxx 50", "symbol": "ESTX50", "trading_class": "FESX", "exchange": "EUREX",
             "currency": "EUR", "multiplier": 10.0, "tick": 1.0, "tz": "Europe/Berlin", "open": "09:00",
             "window": ["09:15", "17:00"], "flat_by": "17:25"},
}

STRATEGY = {
    "rvol_min": 2.5,
    "baseline_days": 10,
    "min_baseline_samples": 5,
    "min_day_volume_ratio": 0.5,
    "breakout_bars": 12,
    "close_pos_min": 0.7,
    "require_vwap": True,
    "atr_bars": 14,
    "max_bar_atr": 2.5,
    "stop_at": "mid",
    "min_stop_ticks": 4,
    "max_stop_atr": 1.5,
    "target_r": 2.0,
    "slippage_ticks": 2,
    "stop_slippage_ticks": 2,
    "directions": ["long"],
}

RISK = {
    "max_loss_per_trade_eur": 100.0,
    "max_daily_loss_eur": 250.0,
    "max_trades_per_day": 3,
    "max_contracts": 2,
    "max_open_positions": 1,
    "cooldown_after_loss_min": 30,
    "max_margin_pct": 50.0,
    "commission_per_side": 0.62,     # IBKR tiered, micro index futures incl. exchange fees (approx.)
    "eurusd": 1.08,                  # USD per EUR, offline fallback only
}


class FuturesError(Exception):
    pass


# ---------------------------------------------------------------- time

def tz(name):
    if ZoneInfo is None:
        raise FuturesError("Python 3.9 or newer is needed (zoneinfo)")
    try:
        return ZoneInfo(name)
    except Exception:
        raise FuturesError("time zone %s unknown: on Windows run  pip install tzdata" % name)


def hhmm(text):
    try:
        h, m = str(text).split(":")
        return datetime.time(int(h), int(m))
    except (ValueError, TypeError):
        raise FuturesError("not a HH:MM time: %r" % (text,))


def local(t, spec):
    return t.astimezone(tz(spec["tz"]))


def slot(t, spec):
    lt = local(t, spec)
    return lt.strftime("%H:%M")


def at_local(day, text, spec):
    """A local wall-clock time on `day` at the exchange, as aware UTC."""
    return datetime.datetime.combine(day, hhmm(text), tzinfo=tz(spec["tz"])).astimezone(UTC)


def round_tick(x, tick, how="nearest"):
    n = x / tick
    if how == "down":
        n = math.floor(n + EPS)
    elif how == "up":
        n = math.ceil(n - EPS)
    else:
        n = round(n)
    return round(n * tick, 10)


# ---------------------------------------------------------------- bars

def parse_time(text):
    s = str(text).strip().replace("T", " ").replace("Z", "+00:00")
    try:
        t = datetime.datetime.fromisoformat(s)
    except ValueError:
        try:
            t = datetime.datetime.utcfromtimestamp(int(float(s)))
        except ValueError:
            raise FuturesError("cannot read the time %r" % (text,))
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.astimezone(UTC)


def load_bars_csv(path):
    """CSV with columns time,open,high,low,close,volume (time = bar START, UTC
    or with an offset). Returns bars sorted by time."""
    bars = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            r = {k.strip().lower(): v for k, v in row.items() if k}
            bars.append({"t": parse_time(r.get("time") or r.get("date")),
                         "o": float(r["open"]), "h": float(r["high"]), "l": float(r["low"]),
                         "c": float(r["close"]), "v": float(r.get("volume") or 0)})
    bars.sort(key=lambda b: b["t"])
    return bars


def save_bars_csv(path, bars):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        for b in bars:
            w.writerow([b["t"].astimezone(UTC).isoformat(), b["o"], b["h"], b["l"], b["c"], b["v"]])


def completed(bars, now):
    """Only bars that have closed by `now` (bar time is the bar's start)."""
    if bars and bars[-1]["t"] + BAR <= now:
        return bars
    return [b for b in bars if b["t"] + BAR <= now]


def ann(b, spec):
    """Cache the bar's exchange-local day and HH:MM slot on the bar itself."""
    if b.get("_tz") != spec["tz"]:
        lt = local(b["t"], spec)
        b["_tz"], b["_d"], b["_s"] = spec["tz"], lt.date(), lt.strftime("%H:%M")
    return b


def session_day(t, spec):
    return local(t, spec).date()


def atr(bars, n):
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(len(bars) - n, len(bars)):
        b, p = bars[i], bars[i - 1]
        trs.append(max(b["h"] - b["l"], abs(b["h"] - p["c"]), abs(b["l"] - p["c"])))
    return sum(trs) / n


def vwap(bars_today):
    pv = vol = 0.0
    for b in bars_today:
        pv += (b["h"] + b["l"] + b["c"]) / 3.0 * b["v"]
        vol += b["v"]
    return pv / vol if vol > 0 else None


def day_volumes(bars, spec, before, days):
    """Total volume per session for the `days` sessions before `before`."""
    tot = {}
    for b in reversed(bars):
        ann(b, spec)
        if b["_d"] >= before:
            continue
        if b["_d"] not in tot and len(tot) >= days:
            break
        tot[b["_d"]] = tot.get(b["_d"], 0) + b["v"]
    return tot


def baseline_volume(bars, sig, spec, days, min_samples, min_day_ratio=0.0):
    """Average volume of the same 5-minute slot over the previous `days` sessions.
    Sessions whose total volume is under `min_day_ratio` x the busiest one are
    left out: after a quarterly roll, the days when this contract was still the
    thin back month would otherwise make every bar look like a surge."""
    ann(sig, spec)
    want, today = sig["_s"], sig["_d"]
    totals = day_volumes(bars, spec, today, days)
    if not totals:
        return None, 0
    floor = max(totals.values()) * min_day_ratio
    ok_days = {d for d, v in totals.items() if v >= floor}
    by_day = {}
    for b in reversed(bars):
        if b["_d"] < today and b["_d"] in ok_days and b["_s"] == want:
            by_day.setdefault(b["_d"], b["v"])
            if len(by_day) >= days:
                break
        elif b["_d"] < today and b["_d"] not in totals:
            break
    vols = [by_day[d] for d in sorted(by_day)]
    if len(vols) < min_samples:
        return None, len(vols)
    return sum(vols) / len(vols), len(vols)


# ---------------------------------------------------------------- the signal

def evaluate(bars, now, spec, strategy=None):
    """Look at the LAST COMPLETED bar at `now`. Returns a dict with
    status "signal" | "none" | "outside-window" | "no-data", the direction,
    the metrics and the reasons it did or did not fire."""
    s = dict(STRATEGY)
    s.update(strategy or {})
    done = completed(bars, now)
    if not done:
        return {"status": "no-data", "reasons": ["no completed bars yet"]}
    sig = done[-1]
    day = session_day(sig["t"], spec)
    bar_close = sig["t"] + BAR
    w0, w1 = at_local(day, spec["window"][0], spec), at_local(day, spec["window"][1], spec)
    out = {"bar_time": sig["t"].isoformat(), "bar_close": bar_close.isoformat(),
           "slot": slot(sig["t"], spec), "close": sig["c"]}
    if now - bar_close > 2 * BAR:
        out.update(status="no-data", reasons=["the last completed bar is %s: the data is stale" % out["slot"]])
        return out
    if not (w0 <= bar_close <= w1):
        out.update(status="outside-window",
                   reasons=["bar closes at %s, the entry window is %s-%s %s"
                            % (local(bar_close, spec).strftime("%H:%M"), spec["window"][0], spec["window"][1],
                               spec["tz"])])
        return out
    open_t = at_local(day, spec["open"], spec)
    today = []
    for b in reversed(done):
        if b["t"] < open_t:
            break
        today.append(b)
    today.reverse()
    a = atr(done, s["atr_bars"])
    base, n_base = baseline_volume(done, sig, spec, s["baseline_days"], s["min_baseline_samples"],
                                   s["min_day_volume_ratio"])
    prior = done[-1 - s["breakout_bars"]:-1]
    vw = vwap(today)
    if a is None or base is None or len(prior) < s["breakout_bars"] or vw is None:
        out.update(status="no-data", reasons=["not enough history: ATR %s, volume baseline %d sessions, "
                                              "%d prior bars" % ("ok" if a else "missing", n_base, len(prior))])
        return out
    rng = sig["h"] - sig["l"]
    pos = (sig["c"] - sig["l"]) / rng if rng > 0 else 0.5
    rvol = sig["v"] / base if base > 0 else 0.0
    hh, ll = max(b["h"] for b in prior), min(b["l"] for b in prior)
    out["metrics"] = {"rvol": round(rvol, 2), "volume": sig["v"], "baseline": round(base, 1),
                      "atr": round(a, 4), "vwap": round(vw, 4), "range_high": hh, "range_low": ll,
                      "bar_range_atr": round(rng / a, 2) if a else None, "close_pos": round(pos, 2)}
    checks = {
        "long": [
            (rvol >= s["rvol_min"], "volume %.1fx the usual for %s (needs %.1fx)" % (rvol, out["slot"], s["rvol_min"])),
            (sig["c"] > hh, "close %s vs the %d-bar high %s" % (sig["c"], s["breakout_bars"], hh)),
            (sig["c"] > sig["o"] and pos >= s["close_pos_min"], "bar closes in the top %d%% of its range (%d%%)"
             % (round((1 - s["close_pos_min"]) * 100), round(pos * 100))),
            ((not s["require_vwap"]) or sig["c"] > vw, "close above VWAP %.2f" % vw),
            (rng <= s["max_bar_atr"] * a, "bar range %.2f ATR (max %.1f)" % (rng / a, s["max_bar_atr"])),
        ],
        "short": [
            (rvol >= s["rvol_min"], "volume %.1fx the usual for %s (needs %.1fx)" % (rvol, out["slot"], s["rvol_min"])),
            (sig["c"] < ll, "close %s vs the %d-bar low %s" % (sig["c"], s["breakout_bars"], ll)),
            (sig["c"] < sig["o"] and pos <= 1 - s["close_pos_min"], "bar closes in the bottom %d%% of its range (%d%%)"
             % (round((1 - s["close_pos_min"]) * 100), round(pos * 100))),
            ((not s["require_vwap"]) or sig["c"] < vw, "close below VWAP %.2f" % vw),
            (rng <= s["max_bar_atr"] * a, "bar range %.2f ATR (max %.1f)" % (rng / a, s["max_bar_atr"])),
        ],
    }
    for d in s["directions"]:
        if d in checks and all(ok for ok, _ in checks[d]):
            out.update(status="signal", direction=d, reasons=[why for _, why in checks[d]])
            out["bar"] = sig
            return out
    d = s["directions"][0] if s["directions"] else "long"
    out.update(status="none", direction=None,
               reasons=["%s %s" % ("ok " if ok else "NO ", why) for ok, why in checks.get(d, [])])
    return out


# ---------------------------------------------------------------- the plan

def make_plan(sig, spec, strategy=None):
    """Signal -> entry limit, stop, target in points. None + reason if the stop
    is out of bounds."""
    s = dict(STRATEGY)
    s.update(strategy or {})
    bar, tick = sig["bar"], spec["tick"]
    a = sig["metrics"]["atr"]
    long_ = sig["direction"] == "long"
    sgn = 1 if long_ else -1
    entry_ref = bar["c"]
    limit = round_tick(entry_ref + sgn * s["slippage_ticks"] * tick, tick)
    if s["stop_at"] == "mid":
        mid = (bar["h"] + bar["l"]) / 2.0
        stop = round_tick(mid - tick, tick, "down") if long_ else round_tick(mid + tick, tick, "up")
    else:
        stop = round_tick(bar["l"] - tick, tick, "down") if long_ else round_tick(bar["h"] + tick, tick, "up")
    risk_pts = (limit - stop) * sgn
    if risk_pts < s["min_stop_ticks"] * tick - EPS:
        stop = round_tick(limit - sgn * s["min_stop_ticks"] * tick, tick)
        risk_pts = (limit - stop) * sgn
    if risk_pts > s["max_stop_atr"] * a + EPS:
        return None, ("stop %.2f points away is more than %.1f x ATR (%.2f): the signal bar is too wide"
                      % (risk_pts, s["max_stop_atr"], s["max_stop_atr"] * a))
    target = round_tick(entry_ref + sgn * s["target_r"] * risk_pts, tick, "down" if long_ else "up")
    return {"direction": sig["direction"], "action": "BUY" if long_ else "SELL",
            "entry_ref": entry_ref, "limit": limit, "stop": stop, "target": target,
            "risk_points": round(risk_pts, 10), "target_r": s["target_r"],
            "signal_bar": sig["bar_time"]}, None


def pick_contract(months, today, roll_days):
    """months: [{"expiry": "YYYYMMDD", ...}]. The nearest contract that expires
    more than `roll_days` calendar days after `today` (equity index futures
    move their volume to the next quarter about 8 days before expiry)."""
    def exp(m):
        e = str(m["expiry"])
        e = e + "15" if len(e) == 6 else e
        return datetime.date(int(e[:4]), int(e[4:6]), int(e[6:8]))
    live = sorted((m for m in months if (exp(m) - today).days > roll_days), key=exp)
    if not live:
        raise FuturesError("no contract expires more than %d days after %s" % (roll_days, today))
    return live[0]


def to_eur(amount, currency, eurusd):
    if currency == "EUR":
        return amount
    if currency == "USD":
        if not eurusd or eurusd <= 0:
            raise FuturesError("no EUR/USD rate")
        return amount / eurusd
    raise FuturesError("currency %s not supported" % currency)


def size(plan, spec, risk=None, eurusd=None):
    """Whole contracts so the loss at the stop (plus stop slippage and both
    commissions) stays within max_loss_per_trade_eur. Returns a dict; qty 0
    comes with the reason."""
    r = dict(RISK)
    r.update(risk or {})
    s = dict(STRATEGY)
    eurusd = eurusd or r["eurusd"]
    mult, tick = spec["multiplier"], spec["tick"]
    stop_slip = s["stop_slippage_ticks"] * tick
    per_ccy = (plan["risk_points"] + stop_slip) * mult + 2 * r["commission_per_side"]
    per_eur = to_eur(per_ccy, spec["currency"], eurusd)
    qty = int(math.floor(r["max_loss_per_trade_eur"] / per_eur + EPS))
    bound = "max loss per trade"
    if qty > r["max_contracts"]:
        qty, bound = int(r["max_contracts"]), "max contracts"
    out = {"qty": qty, "risk_per_contract_eur": round(per_eur, 2), "max_loss_eur": round(qty * per_eur, 2),
           "bound_by": bound, "currency": spec["currency"], "eurusd": eurusd}
    if qty < 1:
        out["reason"] = ("one contract risks EUR %.2f at the stop, more than your max loss per trade EUR %.2f"
                         % (per_eur, r["max_loss_per_trade_eur"]))
    return out


# ---------------------------------------------------------------- the risk rules

def risk_check(plan, sized, spec, state, now, risk=None, margin=None):
    """Every rule that must hold before an entry. state:
      {"date": "YYYY-MM-DD", "trades": n, "pnl_eur": today's P&L (realized + open),
       "open": {"MES": qty, ...}, "last_loss": {"MES": iso time}}
    margin: {"init_eur": x, "available_eur": y} from IBKR's what-if, or None.
    Returns (ok, reasons)."""
    r = dict(RISK)
    r.update(risk or {})
    reasons = []
    key = spec.get("key") or spec["symbol"]
    if sized["qty"] < 1:
        reasons.append(sized.get("reason") or "zero contracts")
    if state.get("halted"):
        reasons.append("trading halted for today: %s" % state["halted"])
    if state.get("trades", 0) >= r["max_trades_per_day"]:
        reasons.append("already %d trades today (max %d)" % (state.get("trades", 0), r["max_trades_per_day"]))
    open_ = {k: v for k, v in (state.get("open") or {}).items() if v}
    if open_.get(key):
        reasons.append("already a position in %s" % key)
    if len(open_) >= r["max_open_positions"]:
        reasons.append("%d position(s) open (max %d)" % (len(open_), r["max_open_positions"]))
    pnl = float(state.get("pnl_eur") or 0.0)
    if pnl <= -r["max_daily_loss_eur"]:
        reasons.append("today's P&L EUR %.2f has hit the daily loss limit EUR %.2f"
                       % (pnl, r["max_daily_loss_eur"]))
    elif pnl - sized.get("max_loss_eur", 0) < -r["max_daily_loss_eur"] - EPS:
        reasons.append("a stop-out (EUR %.2f) would take today past the daily loss limit (P&L now EUR %.2f, "
                       "limit EUR %.2f)" % (sized.get("max_loss_eur", 0), pnl, r["max_daily_loss_eur"]))
    last = (state.get("last_loss") or {}).get(key)
    if last:
        wait = parse_time(last) + datetime.timedelta(minutes=r["cooldown_after_loss_min"])
        if now < wait:
            reasons.append("cooling down after a loss in %s until %s" % (key, local(wait, spec).strftime("%H:%M")))
    if margin:
        cap = margin["available_eur"] * r["max_margin_pct"] / 100.0
        if margin["init_eur"] > cap + EPS:
            reasons.append("initial margin EUR %.0f is more than %d%% of available funds (EUR %.0f)"
                           % (margin["init_eur"], r["max_margin_pct"], cap))
    day = session_day(now, spec)
    if now > at_local(day, spec["window"][1], spec):
        reasons.append("past the last entry time %s" % spec["window"][1])
    return (not reasons), reasons


# ---------------------------------------------------------------- backtest

def backtest(bars, spec, strategy=None, risk=None, eurusd=None):
    """Replay every session in `bars` with the exact live rules.
    Entry: the bar after the signal, if its open is at or better than the limit
    (otherwise the trade is missed, as a live limit order would be).
    Exit: stop, target or flat-by. A bar that touches both stop and target is
    counted as the stop. Stop exits pay `stop_slippage_ticks`. Commissions are
    included. Returns {"trades": [...], "summary": {...}}."""
    s = dict(STRATEGY)
    s.update(strategy or {})
    r = dict(RISK)
    r.update(risk or {})
    eurusd = eurusd or r["eurusd"]
    mult, tick = spec["multiplier"], spec["tick"]
    trades, missed = [], 0
    idx_by_day = {}
    for i, b in enumerate(bars):
        idx_by_day.setdefault(ann(b, spec)["_d"], []).append(i)
    for day in sorted(idx_by_day):
        state = {"date": day.isoformat(), "trades": 0, "pnl_eur": 0.0, "open": {}, "last_loss": {}}
        flat_t = at_local(day, spec["flat_by"], spec)
        w0, w1 = at_local(day, spec["window"][0], spec), at_local(day, spec["window"][1], spec)
        ids = idx_by_day[day]
        k = 0
        while k < len(ids):
            i = ids[k]
            now = bars[i]["t"] + BAR
            if not (w0 <= now <= w1):
                k += 1
                continue
            sig = evaluate(bars[:i + 1], now, spec, s)
            if sig["status"] != "signal":
                k += 1
                continue
            plan, why = make_plan(sig, spec, s)
            if not plan:
                k += 1
                continue
            sized = size(plan, spec, r, eurusd)
            ok, _ = risk_check(plan, sized, spec, state, now, r)
            if not ok or k + 1 >= len(ids):
                k += 1
                continue
            nb = bars[ids[k + 1]]
            if nb["t"] >= flat_t:
                k += 1
                continue
            sgn = 1 if plan["direction"] == "long" else -1
            if (nb["o"] - plan["limit"]) * sgn > EPS:
                missed += 1
                k += 1
                continue
            entry = nb["o"]
            exit_px, why_exit, exit_t = None, None, None
            j = k + 1
            while j < len(ids):
                b = bars[ids[j]]
                if b["t"] >= flat_t:
                    exit_px, why_exit, exit_t = b["o"], "flat-by", b["t"]
                    break
                hit_stop = (b["l"] <= plan["stop"]) if sgn > 0 else (b["h"] >= plan["stop"])
                hit_tgt = (b["h"] >= plan["target"]) if sgn > 0 else (b["l"] <= plan["target"])
                if hit_stop:
                    gap = (b["o"] - plan["stop"]) * sgn < 0 and j > k + 1
                    base = b["o"] if gap else plan["stop"]
                    exit_px, why_exit, exit_t = base - sgn * s["stop_slippage_ticks"] * tick, "stop", b["t"]
                    break
                if hit_tgt:
                    exit_px, why_exit, exit_t = plan["target"], "target", b["t"]
                    break
                j += 1
            if exit_px is None:
                last = bars[ids[-1]]
                exit_px, why_exit, exit_t, j = last["c"], "end of data", last["t"], len(ids) - 1
            qty = sized["qty"]
            pts = (exit_px - entry) * sgn
            gross = pts * mult * qty
            net = gross - 2 * r["commission_per_side"] * qty
            net_eur = to_eur(net, spec["currency"], eurusd)
            risk_eur = sized["max_loss_eur"]
            trades.append({"date": day.isoformat(), "direction": plan["direction"],
                           "signal": local(bars[i]["t"], spec).strftime("%H:%M"),
                           "entry_time": local(nb["t"], spec).strftime("%H:%M"),
                           "exit_time": local(exit_t, spec).strftime("%H:%M"),
                           "qty": qty, "entry": entry, "stop": plan["stop"], "target": plan["target"],
                           "exit": round(exit_px, 6), "exit_reason": why_exit, "points": round(pts, 6),
                           "pnl_eur": round(net_eur, 2), "risk_eur": risk_eur,
                           "r": round(net_eur / risk_eur, 2) if risk_eur else None,
                           "rvol": sig["metrics"]["rvol"]})
            state["trades"] += 1
            state["pnl_eur"] += net_eur
            if net_eur < 0:
                state["last_loss"][spec.get("key") or spec["symbol"]] = exit_t.isoformat()
            # continue after the exit bar
            while k < len(ids) and ids[k] <= ids[j]:
                k += 1
    return {"trades": trades, "summary": summarize(trades, missed)}


def summarize(trades, missed=0):
    n = len(trades)
    wins = [t for t in trades if t["pnl_eur"] > 0]
    losses = [t for t in trades if t["pnl_eur"] <= 0]
    total = sum(t["pnl_eur"] for t in trades)
    gw = sum(t["pnl_eur"] for t in wins)
    gl = -sum(t["pnl_eur"] for t in losses)
    eq = peak = dd = 0.0
    for t in trades:
        eq += t["pnl_eur"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    rs = [t["r"] for t in trades if t["r"] is not None]
    return {"trades": n, "missed_entries": missed, "wins": len(wins), "losses": len(losses),
            "win_rate_pct": round(100.0 * len(wins) / n, 1) if n else None,
            "total_pnl_eur": round(total, 2), "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
            "profit_factor": round(gw / gl, 2) if gl > 0 else None,
            "max_drawdown_eur": round(dd, 2),
            "days": len({t["date"] for t in trades})}


def nl(x):
    """A number the Dutch way for Excel: decimal comma, no thousands separator."""
    if x is None:
        return ""
    if isinstance(x, float):
        return ("%.6f" % x).rstrip("0").rstrip(".").replace(".", ",")
    return str(x)


JOURNAL_FIELDS = ["date", "direction", "signal", "entry_time", "exit_time", "qty", "entry", "stop", "target",
                  "exit", "exit_reason", "points", "pnl_eur", "risk_eur", "r", "rvol"]


def write_trades_csv(path, trades, fields=JOURNAL_FIELDS):
    """Semicolon-separated with decimal commas: opens straight in Dutch Excel."""
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(fields)
        for t in trades:
            w.writerow([nl(t.get(f)) for f in fields])


# ---------------------------------------------------------------- config

def load_config(path):
    cfg = {"strategy": dict(STRATEGY), "risk": dict(RISK), "contracts": ["MES"]}
    if path and os.path.exists(path):
        with open(path) as fh:
            doc = json.load(fh)
        f = doc.get("futures", doc)
        cfg["strategy"].update(f.get("strategy") or {})
        cfg["risk"].update(f.get("risk") or {})
        for k, v in f.items():
            if k not in ("strategy", "risk"):
                cfg[k] = v
    return cfg


def spec_for(key, overrides=None):
    key = key.upper()
    if key not in SPECS:
        raise FuturesError("unknown contract %s; known: %s" % (key, ", ".join(sorted(SPECS))))
    s = dict(SPECS[key])
    s["key"] = key
    s.update(overrides or {})
    return s


# ---------------------------------------------------------------- CLI

def cmd_specs(a, cfg):
    print("%-5s %-28s %-7s %-4s %8s %6s  %s" % ("key", "contract", "exch", "ccy", "per pt", "tick", "entry window"))
    for k in sorted(SPECS):
        s = SPECS[k]
        print("%-5s %-28s %-7s %-4s %8s %6s  %s-%s %s, flat by %s" % (
            k, s["name"], s["exchange"], s["currency"], s["multiplier"], s["tick"], s["window"][0],
            s["window"][1], s["tz"].split("/")[1].replace("_", " "), s["flat_by"]))
    print("\nper pt = money per index point per contract. IBKR's contract details override these live.")
    return 0


def cmd_signal(a, cfg):
    spec = spec_for(a.contract)
    bars = load_bars_csv(a.bars)
    now = parse_time(a.now) if a.now else bars[-1]["t"] + BAR
    if a.now and len(a.now.strip()) <= 16 and "+" not in a.now:
        now = datetime.datetime.fromisoformat(a.now.replace("T", " ")).replace(tzinfo=tz(spec["tz"])).astimezone(UTC)
    sig = evaluate(bars, now, spec, cfg["strategy"])
    print("%s %s at %s: %s" % (spec["key"], sig.get("slot", ""), local(now, spec).strftime("%Y-%m-%d %H:%M"),
                               sig["status"].upper()))
    for line in sig.get("reasons", []):
        print("  " + line)
    if sig["status"] == "signal":
        plan, why = make_plan(sig, spec, cfg["strategy"])
        if not plan:
            print("  no trade: " + why)
            return 0
        sized = size(plan, spec, cfg["risk"])
        print("  plan: %s limit %s, stop %s, target %s (%.2f points risk)" % (
            plan["action"], plan["limit"], plan["stop"], plan["target"], plan["risk_points"]))
        print("  size: %d contract(s), max loss about EUR %.2f (%s)" % (
            sized["qty"], sized["max_loss_eur"], sized.get("reason") or sized["bound_by"]))
    return 0


def cmd_backtest(a, cfg):
    spec = spec_for(a.contract)
    bars = load_bars_csv(a.bars)
    res = backtest(bars, spec, cfg["strategy"], cfg["risk"], a.eurusd)
    sm = res["summary"]
    print("Backtest %s (%s), %d bars, %s to %s" % (
        spec["key"], spec["name"], len(bars), local(bars[0]["t"], spec).date(), local(bars[-1]["t"], spec).date()))
    print("  trades %d on %d days, missed entries %d" % (sm["trades"], sm["days"], sm["missed_entries"]))
    if sm["trades"]:
        print("  won %d, lost %d, win rate %s%%, average %sR, profit factor %s" % (
            sm["wins"], sm["losses"], sm["win_rate_pct"], sm["avg_r"], sm["profit_factor"]))
        print("  result EUR %.2f, worst drawdown EUR %.2f (after commissions and stop slippage)" % (
            sm["total_pnl_eur"], sm["max_drawdown_eur"]))
    if a.out:
        write_trades_csv(a.out, res["trades"])
        print("  trades written to %s (semicolon CSV, opens in Excel)" % a.out)
    print("A backtest shows what the rules did on past bars, not what they will do next.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="trader-futures: strategy, sizing, risk and backtest")
    p.add_argument("--config", default="trader/config.json")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("specs")
    s = sub.add_parser("signal")
    s.add_argument("--contract", default="MES")
    s.add_argument("--bars", required=True)
    s.add_argument("--now")
    b = sub.add_parser("backtest")
    b.add_argument("--contract", default="MES")
    b.add_argument("--bars", required=True)
    b.add_argument("--out")
    b.add_argument("--eurusd", type=float)
    a = p.parse_args(argv)
    try:
        cfg = load_config(a.config)
        if a.cmd == "specs":
            return cmd_specs(a, cfg)
        if a.cmd == "signal":
            return cmd_signal(a, cfg)
        if a.cmd == "backtest":
            return cmd_backtest(a, cfg)
        p.print_help()
        return 2
    except FuturesError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
