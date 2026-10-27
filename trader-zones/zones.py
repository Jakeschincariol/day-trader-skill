#!/usr/bin/env python3
"""Zone Finder for trader-zones: ICT-style supply and demand zones on the 1-hour,
30-minute and 15-minute charts, and the 5-minute and 3-minute entry that follows
a sweep of a zone. Standard library only. It never places an order.

    python3 zones.py markets                          # the five markets and their Yahoo tickers
    python3 zones.py zones GBPUSD                     # today's and yesterday's zones, 60m + 30m + 15m
    python3 zones.py zones XAUUSD --tf 30m --days 2 --max-per-day 3
    python3 zones.py setup NQ                         # sweep + FVG/IFVG in the OTE + M3 CHoCH, long and short
    python3 zones.py setup MGC --now "2026-10-26 08:15" --offline DIR    # replay (New York time)
    python3 zones.py setup EURUSD --write             # also save trader/zones.json

Markets: XAUUSD (gold, read from COMEX gold futures GC=F), GBPUSD, EURUSD,
NQ (Nasdaq 100 futures NQ=F) and MGC (micro gold futures MGC=F).

The zone (one candle, high to low):
  displacement  a candle whose body is at least disp_atr x ATR(14) and
                disp_body of its own range, and that CLOSES beyond the last
                confirmed swing high (demand) or swing low (supply).
  zone candle   the latest candle before it (up to base_lookback back) with a
                small body (under base_body_atr x ATR), wicks making up more
                than base_wick of its range, and a move away from its extreme of
                at least move_atr x ATR. The zone is that one candle, high to low.
  fresh         price has not traded back into it. A zone price has entered is
                "touched".
  caps          only zones from the last --days days, at most --max-per-day per
                day, and (zones_in_sessions) only zone candles that opened in the
                Asia, London or New York window.

The entry (long side shown, short is the mirror image):
  1. price touches a demand zone
  2. on 5-minute bars it sweeps the latest swing low (wick below, close back
     above) with the wick reaching into the zone
  3. after the sweep a 5-minute FVG forms, or a bearish FVG is closed through
     (an IFVG), and its midpoint sits in the 62% to 79% retracement of the leg
     from the sweep low to the highest high since
  4. price trades back into that gap without breaking the sweep low
  5. on 3-minute bars a close above the last lower high made after the sweep
     (the CHoCH) is the trigger, inside an Asia, London or New York window
  stop below the sweep low (sweep_buffer_atr x ATR), target the nearest opposing
  zone or swing, and the trade is dropped when the reward to risk is under min_rr.

Time is New York time for sessions, so daylight saving is handled. The 3-minute
bars are built from 1-minute bars, so Yahoo's roughly week of 1-minute history
is how far back `setup` can look.

Data: Yahoo's free chart JSON (unofficial, can lag, forex and futures bars).
  --offline DIR reads DIR/<SYMBOL>_<interval>.json (a saved Yahoo chart), for
  example GBPUSD_30m.json, GBPUSD_5m.json and GBPUSD_1m.json.

trader/config.json (optional): a "zones" object overrides any default, for
example {"zones": {"min_rr": 3, "sessions": {"ny": [7, 10]}}}.

Exit codes: 0 when something was found, 1 when nothing was, 2 on an error.
"""

import argparse
import bisect
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; day-trader-skill/2.0; +https://github.com/Jakeschincariol/day-trader-skill)"
HOSTS = ("query2", "query1")
BACKOFF = 5.0
EPOCH = datetime.datetime(1970, 1, 1)
INTERVAL_SECS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "60m": 3600}

MARKETS = {
    "XAUUSD": {"yahoo": "GC=F", "digits": 2, "note": "COMEX gold futures stand in for spot gold"},
    "GBPUSD": {"yahoo": "GBPUSD=X", "digits": 5, "note": "spot forex"},
    "EURUSD": {"yahoo": "EURUSD=X", "digits": 5, "note": "spot forex"},
    "NQ": {"yahoo": "NQ=F", "digits": 2, "note": "Nasdaq 100 futures"},
    "MGC": {"yahoo": "MGC=F", "digits": 2, "note": "micro gold futures"},
}
ALIASES = {"NAS100": "NQ", "US100": "NQ", "NDX": "NQ", "GOLD": "XAUUSD"}

DEFAULTS = {
    "atr_len": 14,
    "swing_n": 2,
    "disp_atr": 1.5,
    "disp_body": 0.6,
    "base_body_atr": 0.4,
    "base_wick": 0.5,
    "base_lookback": 5,
    "move_atr": 2.0,
    "fvg_min_atr": 0.1,
    "sweep_buffer_atr": 0.2,
    "min_rr": 2.0,
    "days": 2,
    "max_per_day": 3,
    "zones_in_sessions": True,
    # New York hours [start, end). 24 means midnight.
    "sessions": {"asia": [19, 24], "london": [2, 5], "ny": [7, 10]},
}


class ZoneError(Exception):
    pass


# ---------------------------------------------------------------- time

def _nth_sunday(year, month, n):
    d = datetime.date(year, month, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def eastern_offset(utc):
    """Hours from UTC for New York: -4 in daylight time, -5 otherwise (US rule since 2007)."""
    y = utc.year
    start = datetime.datetime.combine(_nth_sunday(y, 3, 2), datetime.time(7, 0))
    end = datetime.datetime.combine(_nth_sunday(y, 11, 1), datetime.time(6, 0))
    naive = utc.replace(tzinfo=None)
    return -4 if start <= naive < end else -5


def utc_of(ts):
    return EPOCH + datetime.timedelta(seconds=int(ts))


def to_eastern(ts):
    u = utc_of(ts)
    return u + datetime.timedelta(hours=eastern_offset(u))


def eastern_to_ts(local):
    for off in (-4, -5):
        utc = local - datetime.timedelta(hours=off)
        if eastern_offset(utc) == off:
            return int((utc - EPOCH).total_seconds())
    return int((local + datetime.timedelta(hours=5) - EPOCH).total_seconds())


def now_ts():
    return int(time.time())


def fmt_et(ts):
    return to_eastern(ts).strftime("%a %m-%d %H:%M")


def in_session(ts, cfg):
    e = to_eastern(ts)
    minutes = e.hour * 60 + e.minute
    for lo, hi in cfg["sessions"].values():
        if lo * 60 <= minutes < hi * 60:
            return True
    return False


# ---------------------------------------------------------------- data

def resolve(sym):
    s = sym.upper().replace("/", "")
    s = ALIASES.get(s, s)
    if s not in MARKETS:
        raise ZoneError("unknown market %s: use one of %s" % (sym, ", ".join(sorted(MARKETS))))
    return s


def _open_url(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def yahoo_get(path):
    last = "no answer"
    for host in HOSTS:
        url = "https://%s.finance.yahoo.com%s" % (host, path)
        for attempt in (0, 1):
            try:
                return _open_url(url)
            except urllib.error.HTTPError as e:
                code = e.code
                e.close()
                last = "HTTP %d" % code
                if code == 429 and attempt == 0:
                    time.sleep(BACKOFF)
                    continue
                if code == 429 or code >= 500:
                    break
                raise ZoneError("Yahoo answered HTTP %d for %s" % (code, url.split("?")[0]))
            except urllib.error.URLError as e:
                last = "could not connect: %s" % (e.reason,)
                break
            except OSError as e:
                last = "network error: %s" % (e,)
                break
    raise ZoneError("Yahoo did not answer (%s): wait a minute and try again" % last)


def parse_chart(text, sym):
    try:
        data = json.loads(text)
        res = data["chart"]["result"]
    except (ValueError, KeyError, TypeError):
        raise ZoneError("Yahoo returned something unexpected for %s" % sym)
    if not res:
        err = (data.get("chart") or {}).get("error") or {}
        raise ZoneError("Yahoo has no data for %s: %s" % (sym, err.get("description") or "unknown ticker"))
    r = res[0] or {}
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0] or {}

    def at(key, i):
        arr = q.get(key) or []
        return arr[i] if i < len(arr) else None

    bars = []
    for i, t in enumerate(r.get("timestamp") or []):
        c = at("close", i)
        if t is None or c is None:
            continue
        o, h, lo = at("open", i), at("high", i), at("low", i)
        bars.append({"t": int(t), "o": float(c if o is None else o), "h": float(c if h is None else h),
                     "l": float(c if lo is None else lo), "c": float(c)})
    bars.sort(key=lambda b: b["t"])
    return bars


def get_bars(sym, interval, days, offline=None):
    if offline:
        path = os.path.join(offline, "%s_%s.json" % (sym, interval))
        if not os.path.exists(path):
            raise ZoneError("no offline file %s" % path)
        with open(path, encoding="utf-8") as fh:
            return parse_chart(fh.read(), sym)
    if interval == "1m":
        rng = "5d"
    elif interval == "60m":
        rng = "1mo"
    else:
        rng = "5d" if days <= 3 else "1mo"
    path = "/v8/finance/chart/%s?range=%s&interval=%s" % (MARKETS[sym]["yahoo"], rng, interval)
    return parse_chart(yahoo_get(path), sym)


def closed_only(bars, secs, now):
    """A bar counts once it has closed: now >= its start + its length."""
    return [b for b in bars if b["t"] + secs <= now]


def resample(bars, secs):
    """1-minute bars into `secs`-second bars, aligned to UTC midnight."""
    out, cur, key = [], None, None
    for b in bars:
        k = b["t"] - b["t"] % secs
        if k != key:
            if cur:
                out.append(cur)
            cur, key = {"t": k, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]}, k
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
    if cur:
        out.append(cur)
    return out


# ---------------------------------------------------------------- indicators

def atr_series(bars, n):
    tr = []
    for i, b in enumerate(bars):
        if i == 0:
            tr.append(b["h"] - b["l"])
        else:
            pc = bars[i - 1]["c"]
            tr.append(max(b["h"] - b["l"], abs(b["h"] - pc), abs(b["l"] - pc)))
    out = [None] * len(bars)
    for i in range(n - 1, len(bars)):
        out[i] = sum(tr[i - n + 1:i + 1]) / float(n)
    return out


def pivots(bars, n):
    """Swing highs and lows as (confirm_index, index, price). A swing is known only
    n bars after it forms, so nothing here looks ahead."""
    ph, pl = [], []
    for j in range(n, len(bars) - n):
        window = bars[j - n:j + n + 1]
        if bars[j]["h"] >= max(b["h"] for b in window):
            ph.append((j + n, j, bars[j]["h"]))
        if bars[j]["l"] <= min(b["l"] for b in window):
            pl.append((j + n, j, bars[j]["l"]))
    return ph, pl


def last_known(pivs, size):
    """For each bar, the price of the latest swing already confirmed (None before the first)."""
    out, p, cur = [], 0, None
    for i in range(size):
        while p < len(pivs) and pivs[p][0] <= i:
            cur = pivs[p][2]
            p += 1
        out.append(cur)
    return out


def flip_bars(bars):
    return [{"t": b["t"], "o": -b["o"], "h": -b["l"], "l": -b["h"], "c": -b["c"]} for b in bars]


# ---------------------------------------------------------------- zones

def find_zones(bars, cfg):
    """Supply and demand zones in one chart's bars, with whether price has come back."""
    n = len(bars)
    a = atr_series(bars, cfg["atr_len"])
    ph, pl = pivots(bars, cfg["swing_n"])
    sh, sl = last_known(ph, n), last_known(pl, n)
    zones, seen = [], set()
    for i in range(cfg["atr_len"] + 2 * cfg["swing_n"] + 2, n):
        if a[i] is None or a[i] <= 0:
            continue
        b = bars[i]
        rng = b["h"] - b["l"]
        body = abs(b["c"] - b["o"])
        if rng <= 0 or body < cfg["disp_atr"] * a[i] or body < cfg["disp_body"] * rng:
            continue
        up = b["c"] > b["o"]
        if up and not (sh[i - 1] is not None and b["c"] > sh[i - 1]):
            continue
        if not up and not (sl[i - 1] is not None and b["c"] < sl[i - 1]):
            continue
        for k in range(i - 1, max(i - 1 - cfg["base_lookback"], 0), -1):
            z = bars[k]
            rk = z["h"] - z["l"]
            kb = abs(z["c"] - z["o"])
            if a[k] is None or rk <= 0:
                continue
            if not (kb < cfg["base_body_atr"] * a[k] and (rk - kb) / rk > cfg["base_wick"]):
                continue
            if up:
                move = max(x["h"] for x in bars[k + 1:i + 1]) - z["h"]
            else:
                move = z["l"] - min(x["l"] for x in bars[k + 1:i + 1])
            if move < cfg["move_atr"] * a[i]:
                continue
            if (k, up) in seen:
                break
            seen.add((k, up))
            zones.append({"kind": "demand" if up else "supply", "t": z["t"], "disp_t": b["t"],
                          "high": z["h"], "low": z["l"], "di": i, "touched_t": None, "status": "fresh"})
            break
    for z in zones:
        for m in range(z["di"] + 1, n):
            hit = bars[m]["l"] <= z["high"] if z["kind"] == "demand" else bars[m]["h"] >= z["low"]
            if hit:
                z["touched_t"], z["status"] = bars[m]["t"], "touched"
                break
    return zones


def limit_zones(zones, now, cfg):
    """Keep zones from the last `days` days, the latest `max_per_day` per New York day,
    and (when asked) only zone candles that opened in a session window."""
    today = to_eastern(now).date()
    first = today - datetime.timedelta(days=cfg["days"] - 1)
    by_day = {}
    for z in zones:
        day = to_eastern(z["t"]).date()
        if day < first or day > today:
            continue
        if cfg["zones_in_sessions"] and not in_session(z["t"], cfg):
            continue
        by_day.setdefault(day, []).append(z)
    out = []
    for day in by_day:
        out.extend(sorted(by_day[day], key=lambda z: z["di"])[-cfg["max_per_day"]:])
    return sorted(out, key=lambda z: z["t"])


# ---------------------------------------------------------------- entry

STAGES = ["no zone touched yet",
          "zone touched, no sweep of a swing low yet",
          "swept, no FVG or IFVG with its midpoint in the OTE",
          "FVG/IFVG in the OTE, price has not come back into it",
          "price is in the gap, no 3-minute CHoCH yet",
          "CHoCH came outside the sessions or the reward to risk was too small",
          "triggered"]


def ote_band(lo, hi):
    """The 62% to 79% retracement of a leg from lo up to hi, as (low edge, high edge)."""
    rng = hi - lo
    return hi - 0.79 * rng, hi - 0.62 * rng


def gaps_after(m5, j, cfg, a5):
    """Bullish FVGs, and bearish FVGs closed back above (IFVGs), formed after bar j.
    Each is (available_index, low, high, kind)."""
    out = []
    for i in range(j + 2, len(m5)):
        if a5[i] is None:
            continue
        g = cfg["fvg_min_atr"] * a5[i]
        if m5[i]["l"] - m5[i - 2]["h"] >= g:
            out.append((i, m5[i - 2]["h"], m5[i]["l"], "FVG"))
        if m5[i - 2]["l"] - m5[i]["h"] >= g:
            lo, hi = m5[i]["h"], m5[i - 2]["l"]
            for m in range(i + 1, len(m5)):
                if m5[m]["c"] > hi:
                    out.append((m, lo, hi, "IFVG"))
                    break
    return sorted(out)


def m3_choch(m3, ph3, from_idx, sweep_idx, stop_low):
    """First 3-minute close above the last lower high made after the sweep; None if the
    sweep low breaks first."""
    for k in range(from_idx, len(m3)):
        if m3[k]["l"] < stop_low:
            return None
        known = [p for p in ph3 if p[0] < k and p[1] >= sweep_idx]
        if not known:
            continue
        _, pidx, price = known[-1]
        before = [q for q in ph3 if q[1] < pidx]
        if before and before[-1][2] > price and m3[k]["c"] > price:
            return k
    return None


def long_setups(zone, m5, m3, targets, cfg):
    """Every long entry for one demand zone, and how far the best attempt got (an index into STAGES)."""
    best = 0
    out = []
    if zone["touched_t"] is None or len(m5) < 10 or len(m3) < 10:
        return out, best
    best = 1
    a5 = atr_series(m5, cfg["atr_len"])
    _, pl5 = pivots(m5, cfg["swing_n"])
    ph3, _ = pivots(m3, cfg["swing_n"])
    t5 = [b["t"] for b in m5]
    t3 = [b["t"] for b in m3]
    for j in range(bisect.bisect_left(t5, zone["touched_t"]), len(m5)):
        prior = [p for p in pl5 if p[0] < j]
        if not prior or a5[j] is None:
            continue
        swing = prior[-1][2]
        sw = m5[j]
        if not (sw["l"] < swing and sw["c"] > swing and sw["l"] <= zone["high"]):
            continue
        best = max(best, 2)
        for avail, lo, hi, kind in gaps_after(m5, j, cfg, a5):
            leg_hi = max(b["h"] for b in m5[j:avail + 1])
            ote_lo, ote_hi = ote_band(sw["l"], leg_hi)
            if not ote_lo <= (lo + hi) / 2.0 <= ote_hi:
                continue
            best = max(best, 3)
            touch = None
            for m in range(avail + 1, len(m5)):
                if m5[m]["l"] < sw["l"]:
                    break
                if m5[m]["l"] <= hi:
                    touch = m
                    break
            if touch is None:
                continue
            best = max(best, 4)
            k = m3_choch(m3, ph3, bisect.bisect_left(t3, t5[touch]), bisect.bisect_left(t3, sw["t"]), sw["l"])
            if k is None:
                continue
            best = max(best, 5)
            when = t3[k] + 180
            entry = m3[k]["c"]
            stop = sw["l"] - cfg["sweep_buffer_atr"] * a5[touch]
            risk = entry - stop
            if risk <= 0 or not in_session(when, cfg):
                continue
            above = [x for x in targets if x > entry]
            target = min(above) if above else None
            rr = (target - entry) / risk if target is not None else None
            if rr is not None and rr < cfg["min_rr"]:
                continue
            best = 6
            out.append({"trigger": kind, "sweep_t": sw["t"], "sweep_low": sw["l"], "gap": (lo, hi),
                        "ote": (ote_lo, ote_hi), "entry_t": when, "entry": entry, "stop": stop,
                        "target": target, "rr": rr})
            break
    return out, best


def setups_for(zone, m5, m3, fresh_other, cfg):
    """Run the long logic for a demand zone, or for a supply zone on mirrored prices."""
    ph5, pl5 = pivots(m5, cfg["swing_n"])
    if zone["kind"] == "demand":
        targets = [z["low"] for z in fresh_other if z["kind"] == "supply"] + [p[2] for p in ph5]
        res, best = long_setups(zone, m5, m3, targets, cfg)
        for r in res:
            r["side"] = "long"
        return res, best
    mirrored = dict(zone, high=-zone["low"], low=-zone["high"])
    targets = [-z["high"] for z in fresh_other if z["kind"] == "demand"] + [-p[2] for p in pl5]
    res, best = long_setups(mirrored, flip_bars(m5), flip_bars(m3), targets, cfg)
    for r in res:
        r["side"] = "short"
        r["sweep_low"] = -r["sweep_low"]
        r["gap"] = (-r["gap"][1], -r["gap"][0])
        r["ote"] = (-r["ote"][1], -r["ote"][0])
        r["entry"], r["stop"] = -r["entry"], -r["stop"]
        r["target"] = None if r["target"] is None else -r["target"]
    return res, best


# ---------------------------------------------------------------- config and output

def read_config(path):
    cfg = json.loads(json.dumps(DEFAULTS))
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except ValueError as e:
            raise ZoneError("%s is not valid JSON: %s" % (path, e))
        over = doc.get("zones") or {}
        for k, v in over.items():
            if k == "sessions" and isinstance(v, dict):
                cfg["sessions"].update(v)
            elif k in cfg:
                cfg[k] = v
    return cfg


def px(sym, x):
    return "-" if x is None else "%.*f" % (MARKETS[sym]["digits"], x)


def zone_line(sym, tf, z):
    return "%-6s %-4s zone candle %s ET  %s to %s  %s" % (
        z["kind"].upper(), tf, fmt_et(z["t"]), px(sym, z["low"]), px(sym, z["high"]), z["status"])


def collect_zones(sym, tfs, now, cfg, offline):
    found = []
    for tf in tfs:
        bars = closed_only(get_bars(sym, tf, cfg["days"], offline), INTERVAL_SECS[tf], now)
        for z in limit_zones(find_zones(bars, cfg), now, cfg):
            z["tf"] = tf
            found.append(z)
    return sorted(found, key=lambda z: z["t"])


def cmd_zones(args, cfg, now):
    sym = resolve(args.symbol)
    tfs = ["60m", "30m", "15m"] if args.tf == "all" else [args.tf]
    found = collect_zones(sym, tfs, now, cfg, args.offline)
    if args.json:
        print(json.dumps(found, indent=2))
    else:
        print("%s (%s)  zones from the last %d day(s), at most %d per day, as of %s ET"
              % (sym, MARKETS[sym]["yahoo"], cfg["days"], cfg["max_per_day"], fmt_et(now)))
        for z in found:
            print(zone_line(sym, z["tf"], z))
        if not found:
            print("No zones. The rules are strict: a small-bodied, long-wicked candle, then a strong move away.")
    if args.write:
        write_doc(args.out, {"symbol": sym, "as_of": now, "zones": found})
    return 0 if found else 1


def cmd_setup(args, cfg, now):
    sym = resolve(args.symbol)
    zones = collect_zones(sym, ["60m", "30m", "15m"], now, cfg, args.offline)
    m5 = closed_only(get_bars(sym, "5m", cfg["days"], args.offline), 300, now)
    m1 = closed_only(get_bars(sym, "1m", cfg["days"], args.offline), 60, now)
    m3 = closed_only(resample(m1, 180), 180, now)
    fresh = [z for z in zones if z["status"] == "fresh"]
    results, lines, best_all = [], [], 0
    for z in zones:
        if z["touched_t"] is None:
            continue
        res, best = setups_for(z, m5, m3, fresh, cfg)
        best_all = max(best_all, best)
        for r in res:
            r["zone"] = {"tf": z["tf"], "kind": z["kind"], "low": z["low"], "high": z["high"], "t": z["t"]}
            results.append(r)
    results.sort(key=lambda r: r["entry_t"])
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("%s (%s)  as of %s ET  zones: %d (%d fresh, %d touched)"
              % (sym, MARKETS[sym]["yahoo"], fmt_et(now), len(zones), len(fresh), len(zones) - len(fresh)))
        for r in results:
            z = r["zone"]
            rr = "no target found" if r["rr"] is None else "R:R %.1f" % r["rr"]
            print("%s  %s %s zone %s-%s  swept %s, %s %s-%s in the OTE  ENTRY %s ET at %s  stop %s  target %s  %s"
                  % (r["side"].upper(), z["tf"], z["kind"], px(sym, z["low"]), px(sym, z["high"]),
                     fmt_et(r["sweep_t"]), r["trigger"], px(sym, r["gap"][0]), px(sym, r["gap"][1]),
                     fmt_et(r["entry_t"]), px(sym, r["entry"]), px(sym, r["stop"]), px(sym, r["target"]), rr))
        if results:
            print("These are signals from past and current bars. Nothing was placed. Set the stop and size BEFORE any order.")
        else:
            print("No entry. Furthest any zone got: %s." % STAGES[best_all])
    if args.write:
        write_doc(args.out, {"symbol": sym, "as_of": now, "setups": results})
    return 0 if results else 1


def write_doc(path, doc):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print("wrote %s" % path)


def cmd_markets():
    for s in sorted(MARKETS):
        print("%-7s Yahoo %-9s %s" % (s, MARKETS[s]["yahoo"], MARKETS[s]["note"]))
    return 0


def parse_now(text):
    if not text:
        return now_ts()
    for f in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return eastern_to_ts(datetime.datetime.strptime(text, f))
        except ValueError:
            pass
    raise ZoneError('--now wants New York time like "2026-10-26 08:15"')


def build_parser():
    p = argparse.ArgumentParser(prog="zones.py", description="ICT supply and demand zones and the 5m/3m entry")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("markets")
    for name in ("zones", "setup"):
        s = sub.add_parser(name)
        s.add_argument("symbol")
        s.add_argument("--now", help='New York time, e.g. "2026-10-26 08:15"')
        s.add_argument("--offline", help="folder with <SYMBOL>_<interval>.json saved Yahoo charts")
        s.add_argument("--config", default="trader/config.json")
        s.add_argument("--days", type=int)
        s.add_argument("--max-per-day", type=int)
        s.add_argument("--min-rr", type=float)
        s.add_argument("--json", action="store_true")
        s.add_argument("--write", action="store_true")
        s.add_argument("--out", default="trader/zones.json")
        if name == "zones":
            s.add_argument("--tf", default="all", choices=["all", "60m", "30m", "15m"])
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "markets":
            return cmd_markets()
        if args.cmd not in ("zones", "setup"):
            build_parser().print_help()
            return 2
        cfg = read_config(args.config)
        if args.days:
            cfg["days"] = args.days
        if args.max_per_day:
            cfg["max_per_day"] = args.max_per_day
        if args.min_rr is not None:
            cfg["min_rr"] = args.min_rr
        now = parse_now(args.now)
        return cmd_zones(args, cfg, now) if args.cmd == "zones" else cmd_setup(args, cfg, now)
    except ZoneError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
