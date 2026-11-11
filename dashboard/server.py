#!/usr/bin/env python3
"""Trader Dashboard server. Standard library only.

    python3 dashboard/server.py              # http://127.0.0.1:8212
    python3 dashboard/server.py --port 9000

Serves the web app in dashboard/static and a small JSON API:

  GET  /api/universe                      the stock and ETF lists
  GET  /api/quotes?symbols=AAPL,SPY       price, change, rating, entry status
  GET  /api/analysis?symbol=AAPL          bars, indicators, rating, entry plan
  GET  /api/screener?list=stocks|etfs|all every symbol in the list, rated
  GET  /api/search?q=apple                find any stock or ETF on Yahoo
  GET  /api/runners?extra=STAK&min=10     small caps up 10%+ today, each with an entry, stop and targets
  GET  /api/news?symbols=AAPL,NVDA        headlines, newest first
  GET  /api/t212/status                   is Trading 212 linked?
  GET  /api/t212/portfolio                cash + positions from Trading 212
  POST /api/t212/connect                  {"key","secret","env","remember"}
  POST /api/t212/disconnect

Market data: Yahoo Finance's public chart and search endpoints (unofficial,
can lag). Trading 212: the official Public API, read-only. This server never
places, changes or cancels an order.

Trading 212 keys stay on your computer. They are read from the environment
(T212_API_KEY, T212_API_SECRET, T212_ENV=demo|live) or from
dashboard/.t212.json (written only when you tick "remember", mode 0600,
git-ignored). They are never sent to the browser.

The server listens on 127.0.0.1 only and refuses requests whose Host or
Origin is not this machine, so other websites cannot read your portfolio.
"""

import argparse
import base64
import hashlib
import hmac
import secrets
import socket
import calendar
import datetime
import email.utils
import concurrent.futures
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
CRED_FILE = os.path.join(HERE, ".t212.json")
ACCESS_FILE = os.path.join(HERE, ".access.json")  # phone mode secret, git-ignored
UA = "Mozilla/5.0 (compatible; day-trader-skill-dashboard/1.0; +https://github.com/Jakeschincariol/day-trader-skill)"

with open(os.path.join(HERE, "universe.json")) as _f:
    UNIVERSE = json.load(_f)
with open(os.path.join(HERE, "etf_lookthrough.json")) as _f:
    LOOKTHROUGH = json.load(_f)

# ---------------------------------------------------------------- caching

_cache = {}
_cache_lock = threading.Lock()


def cached(key, ttl, fn):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = fn()
    with _cache_lock:
        _cache[key] = (time.time(), val)
    return val


def purge(test):
    """Drop cached entries whose key matches test(key), so the next read fetches fresh data."""
    with _cache_lock:
        for k in [k for k in _cache if test(k)]:
            del _cache[k]


def purge_symbols(symbols):
    up = {x.upper() for x in symbols}
    nas = {x.replace("-", ".") for x in up}
    purge(lambda k: (k[0] in ("bars", "chart") and str(k[1]).upper() in up)
          or (k[0] == "nasdaq" and any("/%s/" % n in k[1].upper() for n in nas)))


def http_get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def yahoo(path):
    last = None
    for host in ("query1", "query2"):
        try:
            return http_get("https://%s.finance.yahoo.com%s" % (host, path))
        except Exception as e:  # try the other host once
            last = e
    raise last


# ---------------------------------------------------------------- indicators

def sma(xs, n):
    out, s = [None] * len(xs), 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(xs, n):
    out, k, prev = [None] * len(xs), 2.0 / (n + 1), None
    for i, x in enumerate(xs):
        if i < n - 1:
            continue
        prev = sum(xs[i - n + 1:i + 1]) / n if prev is None else x * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(xs, n=14):
    out = [None] * len(xs)
    if len(xs) <= n:
        return out
    gains = [max(xs[i] - xs[i - 1], 0) for i in range(1, len(xs))]
    losses = [max(xs[i - 1] - xs[i], 0) for i in range(1, len(xs))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(xs)):
        if i > n:
            ag = (ag * (n - 1) + gains[i - 1]) / n
            al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd(xs):
    e12, e26 = ema(xs, 12), ema(xs, 26)
    line = [a - b if a is not None and b is not None else None for a, b in zip(e12, e26)]
    start = next((i for i, v in enumerate(line) if v is not None), len(line))
    sig_part = ema(line[start:], 9) if len(line) - start >= 9 else [None] * (len(line) - start)
    signal = [None] * start + sig_part
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, signal)]
    return line, signal, hist


def atr(h, l, c, n=14):
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    out = [None] * len(c)
    if len(c) < n:
        return out
    prev = sum(tr[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(c)):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


def r(x, d=2):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, d)


# ---------------------------------------------------------------- market data

def get_bars(symbol, rng="2y"):
    def load():
        q = urllib.parse.quote(symbol)
        data = yahoo("/v8/finance/chart/%s?range=%s&interval=1d&includePrePost=false" % (q, rng))
        res = (data.get("chart") or {}).get("result") or []
        if not res:
            raise ValueError("no data for %s" % symbol)
        res = res[0]
        meta = res.get("meta", {})
        ts = res.get("timestamp") or []
        qt = (res.get("indicators", {}).get("quote") or [{}])[0]
        bars = []
        for i, t in enumerate(ts):
            o, h, l, c, v = (qt.get(k, [None] * len(ts))[i] for k in ("open", "high", "low", "close", "volume"))
            if None in (o, h, l, c):
                continue
            bars.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v or 0})
        if len(bars) < 2:
            raise ValueError("not enough history for %s" % symbol)
        # the chart endpoint's live price is fresher than the last daily bar
        live = meta.get("regularMarketPrice")
        if live and abs(bars[-1]["c"] - live) / live < 0.25:
            bars[-1]["c"] = live
            bars[-1]["h"] = max(bars[-1]["h"], live)
            bars[-1]["l"] = min(bars[-1]["l"], live)
        return {
            "meta": {
                "symbol": meta.get("symbol", symbol),
                "name": meta.get("longName") or meta.get("shortName") or symbol,
                "currency": meta.get("currency"),
                "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
                "type": meta.get("instrumentType"),
                "prevClose": meta.get("chartPreviousClose") if rng == "1d" else None,
                "high52": meta.get("fiftyTwoWeekHigh"),
                "low52": meta.get("fiftyTwoWeekLow"),
                "marketTime": meta.get("regularMarketTime"),
                "tradingPeriod": (meta.get("currentTradingPeriod") or {}).get("regular"),
            },
            "bars": bars,
        }
    return cached(("bars", symbol, rng), 120, load)


BENCH = {".L": "^FTSE", ".DE": "^GDAXI", ".PA": "^FCHI", ".AS": "^AEX", ".MI": "FTSEMIB.MI", ".SW": "^SSMI", ".MC": "^IBEX"}


def benchmark_for(symbol):
    """The index a stock is compared with: its home market, else the S&P 500."""
    s = symbol.upper()
    for suf, idx in BENCH.items():
        if s.endswith(suf.upper()):
            return idx
    return "SPY"


def spy_return_63():
    try:
        c = [b["c"] for b in get_bars("SPY")["bars"]]
        return c[-1] / c[-64] - 1 if len(c) > 64 else None
    except Exception:
        return None


def _day(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def bench_by_day(symbol, rng="2y"):
    """{YYYY-MM-DD: close} for the stock's benchmark index."""
    b = benchmark_for(symbol)
    try:
        return b, {_day(x["t"]): x["c"] for x in get_bars(b, rng)["bars"]}
    except Exception:
        return b, {}


def indicators(bars):
    c = [b["c"] for b in bars]
    h = [b["h"] for b in bars]
    l = [b["l"] for b in bars]
    v = [b["v"] for b in bars]
    ml, ms, mh = macd(c)
    vprev = [None] * len(v)  # 20-day average volume of the days BEFORE i (today's partial volume left out)
    s = 0.0
    for i in range(len(v)):
        if i >= 20:
            vprev[i] = s / 20
            s -= v[i - 20]
        s += v[i]
    return {"t": [b["t"] for b in bars], "o": [b["o"] for b in bars], "c": c, "h": h, "l": l, "v": v,
            "s20": sma(c, 20), "s50": sma(c, 50), "s200": sma(c, 200), "rsi": rsi(c),
            "macd": ml, "signal": ms, "hist": mh, "atr": atr(h, l, c), "vprev": vprev}


def rule(ind, i, bench63=None, vol_frac=1.0):
    """The rating and entry verdict at bar i. Used live (last bar) and by the backtest (every bar)."""
    c, h, l, v = ind["c"], ind["h"], ind["l"], ind["v"]
    price, prev = c[i], c[i - 1]
    at = lambda key, k=0: ind[key][i - k] if i - k >= 0 else None
    reasons, score, maxpts = [], 0.0, 0.0

    def sig(points, ok, good, bad):
        nonlocal score, maxpts
        if ok is None:  # not enough history: the check neither earns nor costs points
            return
        maxpts += abs(points)
        if ok:
            score += points
            reasons.append({"ok": True, "text": good, "pts": points})
        else:
            reasons.append({"ok": False, "text": bad, "pts": 0})

    a20, a50, a200 = at("s20"), at("s50"), at("s200")
    sig(2, None if a50 is None else price > a50, "Price above its 50-day average", "Price below its 50-day average")
    sig(2, None if a200 is None else price > a200, "Price above its 200-day average (long-term uptrend)",
        "Price below its 200-day average (long-term downtrend)")
    sig(1.5, None if a50 is None or a200 is None else a50 > a200, "50-day above 200-day average (golden cross zone)",
        "50-day below 200-day average (death cross zone)")
    sig(1, None if a20 is None else price > a20, "Price above its 20-day average (short-term strength)",
        "Price below its 20-day average (short-term weakness)")
    rv = at("rsi")
    if rv is not None:
        sig(1.5, 45 <= rv <= 68, "RSI %.0f: healthy momentum" % rv,
            "RSI %.0f: %s" % (rv, "overbought, stretched" if rv > 68 else "weak momentum"))
    hv, hp = at("hist"), at("hist", 1)
    sig(1, None if hv is None else hv > 0, "MACD above its signal line", "MACD below its signal line")
    sig(0.5, None if hv is None or hp is None else hv > hp, "MACD momentum rising", "MACD momentum fading")
    r63 = c[i] / c[i - 63] - 1 if i >= 63 else None
    sig(1, None if r63 is None else r63 > 0, "Up %.1f%% over 3 months" % (100 * (r63 or 0)),
        "Down %.1f%% over 3 months" % (-100 * (r63 or 0)))
    if r63 is not None and bench63 is not None:
        sig(1, r63 > bench63, "Beating its market index over 3 months", "Lagging its market index over 3 months")
    va = ind["vprev"][i]
    rvol = (v[i] / (va * max(0.1, vol_frac))) if va else None  # relative volume, scaled to the time of day
    if rvol is not None:
        sig(0.5, price > prev and rvol > 1.2, "Buyers stepping in: up day on above-average volume", "No volume confirmation today")
    pct = 100 * score / maxpts if maxpts else 50
    rating = ("Strong Buy" if pct >= 78 else "Buy" if pct >= 60 else "Hold" if pct >= 40 else "Sell" if pct >= 22 else "Strong Sell")

    av = at("atr") or price * 0.02
    hi20 = max(h[max(0, i - 20):i]) if i > 1 else price
    lo10 = min(l[max(0, i - 10):i + 1])
    downtrend = a50 is not None and a200 is not None and price < a50 and a50 < a200
    extended = (a20 is not None and price > a20 + 2 * av) or (rv is not None and rv > 72)
    breakout = price > hi20 and rvol is not None and rvol > 1.3 and pct >= 55 and not extended
    near20 = a20 is not None and abs(price - a20) <= 0.75 * av
    if downtrend:
        status, entry, trigger = "Avoid", None, a50
        why = "Downtrend: price is below the 50-day and the 50-day is below the 200-day. Wait for a close back above the 50-day average at %.2f." % a50
    elif extended:
        target = (a20 + 0.5 * av) if a20 else price - av
        entry, trigger = min(target, price - 0.5 * av), a20  # a limit always below the market
        status = "Wait: extended"
        why = "Price is stretched (%s). Chasing means a wide stop; a limit near %.2f is the better spot." % (
            ("%.1f ATRs above the 20-day average" % ((price - a20) / av)) if a20 and price > a20 + 2 * av else "RSI %.0f" % rv, entry)
    elif breakout:
        status, entry, trigger = "Buy now: breakout", price, hi20
        why = "Broke above the 20-day high (%.2f) on %.1fx normal volume. Breakouts work best bought the same day, not chased days later." % (hi20, rvol)
    elif near20 and pct >= 55 and (rv is None or rv < 65):
        status, entry, trigger = "Buy zone: pullback", price, a20
        why = "Uptrend pulled back to its 20-day average (%.2f). Buying the dip near support keeps the stop close." % a20
    elif pct >= 55:
        status, entry, trigger = "Watch", None, hi20
        why = "Trend is fine but price is between levels. Buy a pullback to %.2f or a breakout above %.2f on strong volume." % (a20 or price, hi20)
    elif pct < 35:
        status, entry, trigger = "Avoid", None, None
        why = "Weak trend and momentum (score %d of 100): no buy setup. Wait until it trades back above its 50-day average." % round(pct)
    else:
        status, entry, trigger = "No setup", None, None
        why = "Signals are mixed. No clear edge on either side right now."
    plan_px = entry or (trigger if status == "Watch" else None)
    plan = None
    if plan_px:
        stop = min(plan_px - 2 * av, lo10 - 0.1 * av) if status != "Wait: extended" else plan_px - 2 * av
        stop = max(stop, plan_px - 3 * av, plan_px * 0.85)  # never more than 3 ATR or 15% away
        risk = plan_px - stop
        plan = {"entry": r(plan_px), "stop": r(stop), "target1": r(plan_px + 2 * risk), "target2": r(plan_px + 3 * risk),
                "riskPct": r(100 * risk / plan_px, 1)}
        hi52 = max(h[max(0, i - 251):i + 1])
        if plan["target1"] and hi52 > plan_px and hi52 < plan["target1"]:
            plan["resistance"] = r(hi52)  # 52-week high sits between entry and target 1
    return {"pct": pct, "rating": rating, "reasons": reasons, "status": status, "why": why, "plan": plan,
            "atr": av, "rvol": rvol, "r63": r63, "rsi": rv, "a20": a20, "a50": a50, "a200": a200}


def _session_fraction(meta_period):
    """Share of today's regular session that has passed (1.0 when closed)."""
    try:
        start, end = meta_period["start"], meta_period["end"]
        now = time.time()
        if start < now < end:
            return max(0.05, (now - start) / float(end - start))
    except (TypeError, KeyError):
        pass
    return 1.0


EARN_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_earn_pending = set()


def next_earnings(symbol, wait=True):
    """{'date': 'YYYY-MM-DD', 'days': n} for the next report (US listings, Nasdaq.com), else None.

    wait=False never blocks: if the date isn't cached yet it is fetched in the
    background and shows up on the next refresh (keeps big lists fast)."""
    sym = symbol.upper()
    if not re.match(r"^[A-Z]{1,5}(-[A-Z])?$", sym):
        if not FMP["key"]:
            return None
        def fmp_load_e():
            try:
                return fmp_next_earnings(sym)
            except Exception:
                return None
        if not wait:
            with _cache_lock:
                hit = _cache.get(("earnings", sym))
            if not hit:
                if sym not in _earn_pending:
                    _earn_pending.add(sym)

                    def bgf():
                        try:
                            cached(("earnings", sym), 12 * 3600, fmp_load_e)
                        finally:
                            _earn_pending.discard(sym)
                    EARN_POOL.submit(bgf)
                return None
        e = cached(("earnings", sym), 12 * 3600, fmp_load_e)
        if not e:
            return None
        days = int((e["ts"] - calendar.timegm(time.gmtime()[:3] + (0, 0, 0, 0, 0, 0))) // 86400)
        return {"date": e["date"], "days": days} if days >= 0 else None
    if not wait:
        with _cache_lock:
            hit = _cache.get(("earnings", sym))
        if not hit or time.time() - hit[0] > 6 * 3600:
            if sym not in _earn_pending:
                _earn_pending.add(sym)

                def bg():
                    try:
                        next_earnings(sym, True)
                    finally:
                        _earn_pending.discard(sym)
                EARN_POOL.submit(bg)
            return None

    def load():
        try:
            d = nasdaq("analyst/%s/earnings-date" % sym.replace("-", "."), timeout=8)
        except Exception:
            return None
        m = re.search(r":\s*([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", d.get("announcement") or "")
        if not m:
            return None
        try:
            ts = calendar.timegm(time.strptime("%s %s %s" % m.groups(), "%b %d %Y"))
        except ValueError:
            return None
        return {"date": _day(ts), "ts": ts}
    e = cached(("earnings", sym), 6 * 3600, load)
    if not e:
        return None
    days = int((e["ts"] - calendar.timegm(time.gmtime()[:3] + (0, 0, 0, 0, 0, 0))) // 86400)
    return {"date": e["date"], "days": days} if days >= 0 else None


def market_regime():
    """Green / amber / red from the S&P 500 and Nasdaq 100 trends and the VIX."""
    def load():
        notes, pts = [], 0
        for sym, name in (("SPY", "S&P 500"), ("QQQ", "Nasdaq 100")):
            c = [b["c"] for b in get_bars(sym)["bars"]]
            a50, a200 = sum(c[-50:]) / 50, sum(c[-200:]) / 200
            ok50, ok200 = c[-1] > a50, c[-1] > a200
            pts += ok50 + ok200
            notes.append({"ok": ok50, "text": "%s %s its 50-day average" % (name, "above" if ok50 else "below")})
            notes.append({"ok": ok200, "text": "%s %s its 200-day average" % (name, "above" if ok200 else "below")})
        vc = [b["c"] for b in get_bars("^VIX")["bars"]]
        vix, vix20 = vc[-1], sum(vc[-20:]) / 20
        if vix < 20:
            pts += 1
            notes.append({"ok": True, "text": "VIX %.1f: calm market" % vix})
        elif vix > 28:
            pts -= 2
            notes.append({"ok": False, "text": "VIX %.1f: fear is high" % vix})
        else:
            notes.append({"ok": False, "text": "VIX %.1f: nervous market" % vix})
        if vix > 1.25 * vix20:
            pts -= 1
            notes.append({"ok": False, "text": "VIX jumped %.0f%% above its 20-day average" % (100 * (vix / vix20 - 1))})
        level = "green" if pts >= 4 else "amber" if pts >= 2 else "red"
        label = {"green": "Market healthy: trade normal size",
                 "amber": "Market mixed: be selective, consider half size",
                 "red": "Market weak: protect capital, new buys on hold"}[level]
        return {"level": level, "label": label, "score": pts, "max": 5, "notes": notes, "vix": r(vix)}
    try:
        return cached(("regime",), 300, load)
    except Exception:
        return {"level": "unknown", "label": "Market data unavailable", "notes": [], "score": None, "max": 5}


def analyse(symbol, with_series=False):
    data = get_bars(symbol)
    bars = data["bars"]
    ind = indicators(bars)
    c, h, l, v = ind["c"], ind["h"], ind["l"], ind["v"]
    i = len(c) - 1
    bname, bmap = bench_by_day(symbol)
    bench63 = None
    if bmap and symbol.upper() not in ("SPY", bname):
        bc = [bmap[k] for k in sorted(bmap)]
        bench63 = bc[-1] / bc[-64] - 1 if len(bc) > 64 else None
    frac = _session_fraction(data["meta"].get("tradingPeriod"))
    res = rule(ind, i, bench63, frac)
    status, why, plan = res["status"], res["why"], res["plan"]

    earn = next_earnings(symbol, wait=with_series)
    regime = market_regime() if symbol.upper() not in ("SPY", "QQQ", "^VIX") else None
    if earn and earn["days"] <= 7 and status.startswith("Buy"):
        status = "Wait: earnings"
        why = "Earnings %s (%s). A 2-ATR stop can't protect you from an overnight earnings gap: wait for the report, or size it small. Setup was: %s" % (
            "today" if earn["days"] == 0 else "in %d day%s" % (earn["days"], "s" if earn["days"] > 1 else ""), earn["date"], why)
    if regime and regime["level"] == "red" and status.startswith("Buy"):
        status = "Watch: market weak"
        why = "The setup is there, but the overall market is weak (%s). Most stocks fall with the market: wait for it to steady. Setup was: %s" % (
            "; ".join(n["text"] for n in regime["notes"] if not n["ok"])[:160], why)
    price, prev = c[i], c[i - 1]
    av = res["atr"]
    out = {
        "symbol": data["meta"]["symbol"],
        "name": data["meta"]["name"],
        "currency": data["meta"]["currency"],
        "exchange": data["meta"]["exchange"],
        "type": data["meta"]["type"],
        "price": r(price, 4 if price < 2 else 2),
        "change": r(price - prev, 4 if price < 2 else 2),
        "changePct": r(100 * (price / prev - 1)),
        "volume": v[i],
        "avgVolume": r(ind["vprev"][i], 0),
        "rvol": r(res["rvol"], 2),
        "high52": r(max(h[-252:])),
        "low52": r(min(l[-252:])),
        "ret1m": r(100 * (c[i] / c[i - 21] - 1)) if i >= 21 else None,
        "ret3m": r(100 * res["r63"]) if res["r63"] is not None else None,
        "ret1y": r(100 * (c[i] / c[max(0, i - 252)] - 1)),
        "rsi": r(res["rsi"], 1),
        "atr": r(av),
        "sma20": r(res["a20"]), "sma50": r(res["a50"]), "sma200": r(res["a200"]),
        "chandelier": r(max(c[-22:]) - 3 * av),
        "score": round(res["pct"]),
        "rating": res["rating"],
        "reasons": res["reasons"],
        "entryStatus": status,
        "entryWhy": why,
        "plan": plan,
        "earnings": earn,
        "regime": {"level": regime["level"], "label": regime["label"]} if regime else None,
        "benchmark": bname,
        "asOf": bars[-1]["t"],
    }
    if with_series:
        r2 = lambda xs, d=2: [r(x, d) for x in xs]
        out["series"] = {
            "t": ind["t"], "o": r2(ind["o"], 4), "h": r2(h, 4), "l": r2(l, 4), "c": r2(c, 4), "v": v,
            "sma20": r2(ind["s20"]), "sma50": r2(ind["s50"]), "sma200": r2(ind["s200"]),
            "rsi": r2(ind["rsi"], 1), "macd": r2(ind["macd"], 3), "signal": r2(ind["signal"], 3), "hist": r2(ind["hist"], 3),
        }
        out["forecast"] = forecast(c)
    return out


BT_COST = 0.004  # about 0.15% FX fee each way at Trading 212 plus about 0.1% spread


def backtest(symbol, hold=40):
    """Replay the same rules over 5 years: buy the next open after a 'Buy' verdict, exit at the stop,
    at 2R, or after `hold` days. One trade at a time; no costs, earnings or market filter."""
    def load():
        bars = get_bars(symbol, "5y")["bars"]
        ind = indicators(bars)
        _, bmap = bench_by_day(symbol, "5y")
        bdays = sorted(bmap)
        bidx = {d: k for k, d in enumerate(bdays)}
        o, c, h, l = ind["o"], ind["c"], ind["h"], ind["l"]
        n = len(c)
        trades, i = [], 260
        while i < n - 2:
            d = _day(ind["t"][i])
            k = bidx.get(d)
            b63 = bmap[bdays[k]] / bmap[bdays[k - 63]] - 1 if k is not None and k >= 63 else None
            res = rule(ind, i, b63)
            if not (res["status"].startswith("Buy") and res["plan"]):
                i += 1
                continue
            e, stop = o[i + 1], res["plan"]["stop"]
            if e <= stop:
                i += 1
                continue
            risk = e - stop
            tgt = e + 2 * risk
            exit_px, outcome, j = None, None, i + 1
            while j < n:
                if j > i + 1 and o[j] <= stop:
                    exit_px, outcome = o[j], "stop (gap)"
                elif l[j] <= stop:
                    exit_px, outcome = stop, "stop"
                elif h[j] >= tgt:
                    exit_px, outcome = (o[j] if o[j] > tgt and j > i + 1 else tgt), "target"
                elif j - i >= hold:
                    exit_px, outcome = c[j], "time"
                if exit_px is not None:
                    break
                j += 1
            if exit_px is None:  # still open at the end of the data
                break
            cost = BT_COST * e  # FX fee both ways plus spread, in price terms
            trades.append({"date": d, "setup": res["status"].split(": ")[-1], "entry": r(e), "exit": r(exit_px),
                           "R": round((exit_px - e - cost) / risk, 2), "days": j - i, "outcome": outcome})
            i = j + 1
        Rs = [t["R"] for t in trades]
        pos, neg = sum(x for x in Rs if x > 0), -sum(x for x in Rs if x < 0)
        eq, run = [], 0.0
        for x in Rs:
            run += x
            eq.append(round(run, 2))
        days = sorted(t["days"] for t in trades)
        return {
            "symbol": symbol, "years": round((ind["t"][-1] - ind["t"][0]) / 31557600.0, 1), "n": len(trades),
            "hitTarget": round(100.0 * sum(1 for t in trades if t["outcome"] == "target") / len(trades), 1) if trades else None,
            "winRate": round(100.0 * sum(1 for x in Rs if x > 0) / len(Rs), 1) if Rs else None,
            "expectancy": round(sum(Rs) / len(Rs), 2) if Rs else None,
            "profitFactor": round(pos / neg, 2) if neg else None,
            "medianDays": days[len(days) // 2] if days else None,
            "equity": eq, "trades": trades[-12:][::-1],
            "buyHold": round(100 * (c[-1] / c[260] - 1), 1) if n > 261 else None,
            "inMarket": round(100.0 * sum(t["days"] for t in trades) / max(1, n - 261), 0),
            "note": "Next-day open entry, stop or 2R target, %d-day time exit, 0.4%% costs per trade (FX fee and spread). Ignores earnings and the market filter." % hold,
        }
    return cached(("backtest", symbol, hold), 6 * 3600, load)


def forecast(closes, days=63, lookback=126, shrink=0.5):
    """Statistical projection, not a prediction.

    Centre: the last 6 months' log-linear trend, halved and capped at about
    +/-10% a year (trends fade).
    Bands: +/-1 and +/-2 standard deviations of daily log returns, widening
    with the square root of time (about 68% and 95% of outcomes if the
    recent volatility holds)."""
    xs = [math.log(x) for x in closes[-lookback:] if x and x > 0]
    n = len(xs)
    if n < 30:
        return None
    mx = (n - 1) / 2.0
    my = sum(xs) / n
    slope = sum((i - mx) * (y - my) for i, y in enumerate(xs)) / sum((i - mx) ** 2 for i in range(n))
    rets = [xs[i] - xs[i - 1] for i in range(1, n)]
    mu = sum(rets) / len(rets)
    sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / (len(rets) - 1))
    drift = max(-0.0004, min(0.0004, slope * shrink))  # at most about +/-10% a year: trends fade
    p0 = closes[-1]
    out = {"days": days, "mid": [], "lo1": [], "hi1": [], "lo2": [], "hi2": [],
           "drift": r(100 * (math.exp(drift * 252) - 1), 1), "vol": r(100 * sd * math.sqrt(252), 1)}
    for t in range(1, days + 1):
        m = math.log(p0) + drift * t
        w = sd * math.sqrt(t)
        out["mid"].append(r(math.exp(m), 4))
        out["lo1"].append(r(math.exp(m - w), 4))
        out["hi1"].append(r(math.exp(m + w), 4))
        out["lo2"].append(r(math.exp(m - 2 * w), 4))
        out["hi2"].append(r(math.exp(m + 2 * w), 4))
    for k in ("mid", "lo1", "hi1", "lo2", "hi2"):
        out[k + "End"] = out[k][-1]
    return out


POOL = concurrent.futures.ThreadPoolExecutor(max_workers=8)


def analyse_many(symbols):
    def one(s):
        try:
            return analyse(s)
        except Exception as e:
            return {"symbol": s, "error": str(e)[:200]}
    return list(POOL.map(one, symbols))


TAGS = [
    ("earnings", r"\bearnings\b|\bresults\b|\bEPS\b|\bguidance\b|\bquarter"),
    ("analyst", r"upgrade|downgrade|price target|outperform|underperform|\brating\b"),
    ("deal", r"\bacquir|\bmerger\b|\bbuyout\b|\bdeal\b|\bstake\b"),
    ("legal", r"lawsuit|\bsued\b|\bprobe\b|investigation|antitrust|\bcourt\b"),
    ("macro", r"\bFed\b|inflation|\bCPI\b|\brates?\b|jobs report|tariff|recession"),
]


def _rss(sym):
    url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s&region=US&lang=en-US" % urllib.parse.quote(sym)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        root = ET.fromstring(resp.read())
    out = []
    for it in root.iter("item"):
        when = it.findtext("pubDate")
        try:
            ts = int(email.utils.parsedate_to_datetime(when).timestamp()) if when else None
        except (TypeError, ValueError):
            ts = None
        out.append({"uuid": it.findtext("guid") or it.findtext("link"), "title": it.findtext("title") or "",
                    "summary": (it.findtext("description") or "")[:300], "link": it.findtext("link"),
                    "providerPublishTime": ts, "publisher": urllib.parse.urlparse(it.findtext("link") or "").hostname,
                    "relatedTickers": [sym]})
    return out


def _search_news(q):
    d = yahoo("/v1/finance/search?q=%s&quotesCount=0&newsCount=12" % urllib.parse.quote(q))
    return d.get("news") or []


def get_news(symbols):
    def one(q):
        is_sym = bool(re.match(r"^[A-Z0-9.\-^=]{1,12}$", q))
        try:
            return q, cached(("news", q), 300, lambda: _rss(q) if is_sym else _search_news(q))
        except Exception:
            return q, []
    seen, items = set(), []
    for q, news in POOL.map(one, symbols):
        for n in news:
            uid = n.get("uuid") or n.get("link")
            title = n.get("title", "")
            if uid in seen or not title:
                continue
            seen.add(uid)
            thumb = None
            for res in ((n.get("thumbnail") or {}).get("resolutions") or []):
                if res.get("width", 0) <= 200:
                    thumb = res.get("url")
            pub = (n.get("publisher") or "").replace("www.", "")
            items.append({
                "id": uid, "title": title, "summary": n.get("summary"), "publisher": pub, "link": n.get("link"),
                "time": n.get("providerPublishTime"), "thumb": thumb,
                "tickers": sorted(set(n.get("relatedTickers") or []))[:6],
                "tags": [name for name, pat in TAGS if re.search(pat, title + " " + (n.get("summary") or ""), re.I)],
            })
            items[-1]["mood"], items[-1]["impact"] = news_impact(title, n.get("summary") or "")
    items.sort(key=lambda x: x.get("time") or 0, reverse=True)
    return items[:100]


# ---------------------------------------------------------------- intraday, performance

def _chart(symbol, query, ttl):
    def load():
        d = yahoo("/v8/finance/chart/%s?%s" % (urllib.parse.quote(symbol), query))
        res = ((d.get("chart") or {}).get("result") or [None])[0]
        if not res:
            raise ValueError("no data for %s" % symbol)
        return res
    return cached(("chart", symbol, query), ttl, load)


def _rows(res):
    ts = res.get("timestamp") or []
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    out = []
    for i, t in enumerate(ts):
        o, h, l, c, v = (q.get(k, [None] * len(ts))[i] for k in ("open", "high", "low", "close", "volume"))
        if None in (o, h, l, c):
            continue
        out.append((t, o, h, l, c, v or 0))
    return out


def intraday(symbol):
    """Today in 5-minute bars, the last 7 days in hourly bars, and hourly levels for the last session."""
    now = int(time.time())
    d1 = _chart(symbol, "range=1d&interval=5m&includePrePost=false", 60)
    d7 = _chart(symbol, "period1=%d&period2=%d&interval=1h&includePrePost=false" % (now - 8 * 86400, now), 120)
    meta = d1.get("meta", {})
    gmt = meta.get("gmtoffset") or 0
    pack = lambda rows: {"t": [x[0] for x in rows], "o": [r(x[1], 4) for x in rows], "h": [r(x[2], 4) for x in rows],
                         "l": [r(x[3], 4) for x in rows], "c": [r(x[4], 4) for x in rows], "v": [x[5] for x in rows]}
    r1, r7 = _rows(d1), _rows(d7)
    # keep 7 calendar days of hourly bars
    if r7:
        cut = r7[-1][0] - 7 * 86400
        r7 = [x for x in r7 if x[0] > cut]
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    # hourly levels for the latest session (exchange-local day)
    hourly = []
    if r7:
        last_day = time.gmtime(r7[-1][0] + gmt)[:3]
        ref = None
        for x in r7:
            if time.gmtime(x[0] + gmt)[:3] == last_day:
                base = ref if ref is not None else prev
                hourly.append({"t": x[0], "o": r(x[1], 4), "h": r(x[2], 4), "l": r(x[3], 4), "c": r(x[4], 4), "v": x[5],
                               "chgPct": r(100 * (x[4] / base - 1)) if base else None})
                ref = x[4]
    # daily summary of the 7-day window
    days = {}
    for x in r7:
        k = time.strftime("%Y-%m-%d", time.gmtime(x[0] + gmt))
        dd = days.setdefault(k, {"date": k, "o": x[1], "h": x[2], "l": x[3], "c": x[4], "v": 0, "t": x[0]})
        dd["h"], dd["l"], dd["c"], dd["v"] = max(dd["h"], x[2]), min(dd["l"], x[3]), x[4], dd["v"] + x[5]
    daylist = sorted(days.values(), key=lambda z: z["date"])
    for i, dd in enumerate(daylist):
        base = daylist[i - 1]["c"] if i else None
        dd["chgPct"] = r(100 * (dd["c"] / base - 1)) if base else None
        for k in ("o", "h", "l", "c"):
            dd[k] = r(dd[k], 4)
    return {"symbol": meta.get("symbol", symbol), "currency": meta.get("currency"), "gmtoffset": gmt,
            "tz": meta.get("exchangeTimezoneName"), "prevClose": prev, "day": pack(r1), "week": pack(r7),
            "hourly": hourly, "days": daylist}


def _ret_table(daily, weekly):
    """Returns over standard windows from daily (2y) and weekly (max) closes [(t, close)]."""
    if not daily:
        return {}
    t_end, last = daily[-1]

    def back(series, seconds):
        target = t_end - seconds
        prior = [c for t, c in series if t <= target]
        return prior[-1] if prior else None
    d = 86400
    y_start = time.mktime((time.gmtime(t_end).tm_year, 1, 1, 0, 0, 0, 0, 0, 0))
    ytd_base = [c for t, c in daily if t < y_start]
    out = {
        "1W": back(daily, 7 * d), "1M": back(daily, 30 * d), "3M": back(daily, 91 * d), "6M": back(daily, 182 * d),
        "YTD": ytd_base[-1] if ytd_base else None, "1Y": back(daily, 365 * d),
        "2Y": back(weekly or daily, 730 * d), "5Y": back(weekly, 1826 * d) if weekly else None,
        "Max": weekly[0][1] if weekly else daily[0][1],
    }
    return {k: (r(100 * (last / v - 1)) if v else None) for k, v in out.items()}


def performance(symbol):
    def series(sym):
        dres = _chart(sym, "range=2y&interval=1d", 600)
        wres = _chart(sym, "range=max&interval=1wk", 3600)
        daily = _adj(dres)  # dividends included
        weekly = _adj(wres)
        if daily and weekly and weekly[-1][0] < daily[-1][0]:
            weekly.append(daily[-1])
        return daily, weekly
    bench = benchmark_for(symbol)
    me, spy = POOL.map(lambda s: series(s), [symbol, bench if bench != symbol else "SPY"])
    first = me[1][0][0] if me[1] else None
    if first:  # same start for both, so "Max" compares like with like
        spy = ([x for x in spy[0] if x[0] >= first], [x for x in spy[1] if x[0] >= first])
    return {"symbol": symbol, "since": first, "returns": _ret_table(*me), "spy": _ret_table(*spy), "benchmark": bench, "totalReturn": True}


# ---------------------------------------------------------------- fundamentals (Nasdaq, US listings)

def nasdaq(path, ttl=6 * 3600, timeout=25):
    def load():
        d = http_get("https://api.nasdaq.com/api/" + path, headers={"User-Agent": "Mozilla/5.0 (compatible; day-trader-skill-dashboard/1.0)"}, timeout=timeout)
        return d.get("data") or {}
    return cached(("nasdaq", path), ttl, load)


def money_num(s):
    """'$109,417,000' -> 109417000.0, '-$4,508' -> -4508, '$143,756(m)' -> 143756e6, '--' -> None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    mult = 1e6 if s.endswith("(m)") else 1.0
    m = re.search(r"(-?)\$?(-?)([\d,]+(?:\.\d+)?)", s)
    if not m:
        return None
    v = float(m.group(3).replace(",", ""))
    return -v * mult if (m.group(1) or m.group(2)) else v * mult


def _table(tb):
    """Nasdaq table -> ({row label: [v2, v3, v4, v5]}, [header dates])."""
    hdr = tb.get("headers") or {}
    cols = [k for k in ("value2", "value3", "value4", "value5") if k in hdr]
    rows = {}
    for row in tb.get("rows") or []:
        rows[row.get("value1", "").strip()] = [row.get(k) for k in cols]
    return rows, [hdr[k] for k in cols]


def _fiscal_quarters(data):
    """Revenue & EPS table -> [{date, label, fy, q, revenue, eps}] oldest first."""
    tb = (data or {}).get("revenueTable") or {}
    hdr = tb.get("headers") or {}
    cols = [k for k in ("value2", "value3", "value4") if k in hdr]
    years = {k: (re.search(r"(\d{4})", hdr[k]) or [None, None])[1] for k in cols}
    out, qn, rev = [], 0, {}
    for row in tb.get("rows") or []:
        label = (row.get("value1") or "").strip()
        if label not in ("Revenue", "EPS", "Dividends", "Total"):
            qn += 1
            rev = {}
            continue
        if label == "Revenue":
            rev = {k: money_num(row.get(k)) for k in cols}
        elif label == "EPS":
            for k in cols:
                txt = row.get(k) or ""
                m = re.search(r"(-?\$?-?[\d.]+)\s*\((\d\d)/(\d\d)/(\d{4})\)", txt)
                if not m or qn > 4:
                    continue
                eps = money_num(m.group(1))
                date = "%s-%s-%s" % (m.group(4), m.group(2), m.group(3))
                fy = years.get(k)
                out.append({"date": date, "fy": fy, "q": qn, "label": "Q%d FY%s" % (qn, (fy or "")[-2:]),
                            "eps": eps, "revenue": rev.get(k)})
    out.sort(key=lambda x: x["date"])
    for i, x in enumerate(out):
        prev = next((y for y in out[:i] if y["q"] == x["q"] and y["fy"] and x["fy"] and int(y["fy"]) == int(x["fy"]) - 1), None)
        x["epsYoY"] = r(100 * (x["eps"] / prev["eps"] - 1), 1) if prev and prev["eps"] and prev["eps"] > 0 and x["eps"] is not None else None
        x["revYoY"] = r(100 * (x["revenue"] / prev["revenue"] - 1), 1) if prev and prev.get("revenue") and x.get("revenue") else None
    return out


def fundamentals(symbol):
    sym = symbol.upper()
    if not re.match(r"^[A-Z]{1,5}(-[A-Z])?$", sym):
        return {"symbol": symbol, "available": False, "why": "Fundamentals cover US-listed stocks only."}
    nsym = sym.replace("-", ".")
    paths = {
        "summary": "quote/%s/summary?assetclass=stocks" % nsym,
        "revenue": "company/%s/revenue?limit=1" % nsym,
        "finq": "company/%s/financials?frequency=2" % nsym,
        "fina": "company/%s/financials?frequency=1" % nsym,
        "forecast": "analyst/%s/earnings-forecast" % nsym,
        "target": "analyst/%s/targetprice" % nsym,
        "peg": "analyst/%s/peg-ratio" % nsym,
        "edate": "analyst/%s/earnings-date" % nsym,
    }

    def get(item):
        k, p = item
        try:
            return k, nasdaq(p)
        except Exception:
            return k, {}
    D = dict(POOL.map(get, paths.items()))
    summ = (D["summary"].get("summaryData") or {})
    sv = lambda k: (summ.get(k) or {}).get("value")
    if not summ and not D["finq"]:
        return {"symbol": sym, "available": False, "why": "No fundamentals found for %s (ETFs and funds have none)." % sym}
    try:
        price = analyse(sym)["price"]
    except Exception:
        price = money_num(sv("PreviousClose"))

    quarters = _fiscal_quarters(D["revenue"])
    eps_ttm = sum(x["eps"] for x in quarters[-4:]) if len(quarters) >= 4 and all(x["eps"] is not None for x in quarters[-4:]) else None

    inc, qdates = _table(D["finq"].get("incomeStatementTable") or {})
    bal, _ = _table(D["finq"].get("balanceSheetTable") or {})
    cfa, _ = _table(D["fina"].get("cashFlowTable") or {})
    inca, adates = _table(D["fina"].get("incomeStatementTable") or {})
    K = 1000.0  # Nasdaq statements are in thousands

    def col(rows, name, i=0):
        v = rows.get(name)
        return money_num(v[i]) * K if v and i < len(v) and money_num(v[i]) is not None else None

    def ttm(rows, name):
        v = [col(rows, name, i) for i in range(4)]
        return sum(v) if all(x is not None for x in v) else None
    rev_ttm, ni_ttm = ttm(inc, "Total Revenue"), ttm(inc, "Net Income")
    op_ttm = ttm(inc, "Operating Income")
    equity, assets = col(bal, "Total Equity"), col(bal, "Total Assets")
    debt = sum(x for x in (col(bal, "Short-Term Debt / Current Portion of Long-Term Debt"), col(bal, "Long-Term Debt")) if x)
    cash = sum(x for x in (col(bal, "Cash and Cash Equivalents"), col(bal, "Short-Term Investments")) if x)
    dep = col(cfa, "Depreciation")
    ocf, capex = col(cfa, "Net Cash Flow-Operating"), col(cfa, "Capital Expenditures")
    mcap = money_num(sv("MarketCap"))
    ev = mcap + debt - cash if mcap else None
    ebitda = (op_ttm + dep) if op_ttm is not None and dep is not None else None

    fc_rows = ((D["forecast"].get("quarterlyForecast") or {}).get("rows") or [])
    forecasts = [{"fiscalEnd": x.get("fiscalEnd"), "eps": x.get("consensusEPSForecast"), "high": x.get("highEPSForecast"),
                  "low": x.get("lowEPSForecast"), "n": x.get("noOfEstimates")} for x in fc_rows]
    fwd_eps = sum(x["eps"] for x in forecasts[:4]) if len(forecasts) >= 4 and all(isinstance(x["eps"], (int, float)) for x in forecasts[:4]) else None
    co = D["target"].get("consensusOverview") or {}
    peg = (D["peg"].get("pegr") or {}).get("pegValue")
    edate = D["edate"].get("announcement") or ""
    m = re.search(r":\s*(.+)$", edate)

    def ratio(a, b):
        return r(a / b) if a is not None and b not in (None, 0) else None

    def pct_(a, b):
        return r(100 * a / b) if a is not None and b not in (None, 0) else None

    def rev_vs_earn(rows, dates, n):
        out = []
        for i in range(min(n, len(dates))):
            rv, ni = col(rows, "Total Revenue", i), col(rows, "Net Income", i)
            out.append({"period": dates[i], "revenue": rv, "netIncome": ni, "margin": pct_(ni, rv)})
        return list(reversed(out))

    return {
        "symbol": sym, "available": True, "price": price,
        "sector": sv("Sector"), "industry": sv("Industry"),
        "valuation": {
            "marketCap": mcap, "enterpriseValue": ev,
            "peTTM": ratio(price, eps_ttm) if eps_ttm and 0 < eps_ttm < price else None,  # EPS above price = share-class mismatch
            "forwardPE": ratio(price, fwd_eps) if fwd_eps and fwd_eps > 0 else None,
            "peg": peg or None, "priceSales": ratio(mcap, rev_ttm), "priceBook": ratio(mcap, equity),
            "evRevenue": ratio(ev, rev_ttm), "evEbitda": ratio(ev, ebitda),
        },
        "highlights": {
            "profitMargin": pct_(ni_ttm, rev_ttm), "operatingMargin": pct_(op_ttm, rev_ttm),
            "roa": pct_(ni_ttm, assets), "roe": pct_(ni_ttm, equity),
            "revenueTTM": rev_ttm, "netIncomeTTM": ni_ttm, "epsTTM": r(eps_ttm) if eps_ttm is not None else None,
            "totalCash": cash or None, "totalDebt": debt or None, "debtEquity": pct_(debt, equity),
            "freeCashFlow": (ocf + capex) if ocf is not None and capex is not None else None,
            "fcfPeriod": adates[0] if adates else None,
            "dividendYield": sv("Yield"), "dividend": sv("AnnualizedDividend"), "exDividend": sv("ExDividendDate"),
        },
        "analyst": {"low": co.get("lowPriceTarget"), "avg": co.get("priceTarget"), "high": co.get("highPriceTarget"),
                    "buy": co.get("buy"), "hold": co.get("hold"), "sell": co.get("sell"),
                    "upside": pct_((co.get("priceTarget") or 0) - price, price) if co.get("priceTarget") and price else None},
        "nextEarnings": m.group(1).strip() if m else None,
        "earnings": quarters[-8:] if not (eps_ttm and price and eps_ttm > price) else [],
        "forecasts": forecasts[:4],
        "revVsEarnings": {"quarterly": rev_vs_earn(inc, qdates, 4), "annual": rev_vs_earn(inca, adates, 4)},
        "source": "Nasdaq.com (Zacks estimates)",
    }


# ---------------------------------------------------------------- AI multibagger radar

RADAR_WINNERS = ["NVDA", "MU", "SNDK", "ASML", "WDC", "PLTR", "APP", "AVGO",
                 "LLY", "VST", "AXON", "CELH", "HOOD"]  # big winners outside AI too: health, power, defense, consumer, finance
RADAR_THEMES = {
    "Memory & storage": ["MU", "SNDK", "WDC", "STX"],
    "Chip equipment": ["ASML", "AMAT", "LRCX", "KLAC", "TER", "ONTO", "ACMR"],
    "AI chips": ["NVDA", "AMD", "AVGO", "MRVL", "ARM", "ALAB", "CRDO", "INTC"],
    "Networking & optics": ["ANET", "CIEN", "COHR", "LITE", "AAOI", "FN", "CLS"],
    "Power & data centers": ["VRT", "VST", "CEG", "OKLO", "NBIS", "CRWV", "IREN", "BE"],
    "Quantum & space": ["IONQ", "RGTI", "QBTS", "RKLB", "ASTS"],
    "AI software": ["PLTR", "APP", "SNOW", "CRWD", "NET", "DDOG"],
    # every other sector
    "Healthcare & biotech": ["LLY", "NVO", "VRTX", "REGN", "ISRG", "ABBV", "BSX", "HIMS", "VKTX", "ARGX"],
    "Energy: oil & gas": ["XOM", "CVX", "COP", "OXY", "EOG", "SLB", "FANG"],
    "Clean energy & nuclear": ["NEE", "FSLR", "ENPH", "CCJ", "LEU", "NXT", "SMR"],
    "Defense & aerospace": ["LMT", "RTX", "NOC", "GD", "LHX", "AXON", "KTOS", "HWM"],
    "Banks & fintech": ["JPM", "GS", "V", "MA", "HOOD", "COIN", "SOFI", "NU", "IBKR"],
    "Consumer & retail": ["COST", "AMZN", "WMT", "CELH", "ELF", "CMG", "ONON", "DECK", "LULU"],
    "Industrials & infrastructure": ["GE", "CAT", "ETN", "PWR", "URI", "DE", "GEV"],
    "Materials & mining": ["FCX", "NEM", "SCCO", "MP", "ALB", "AEM"],
    "Software & internet": ["MSFT", "GOOGL", "META", "NOW", "SHOP", "MELI", "UBER", "SPOT"],
}
AI_RADAR_THEMES = {"Memory & storage", "Chip equipment", "AI chips", "Networking & optics", "Power & data centers", "Quantum & space", "AI software"}
# more listings of the same themes, for portfolio checks (not scanned by the radar)
LT_EXTRA_THEMES = {
    "Memory & storage": ["000660.KS", "HY9H.F", "HY9H.DE", "005930.KS"],
    "Chip equipment": ["ASM.AS", "ASMIY", "6857.T", "ATEYY", "AMKR", "BESI.AS", "ASMI.AS", "8035.T"],
    "AI chips": ["TSM", "2330.TW", "QCOM", "SMTC", "MPWR", "SMCI", "IFX.DE", "STMPA.PA"],
    "Networking & optics": ["CSCO", "NOK", "ERIC"],
    "Power & data centers": ["APLD", "CORZ", "GEV", "ETN", "NRG", "TLN", "SMR", "PWR", "SU.PA", "SIE.DE"],
}
# themes that rise and fall together with AI spending
AI_BUILDOUT = {"Memory & storage": "AI build-out", "Chip equipment": "AI build-out", "AI chips": "AI build-out",
               "Networking & optics": "AI build-out", "Power & data centers": "AI build-out"}
FEATURES = [  # (key, label, scale used to compare)
    ("r3", "3-month return", 0.30), ("r6", "6-month return", 0.50), ("r12", "12-month return", 0.80),
    ("rs6", "Beat S&P (6m)", 0.40), ("fromHigh", "Near 52-week high", 0.15), ("d200", "Above 200-day avg", 0.30),
    ("slope50", "50-day trend slope", 0.08), ("volr", "Rising volume", 0.40), ("vola", "Volatility", 0.30),
]


def _features(c, v, i, spy_at):
    """Price-pattern features at bar i (needs ~260 bars of history)."""
    if i < 260:
        return None
    s50 = sum(c[i - 49:i + 1]) / 50
    s50p = sum(c[i - 69:i - 19]) / 50
    s200 = sum(c[i - 199:i + 1]) / 200
    rets = [math.log(c[k] / c[k - 1]) for k in range(i - 62, i + 1) if c[k - 1] > 0]
    mu = sum(rets) / len(rets)
    vol50 = sum(v[i - 49:i + 1]) / 50
    vol200 = sum(v[i - 199:i + 1]) / 200
    r6 = c[i] / c[i - 126] - 1
    spy6 = spy_at(i, 126)
    return {
        "r3": c[i] / c[i - 63] - 1, "r6": r6, "r12": c[i] / c[i - 252] - 1,
        "rs6": r6 - spy6 if spy6 is not None else 0.0,
        "fromHigh": c[i] / max(c[i - 251:i + 1]) - 1, "d200": c[i] / s200 - 1,
        "slope50": s50 / s50p - 1, "volr": (vol50 / vol200 - 1) if vol200 else 0.0,
        "vola": math.sqrt(sum((x - mu) ** 2 for x in rets) / (len(rets) - 1) * 252),
    }


def _series(sym, rng):
    rows = _rows(_chart(sym, "range=%s&interval=1d" % rng, 3600))
    return [x[0] for x in rows], [x[4] for x in rows], [x[5] for x in rows]


def _spy_lookup(rng):
    t, c, _ = _series("SPY", rng)

    def at(ts, back):
        # index of the last SPY bar at or before ts
        lo, hi = 0, len(t) - 1
        if not t or ts < t[0]:
            return None
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if t[mid] <= ts:
                lo = mid
            else:
                hi = mid - 1
        return c[lo] / c[lo - back] - 1 if lo >= back else None
    return at


def _launch(t, c, v, spy):
    """The first confirmed-uptrend day of the stock's best 12-month run.

    Confirmed uptrend: close above a rising 50-day average that is above the
    200-day. Among those days, take the one with the biggest gain over the next
    12 months, then walk back to the start of that uptrend stretch."""
    n = len(c)
    s50 = sma(c, 50)
    s200 = sma(c, 200)
    ok = [i >= 260 and s50[i] and s200[i] and c[i] > s50[i] > s200[i] and s50[i] > (s50[i - 10] or 0) for i in range(n)]
    best, bi = 0, None
    for i in range(260, n - 20):
        if not ok[i]:
            continue
        fwd = max(c[i + 1:i + 253]) / c[i]
        if fwd > best:
            best, bi = fwd, i
    if bi is None:
        return None
    while bi > 260 and ok[bi - 1]:
        bi -= 1
    spy_at = lambda i, back: spy(t[i], back)
    end = min(n - 1, bi + 252)
    path = [round(c[k] / c[bi], 4) for k in range(bi, end + 1, 5)]
    peak = max(c[bi:end + 1]) / c[bi] - 1
    return {"i": bi, "date": time.strftime("%Y-%m-%d", time.gmtime(t[bi])), "price": r(c[bi]),
            "gain12": r(100 * (c[end] / c[bi] - 1), 0), "peak12": r(100 * peak, 0),
            "features": _features(c, v, bi, spy_at), "path": path}


def radar_winners():
    def load():
        spy = _spy_lookup("10y")
        out = []
        for sym in RADAR_WINNERS:
            try:
                t, c, v = _series(sym, "10y")
                L = _launch(t, c, v, spy)
                if L and L["features"]:
                    L.update(symbol=sym, now=r(c[-1]), sinceLaunch=r(100 * (c[-1] / c[L["i"]] - 1), 0))
                    L.pop("i")
                    out.append(L)
            except Exception:
                continue
        return out
    return cached(("radar-winners",), 12 * 3600, load)


def _growth(fa):
    """0-100 growth score from reported and forecast earnings, plus the reasons."""
    if not fa or not fa.get("available"):
        return None, []
    pts, why = [], []
    q = fa.get("earnings") or []
    last = q[-1] if q else {}
    prev = q[-2] if len(q) > 1 else {}
    rev = last.get("revYoY")
    if rev is not None:
        pts.append(min(1.0, max(0.0, rev / 80.0)))
        why.append(("Revenue %+.0f%% vs a year ago" % rev, rev >= 20))
    eps = last.get("epsYoY")
    if eps is not None:
        pts.append(min(1.0, max(0.0, eps / 150.0)))
        why.append(("EPS %+.0f%% vs a year ago" % eps, eps >= 25))
    if rev is not None and prev.get("revYoY") is not None:
        acc = rev > prev["revYoY"]
        pts.append(1.0 if acc else 0.2)
        why.append(("Revenue growth %s (%.0f%% then %.0f%%)" % ("accelerating" if acc else "slowing", prev["revYoY"], rev), acc))
    v, h = fa.get("valuation") or {}, fa.get("highlights") or {}
    fc = fa.get("forecasts") or []
    if h.get("epsTTM") and len(fc) >= 4 and all(isinstance(x.get("eps"), (int, float)) for x in fc[:4]) and h["epsTTM"] > 0:
        fg = 100 * (sum(x["eps"] for x in fc[:4]) / h["epsTTM"] - 1)
        pts.append(min(1.0, max(0.0, fg / 100.0)))
        why.append(("Analysts expect EPS %+.0f%% next 4 quarters" % fg, fg >= 25))
    if h.get("operatingMargin") is not None:
        pts.append(min(1.0, max(0.0, h["operatingMargin"] / 35.0)))
        why.append(("Operating margin %.0f%%" % h["operatingMargin"], h["operatingMargin"] >= 15))
    up = (fa.get("analyst") or {}).get("upside")
    if up is not None:
        pts.append(min(1.0, max(0.0, up / 60.0)))
        why.append(("Analyst target %+.0f%% from here" % up, up >= 15))
    if len(pts) < 3:  # too little data to judge growth fairly
        return None, why + [("Not enough earnings data for a growth score", False)]
    return round(100 * sum(pts) / len(pts)), why


def radar():
    def load():
        winners = radar_winners()
        if not winners:
            raise ValueError("could not load the reference winners")
        def median(xs):
            xs = sorted(xs)
            m = len(xs) // 2
            return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2
        # median, so one extreme run (a fresh spin-off up 1,000%) can't drag the profile
        prof = {k: median([w["features"][k] for w in winners]) for k, _, _ in FEATURES}
        spy = _spy_lookup("2y")
        theme_of = {}
        for th, syms in RADAR_THEMES.items():
            for s in syms:
                theme_of.setdefault(s, th)
        syms = list(theme_of)

        def one(sym):
            try:
                t, c, v = _series(sym, "2y")
                f = _features(c, v, len(c) - 1, lambda i, back: spy(t[i], back))
                if not f:
                    return None
                d2 = sum(((f[k] - prof[k]) / sc) ** 2 for k, _, sc in FEATURES) / len(FEATURES)
                sim = round(100 * math.exp(-d2 / 3))
                try:
                    fa = fundamentals(sym)
                except Exception:
                    fa = None
                g, gwhy = _growth(fa)
                score = round(0.55 * sim + 0.45 * (g if g is not None else 35))  # missing growth data counts as below average
                stage = ("Late: already ran" if f["r12"] > 2.5 else "Extended" if f["fromHigh"] > -0.03 and f["d200"] > 0.6
                         else "Launch pattern" if sim >= 55 and f["r12"] < 1.0 else "Building" if sim >= 40 else "Not yet")
                close = sorted(FEATURES, key=lambda x: abs((f[x[0]] - prof[x[0]]) / x[2]))
                match = [lab for k, lab, sc in close[:3]]
                miss = [lab for k, lab, sc in close[-2:]]
                meta = {}
                try:
                    meta = get_bars(sym)["meta"]
                except Exception:
                    pass
                return {
                    "symbol": sym, "name": meta.get("name") or sym, "theme": theme_of[sym], "price": r(c[-1]),
                    "group": "AI & tech" if theme_of[sym] in AI_RADAR_THEMES else "Other sectors",
                    "currency": meta.get("currency"), "changePct": r(100 * (c[-1] / c[-2] - 1)),
                    "features": {k: r(x, 4) for k, x in f.items()}, "similarity": sim, "growth": g, "score": score,
                    "growthWhy": [{"text": a, "ok": b} for a, b in gwhy], "stage": stage,
                    "matches": match, "differs": miss,
                    "upside": (fa or {}).get("analyst", {}).get("upside") if fa and fa.get("available") else None,
                    "targetHigh": (fa or {}).get("analyst", {}).get("high") if fa and fa.get("available") else None,
                    "isPastWinner": sym in RADAR_WINNERS,
                    "spark": [r(x) for x in c[-126::3]],
                }
            except Exception:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as outer:  # own pool: one() uses POOL inside
            rows = [x for x in outer.map(one, syms) if x]
        rows.sort(key=lambda x: -x["score"])
        themes = {}
        for x in rows:
            themes.setdefault(x["theme"], []).append(x["score"])
        return {
            "asOf": int(time.time()), "profile": {k: r(x, 4) for k, x in prof.items()},
            "features": [{"key": k, "label": lab, "scale": sc} for k, lab, sc in FEATURES],
            "winners": winners, "candidates": rows,
            "themes": sorted([{"theme": k, "avg": round(sum(v) / len(v)), "n": len(v), "top": max(v),
                               "group": "AI & tech" if k in AI_RADAR_THEMES else "Other sectors"} for k, v in themes.items()], key=lambda x: -x["avg"]),
        }
    return cached(("radar",), 1800, load)


# ---------------------------------------------------------------- Trading 212 (read-only)

T212 = {"key": None, "secret": None, "env": "demo"}
_t212_lock = threading.Lock()


def load_creds():
    if os.environ.get("T212_API_KEY"):
        T212.update(key=os.environ["T212_API_KEY"], secret=os.environ.get("T212_API_SECRET"),
                    env=os.environ.get("T212_ENV", "live"))
        return
    try:
        with open(CRED_FILE) as f:
            d = json.load(f)
        T212.update(key=d.get("key"), secret=d.get("secret"), env=d.get("env", "live"))
    except (OSError, ValueError):
        pass


def t212_get(path):
    if not T212["key"]:
        raise PermissionError("Trading 212 is not linked")
    base = "https://%s.trading212.com/api/v0" % ("demo" if T212["env"] == "demo" else "live")
    if T212["secret"]:
        auth = "Basic " + base64.b64encode(("%s:%s" % (T212["key"], T212["secret"])).encode()).decode()
    else:  # older single-key style
        auth = T212["key"]
    return http_get(base + path, headers={"Authorization": auth}, timeout=20)


def t212_try(*paths):
    last = None
    for p in paths:
        try:
            return t212_get(p)
        except urllib.error.HTTPError as e:
            if e.code in (404, 405):
                last = e
                continue
            raise
    raise last


SUFFIX = {"l": ".L", "d": ".DE", "p": ".PA", "a": ".AS", "m": ".MI", "e": ".MC", "s": ".SW", "b": ".BR"}


def t212_to_yahoo(t):
    m = re.match(r"^([A-Za-z0-9.]+?)_(US)_EQ$", t)
    if m:
        return m.group(1).replace(".", "-")
    m = re.match(r"^([A-Z0-9.]+)([a-z])_EQ$", t)
    if m:
        return m.group(1) + SUFFIX.get(m.group(2), "")
    return t.split("_")[0]


def num(*xs):
    for x in xs:
        if isinstance(x, (int, float)):
            return x
    return None


def t212_portfolio():
    def load():
        with _t212_lock:
            info = {}
            try:
                info = t212_get("/equity/account/info")
            except Exception:
                pass
            cash = t212_try("/equity/account/cash", "/equity/account/summary")
            raw = t212_try("/equity/portfolio", "/equity/positions")
        positions = []
        for p in raw if isinstance(raw, list) else raw.get("items", []):
            inst = p.get("instrument") or {}
            ticker = p.get("ticker") or inst.get("ticker") or ""
            qty = num(p.get("quantity"))
            avg = num(p.get("averagePrice"), p.get("averagePricePaid"))
            cur = num(p.get("currentPrice"))
            wi = p.get("walletImpact") or {}
            ppl = num(p.get("ppl"), wi.get("unrealizedProfitLoss"))
            value = num(wi.get("currentValue"))
            positions.append({
                "t212": ticker, "symbol": t212_to_yahoo(ticker), "name": inst.get("name"),
                "qty": qty, "avgPrice": avg, "price": cur, "ppl": ppl, "fxPpl": num(p.get("fxPpl")),
                "value": value, "currency": inst.get("currency") or inst.get("currencyCode"),
                "opened": p.get("initialFillDate") or p.get("createdAt"),
            })
        cash_out = {
            "free": num(cash.get("free"), (cash.get("cash") or {}).get("availableToTrade")),
            "total": num(cash.get("total"), cash.get("totalValue")),
            "invested": num(cash.get("invested"), (cash.get("investments") or {}).get("totalCost")),
            "ppl": num(cash.get("ppl"), (cash.get("investments") or {}).get("unrealizedProfitLoss")),
            "result": num(cash.get("result"), (cash.get("investments") or {}).get("realizedProfitLoss")),
        }
        try:
            pending = t212_pending()
        except Exception:
            pending = None  # older keys may lack the orders permission
        return {"env": T212["env"], "currency": info.get("currencyCode") or cash.get("currency"),
                "cash": cash_out, "positions": positions, "pending": pending, "fetched": int(time.time())}
    return cached(("t212", T212["key"], T212["env"]), 15, load)


# ---------------------------------------------------------------- portfolio history

_orders = {"key": None, "items": [], "next": "/equity/history/orders?limit=50", "done": False, "at": 0}


def _iso_ts(s):
    if not s:
        return None
    try:
        s = re.sub(r"(\.\d+)?(Z|[+-]\d\d:?\d\d)?$", "", str(s))
        return int(calendar.timegm(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")))
    except ValueError:
        try:
            return int(calendar.timegm(time.strptime(s[:10], "%Y-%m-%d")))
        except ValueError:
            return None


def t212_orders(max_pages=5):
    """Filled orders from Trading 212's history, loaded a few pages per call (the API allows 6 calls a minute)."""
    key = (T212["key"], T212["env"])
    with _t212_lock:
        if _orders["key"] != key:
            _orders.update(key=key, items=[], next="/equity/history/orders?limit=50", done=False, at=0)
        if _orders["done"] and time.time() - _orders["at"] < 1800:
            return _orders["items"], True
        if _orders["done"]:  # refresh newest page only
            _orders.update(next="/equity/history/orders?limit=50", done=False)
            refresh = True
        else:
            refresh = False
        seen = {x["id"] for x in _orders["items"]}
        for _ in range(max_pages):
            path = _orders["next"]
            if not path:
                _orders["done"] = True
                break
            try:
                page = t212_get(path.replace("/api/v0", ""))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    break
                raise
            new = 0
            for it in page.get("items", []):
                o = _norm_order(it)
                if o and o["id"] not in seen:
                    seen.add(o["id"])
                    _orders["items"].append(o)
                    new += 1
            _orders["next"] = page.get("nextPagePath")
            if not _orders["next"] or (refresh and new == 0):
                _orders["done"] = True
                break
        _orders["at"] = time.time()
        return list(_orders["items"]), _orders["done"]


def _norm_order(it):
    order = it.get("order") or it
    fill = it.get("fill") or {}
    status = (order.get("status") or "FILLED").upper()
    if status not in ("FILLED", "PARTIALLY_FILLED"):
        return None
    ticker = order.get("ticker") or (order.get("instrument") or {}).get("ticker")
    qty = num(fill.get("quantity"), order.get("filledQuantity"))
    price = num(fill.get("price"), order.get("fillPrice"))
    if not ticker or not qty or not price:
        return None
    side = (order.get("side") or "").upper()
    if not side:
        sign_src = num(order.get("orderedQuantity"), order.get("filledQuantity"), order.get("orderedValue"), order.get("filledValue")) or 0
        side = "SELL" if sign_src < 0 else "BUY"
    ts = _iso_ts(fill.get("filledAt") or order.get("dateExecuted") or order.get("dateModified") or order.get("createdAt") or order.get("dateCreated"))
    if not ts:
        return None
    q = abs(qty)
    return {"id": str(fill.get("id") or order.get("fillId") or order.get("id")) + side, "symbol": t212_to_yahoo(ticker),
            "ts": ts, "qty": q if side == "BUY" else -q, "price": abs(price)}


def _daily_closes(symbol, start_ts):
    now = int(time.time())
    start = (start_ts - 10 * 86400) // 86400 * 86400
    res = _chart(symbol, "period1=%d&period2=%d&interval=1d" % (start, now), 1800)
    rows = _rows(res)
    ccy = res.get("meta", {}).get("currency")
    return {time.strftime("%Y-%m-%d", time.gmtime(x[0])): x[4] for x in rows}, ccy


def portfolio_history(lots, base="USD"):
    """lots: [{symbol, ts, qty (+buy/-sell), price (instrument currency)}] -> daily value vs invested."""
    lots = sorted([x for x in lots if x.get("symbol") and x.get("ts") and x.get("qty")], key=lambda x: x["ts"])
    if not lots:
        return {"dates": [], "value": [], "invested": [], "realized": [], "returns": {}, "warnings": []}
    first = lots[0]["ts"]
    syms = sorted({x["symbol"] for x in lots})
    warnings = []

    def load(sym):
        try:
            return sym, _daily_closes(sym, first)
        except Exception as e:
            return sym, (None, str(e))
    prices, ccys = {}, {}
    for sym, (series, ccy) in POOL.map(load, syms):
        if series:
            prices[sym], ccys[sym] = series, ccy
        else:
            warnings.append("No price history for %s" % sym)

    fx = {}
    for c in {c for c in ccys.values() if c}:
        unit, scale = (c, 1.0)
        if c in ("GBp", "GBX"):
            unit, scale = "GBP", 0.01
        if c in ("ZAc", "ILA"):
            unit, scale = ("ZAR" if c == "ZAc" else "ILS"), 0.01
        if unit == base:
            fx[c] = ({}, scale, 1.0)
            continue
        try:
            series, _ = _daily_closes("%s%s=X" % (unit, base), first)
            fx[c] = (series, scale, None)
        except Exception:
            fx[c] = ({}, scale, 1.0)
            warnings.append("No %s to %s exchange rate: %s shown unconverted" % (unit, base, unit))

    dates = sorted(set(d for s in prices.values() for d in s))
    by_day = {}
    for x in lots:
        d = time.strftime("%Y-%m-%d", time.gmtime(x["ts"]))
        nd = next((dd for dd in dates if dd >= d), None)
        if nd and x["symbol"] in prices:
            # London prices come in pence or pounds depending on the source: fix a x100 mismatch
            mkt = prices[x["symbol"]].get(nd) or next((v for k, v in sorted(prices[x["symbol"]].items()) if k >= nd and v), None)
            if mkt and x["price"]:
                ratio = x["price"] / mkt
                if 60 < ratio < 170:
                    x = dict(x, price=x["price"] / 100.0)
                elif 1 / 170.0 < ratio < 1 / 60.0:
                    x = dict(x, price=x["price"] * 100.0)
            by_day.setdefault(nd, []).append(x)

    last_px, last_fx = {}, {}
    hold, cost = {}, {}
    out = {"dates": [], "value": [], "invested": [], "realized": [], "flow": []}
    realized = 0.0
    for d in dates:
        for sym, s in prices.items():
            if d in s and s[d] is not None:
                last_px[sym] = s[d]
        for c, (series, scale, fixed) in fx.items():
            if fixed is not None:
                last_fx[c] = fixed * scale
            elif d in series and series[d]:
                last_fx[c] = series[d] * scale
            elif c not in last_fx and series:
                last_fx[c] = next(iter(series.values())) * scale
        flow = 0.0
        for x in by_day.get(d, []):
            sym = x["symbol"]
            rate = last_fx.get(ccys.get(sym), 1.0)
            amt = abs(x["qty"]) * x["price"] * rate
            h = hold.get(sym, 0.0)
            if x["qty"] > 0:
                hold[sym] = h + x["qty"]
                cost[sym] = cost.get(sym, 0.0) + amt
                flow += amt
            else:
                q = min(abs(x["qty"]), h) if h > 0 else 0.0
                avg = cost.get(sym, 0.0) / h if h > 0 else 0.0
                realized += q * x["price"] * rate - q * avg
                hold[sym] = h - q
                cost[sym] = cost.get(sym, 0.0) - q * avg
                flow -= q * x["price"] * rate
        value = sum(q * last_px.get(sym, 0) * last_fx.get(ccys.get(sym), 1.0) for sym, q in hold.items() if q > 1e-9)
        out["dates"].append(d)
        out["value"].append(round(value, 2))
        out["invested"].append(round(sum(v for k, v in cost.items() if hold.get(k, 0) > 1e-9), 2))
        out["realized"].append(round(realized, 2))
        out["flow"].append(round(flow, 2))
    out["returns"] = period_returns(out)
    out["warnings"] = warnings
    out["base"] = base
    out.update(_twr_stats(out))
    try:
        out.update(_bench_replay(out, base, first))
    except Exception:
        pass
    return out


def _twr_stats(h):
    """Time-weighted index (deposits removed), its yearly growth rate and worst fall."""
    V, F, dates = h["value"], h["flow"], h["dates"]
    idx, level, started = [], 1.0, False
    for i in range(len(V)):
        if i and V[i - 1] > 0:
            r_ = (V[i] - F[i]) / V[i - 1] - 1
            level *= 1 + r_
            started = True
        idx.append(level if started or V[i] > 0 else None)
    pts = [(d, x) for d, x in zip(dates, idx) if x is not None]
    if len(pts) < 2:
        return {}
    yrs = (calendar.timegm(time.strptime(pts[-1][0], "%Y-%m-%d")) - calendar.timegm(time.strptime(pts[0][0], "%Y-%m-%d"))) / 31557600.0
    total = pts[-1][1] / pts[0][1] - 1
    return {"twr": {"total": round(100 * total, 2), "cagr": round(100 * ((1 + total) ** (1 / yrs) - 1), 2) if yrs >= 1 else None,
                    "years": round(yrs, 1), "maxdd": round(100 * _max_drawdown([x for _, x in pts]), 2)}}


def _bench_replay(h, base, first, bench="VWRL.L"):
    """The same money, on the same days, put into a world index fund instead."""
    series, ccy = _daily_closes(bench, first)
    unit, scale = (ccy, 1.0) if ccy not in ("GBp", "GBX") else ("GBP", 0.01)
    fxs = {} if unit == base else _daily_closes("%s%s=X" % (unit, base), first)[0]
    units, out, px, rate = 0.0, [], None, None
    for d, f in zip(h["dates"], h["flow"]):
        px = series.get(d, px)
        rate = fxs.get(d, rate) if fxs else 1.0
        if px is None or rate is None:
            out.append(None)
            continue
        p = px * scale * rate
        units += f / p
        out.append(round(units * p, 2))
    return {"bench": out, "benchSymbol": bench, "benchName": "Vanguard FTSE All-World (VWRL)"}


def period_returns(h):
    """Gain in money and percent over standard windows (Modified Dietz, so buys and sells don't count as gains)."""
    dates, V, F = h["dates"], h["value"], h["flow"]
    n = len(dates)
    if n < 2:
        return {}
    end = dates[-1]
    ey, em, ed = (int(x) for x in end.split("-"))

    def shift(days=0, months=0, years=0):
        y, m = ey - years, em - months
        while m < 1:
            m += 12
            y -= 1
        t = calendar.timegm((y, m, min(ed, 28) if (months or years) else ed, 0, 0, 0)) - days * 86400
        return time.strftime("%Y-%m-%d", time.gmtime(t))
    starts = {"1D": dates[-2], "1W": shift(days=7), "1M": shift(months=1), "3M": shift(months=3),
              "YTD": "%04d-01-01" % ey, "1Y": shift(years=1), "5Y": shift(years=5)}
    out = {}
    for k, s in starts.items():
        prior = [i for i, d in enumerate(dates) if d <= s]
        i0 = prior[-1] if prior else None
        partial = False
        if i0 is None and k in ("1Y", "5Y", "YTD") and n > 1:
            i0, partial = 0, True  # history is shorter than the window: measure since the first buy
        if i0 is None or i0 >= n - 1:
            out[k] = None
            continue
        v0 = V[i0]
        flows = F[i0 + 1:]
        cf = sum(flows)
        weighted = sum(f * (len(flows) - j) / len(flows) for j, f in enumerate(flows)) if flows else 0.0
        gain = V[-1] - v0 - cf  # sells count as cash out, so realized gains are included
        denom = v0 + weighted
        out[k] = {"gain": round(gain, 2), "pct": round(100 * gain / denom, 2) if denom > 0 else None, "partial": partial}
    # all time: the same method from the first day, so every tile is comparable
    flows = F[1:]
    weighted = sum(f * (len(flows) - j) / len(flows) for j, f in enumerate(flows)) if flows else 0.0
    gain = V[-1] - V[0] - sum(flows)
    denom = V[0] + weighted
    out["Max"] = {"gain": round(gain, 2), "pct": round(100 * gain / denom, 2) if denom > 0 else None}
    return out


def build_lots(manual, include_t212=True, include_revolut=True):
    lots, notes = [], []
    base = None
    if include_revolut and os.path.exists(REVOLUT_FILE):
        try:
            rl, base = revolut_lots()
            lots += rl
        except Exception as e:
            notes.append("Revolut history unavailable (%s)" % str(e)[:80])
    for m in manual or []:
        try:
            ts = _iso_ts(m.get("date")) or int(time.time()) - 86400
            lots.append({"symbol": str(m["symbol"]).upper(), "ts": ts, "qty": float(m["qty"]), "price": float(m["avgPrice"])})
        except (KeyError, TypeError, ValueError):
            continue
    if include_t212 and T212["key"]:
        pf = t212_portfolio()
        base = pf.get("currency") or base
        try:
            orders, complete = t212_orders()
        except Exception as e:
            orders, complete = [], True
            notes.append("Trading 212 order history unavailable (%s): using each position's average price and first buy date" % str(e)[:80])
        if not complete:
            notes.append("Older Trading 212 orders are still loading (the API allows a few pages a minute). Refresh in a minute for the full history.")
        held = {}
        for o in orders:
            held[o["symbol"]] = held.get(o["symbol"], 0.0) + o["qty"]
        lots += orders
        for p in pf["positions"]:
            sym, qty = p["symbol"], p.get("qty") or 0
            gap = qty - held.get(sym, 0.0)
            if abs(gap) > 1e-6 and p.get("avgPrice"):
                first = min([o["ts"] for o in orders if o["symbol"] == sym] or [_iso_ts(p.get("opened")) or int(time.time()) - 365 * 86400])
                lots.append({"symbol": sym, "ts": first, "qty": gap, "price": p["avgPrice"]})
    return lots, base, notes


# ---------------------------------------------------------------- pending orders, journal, FX

def t212_pending():
    """Open (unfilled) orders, read-only: used to check every position has a protective stop."""
    def load():
        raw = t212_get("/equity/orders")
        out = []
        for o in raw if isinstance(raw, list) else raw.get("items", []):
            o = o.get("order") or o
            ticker = o.get("ticker") or (o.get("instrument") or {}).get("ticker") or ""
            qty = num(o.get("quantity"), o.get("orderedQuantity")) or 0
            side = (o.get("side") or ("SELL" if qty < 0 else "BUY")).upper()
            out.append({"symbol": t212_to_yahoo(ticker), "t212": ticker, "type": (o.get("type") or "").upper(),
                        "side": side, "qty": abs(qty), "stopPrice": num(o.get("stopPrice")),
                        "limitPrice": num(o.get("limitPrice")), "status": o.get("status")})
        return out
    return cached(("t212", "pending", T212["key"], T212["env"]), 15, load)


def trade_journal():
    """Closed trades from Trading 212 fills, matched first-in first-out, with summary stats."""
    orders, complete = t212_orders()
    lots, trades = {}, []
    for o in sorted(orders, key=lambda x: x["ts"]):
        q = lots.setdefault(o["symbol"], [])
        if o["qty"] > 0:
            q.append([o["qty"], o["price"], o["ts"]])
            continue
        left, cost, qty, first = -o["qty"], 0.0, 0.0, None
        while left > 1e-9 and q:
            lot = q[0]
            take = min(left, lot[0])
            cost += take * lot[1]
            qty += take
            first = first or lot[2]
            lot[0] -= take
            left -= take
            if lot[0] <= 1e-9:
                q.pop(0)
        if qty <= 0:
            continue  # sold shares bought before the loaded history
        entry = cost / qty
        pnl = qty * (o["price"] - entry)
        trades.append({"symbol": o["symbol"], "opened": _day(first), "closed": _day(o["ts"]), "qty": round(qty, 6),
                       "entry": round(entry, 4), "exit": round(o["price"], 4), "pnl": round(pnl, 2),
                       "pct": round(100 * (o["price"] / entry - 1), 2), "days": max(0, int((o["ts"] - first) // 86400))})
    pcts = [t["pct"] for t in trades]
    wins = [x for x in pcts if x > 0]
    losses = [x for x in pcts if x <= 0]
    months = {}
    for t in trades:
        m = months.setdefault(t["closed"][:7], {"month": t["closed"][:7], "n": 0, "wins": 0, "sumPct": 0.0})
        m["n"] += 1
        m["wins"] += t["pct"] > 0
        m["sumPct"] += t["pct"]
    open_lots = [{"symbol": s, "qty": round(sum(l[0] for l in q), 6)} for s, q in lots.items() if sum(l[0] for l in q) > 1e-6]
    return {
        "complete": complete, "trades": trades[::-1],
        "stats": {
            "n": len(trades), "winRate": round(100.0 * len(wins) / len(pcts), 1) if pcts else None,
            "avgWin": round(sum(wins) / len(wins), 2) if wins else None,
            "avgLoss": round(sum(losses) / len(losses), 2) if losses else None,
            "expectancy": round(sum(pcts) / len(pcts), 2) if pcts else None,
            "profitFactor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else None,
            "best": max(trades, key=lambda t: t["pct"]) if trades else None,
            "worst": min(trades, key=lambda t: t["pct"]) if trades else None,
            "avgDays": round(sum(t["days"] for t in trades) / len(trades), 1) if trades else None,
        },
        "months": sorted(months.values(), key=lambda m: m["month"]),
        "openLots": open_lots,
        "note": "Matched first-in first-out from your Trading 212 order history. P/L is in each stock's own currency; % figures are comparable across currencies.",
    }


def fx_rate(src, dst):
    """How many units of dst one unit of src buys (GBp and other minor units handled)."""
    scale = 1.0
    if src in ("GBp", "GBX"):
        src, scale = "GBP", 0.01
    if dst in ("GBp", "GBX"):
        dst, scale = "GBP", scale * 100
    src, dst = (src or "USD").upper(), (dst or "USD").upper()
    if src == dst:
        return scale
    try:
        return scale * get_bars("%s%s=X" % (src, dst))["bars"][-1]["c"]
    except Exception:
        return None


# ---------------------------------------------------------------- long-term investing

def _adj(res):
    """[(t, close)] using dividend-adjusted closes when Yahoo provides them (total return)."""
    ts = res.get("timestamp") or []
    adj = ((res.get("indicators", {}).get("adjclose") or [{}])[0]).get("adjclose")
    q = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    src = adj if adj and len(adj) == len(ts) else q
    return [(t, c) for t, c in zip(ts, src) if c]


def _lin(x, lo, hi):
    """Map x onto 0-100 between lo (0) and hi (100); works for falling scales too (lo > hi)."""
    if x is None:
        return None
    t = (x - lo) / float(hi - lo)
    return max(0.0, min(100.0, 100.0 * t))


def _max_drawdown(closes):
    peak, dd = None, 0.0
    for c in closes:
        peak = c if peak is None or c > peak else peak
        dd = min(dd, c / peak - 1)
    return dd


def lt_profile(symbol):
    """Long-term score (quality, growth, valuation, balance sheet, dividend, trend), buy zone and history."""
    sym = symbol.upper()

    def load():
        res = _chart(sym, "range=10y&interval=1d", 3600)
        meta = res.get("meta", {})
        adj = _adj(res)
        t = [x[0] for x in adj]
        c = [x[1] for x in adj]
        if len(c) < 60:
            raise ValueError("not enough history for %s" % sym)
        raw = [x[4] for x in _rows(res)]
        price = raw[-1] if raw else c[-1]
        n = len(c)

        def back(days):
            target = t[-1] - days * 86400
            prior = [i for i in range(n) if t[i] <= target]
            if prior:
                return prior[-1]
            return 0 if t[0] - target < 30 * 86400 else None  # history starts a few days late
        bname = benchmark_for(sym)
        try:
            bres = _chart(bname if bname != "SPY" else "SPY", "range=10y&interval=1d", 3600)
            badj = _adj(bres)
        except Exception:
            badj = []

        def bret(days_from, days_to=0):
            if not badj:
                return None
            bt = [x[0] for x in badj]
            def at(d):
                target = badj[-1][0] - d * 86400
                prior = [i for i in range(len(bt)) if bt[i] <= target]
                return badj[prior[-1]][1] if prior else None
            a, b = at(days_from), at(days_to)
            return b / a - 1 if a and b else None
        i12, i1 = back(365), back(30)
        mom = (c[i1] / c[i12] - 1) if i12 is not None and i1 is not None else None
        bmom = bret(365, 30)
        s200 = sum(c[-200:]) / 200 if n >= 200 else None
        i3y = back(3 * 365)
        dd3 = _max_drawdown(c[i3y:]) if i3y is not None else _max_drawdown(c)
        ath = max(c)
        dd_now = c[-1] / ath - 1
        hi52, lo52 = max(raw[-252:]), min(raw[-252:])
        z200 = price / (sum(raw[-200:]) / 200) - 1 if len(raw) >= 200 else None

        def cagr(years):
            i = back(int(years * 365.25))
            if i is None:
                return None
            yrs = (t[-1] - t[i]) / 31557600.0
            return (c[-1] / c[i]) ** (1 / yrs) - 1 if yrs > 0.5 else None
        hist = {"cagr1": cagr(1), "cagr3": cagr(3), "cagr5": cagr(5), "cagr10": cagr(10), "maxdd3": dd3, "fromATH": dd_now}

        fa = company_figures(sym)
        has_fa = bool(fa and fa.get("available"))
        groups, why = {}, []

        def add(group, label, value, score, fmtv):
            if score is None:
                return
            groups.setdefault(group, []).append(score)
            why.append({"group": group, "text": "%s %s" % (label, fmtv(value)), "score": round(score), "ok": score >= 50})
        pctf = lambda v: "%.1f%%" % (100 * v) if v is not None else "n/a"
        numf = lambda v: "%.2f" % v if v is not None else "n/a"
        if has_fa:
            v, h = fa["valuation"], fa["highlights"]
            roe = h.get("roe")
            add("Quality", "Return on equity", roe, _lin(roe, 8, 25) if roe is not None else None, lambda x: "%.0f%%" % x)
            om = h.get("operatingMargin")
            add("Quality", "Operating margin", om, _lin(om, 5, 30) if om is not None else None, lambda x: "%.0f%%" % x)
            fcf, rev = h.get("freeCashFlow"), h.get("revenueTTM")
            fcfm = fcf / rev if fcf is not None and rev else None
            add("Quality", "Free-cash-flow margin", fcfm, _lin(fcfm, 0, 0.20), pctf)
            ann = (fa.get("revVsEarnings") or {}).get("annual") or []
            prof = [x for x in ann if x.get("netIncome") is not None]
            if prof:
                share = sum(1 for x in prof if x["netIncome"] > 0) / float(len(prof))
                add("Quality", "Profitable years", share, 100 * share, lambda x: "%d of %d" % (round(x * len(prof)), len(prof)))
            revs = [x.get("revenue") for x in ann if x.get("revenue")]
            if len(revs) >= 3 and revs[0] > 0:
                g = (revs[-1] / revs[0]) ** (1.0 / (len(revs) - 1)) - 1
                add("Growth", "Revenue growth a year", g, _lin(g, 0, 0.15), pctf)
            eps_yoy = [q.get("epsYoY") for q in (fa.get("earnings") or [])[-4:] if q.get("epsYoY") is not None]
            if eps_yoy:
                e = sum(eps_yoy) / len(eps_yoy) / 100.0
                add("Growth", "EPS growth (last 4 quarters)", e, _lin(e, 0, 0.25), pctf)
            if v.get("peTTM") and v.get("forwardPE"):
                fg = v["peTTM"] / v["forwardPE"] - 1
                add("Growth", "Expected EPS growth next year", fg, _lin(fg, 0, 0.15), pctf)
            add("Valuation", "PEG ratio", v.get("peg"), _lin(v.get("peg"), 3, 1) if v.get("peg") else None, numf)
            mcap = v.get("marketCap")
            fy = fcf / mcap if fcf and mcap else None
            add("Valuation", "Free-cash-flow yield", fy, _lin(fy, 0.01, 0.06), pctf)
            up = (fa.get("analyst") or {}).get("upside")
            add("Valuation", "Analyst target upside", up, _lin(up, -10, 30) if up is not None else None, lambda x: "%+.0f%%" % x)
            de, cash, debt = h.get("debtEquity"), h.get("totalCash"), h.get("totalDebt")
            if cash and debt is not None and cash > debt:
                add("Balance sheet", "Net cash", cash - debt, 100.0, lambda x: big_num(x))
            elif de is not None:
                add("Balance sheet", "Debt / equity", de, _lin(de, 200, 30), lambda x: "%.0f%%" % x)
            dy = h.get("dividendYield")
            try:
                dyv = float(str(dy).strip("%")) if dy not in (None, "N/A", "") else None
            except ValueError:
                dyv = None
            if dyv:
                div = money_num(h.get("dividend"))
                payout = div / h["epsTTM"] if div and h.get("epsTTM") else None
                sc = _lin(dyv, 0, 4)
                if payout is not None and payout > 0.7:
                    sc *= 0.6
                add("Dividend", "Dividend yield", dyv, sc, lambda x: "%.2f%%%s" % (x, " (payout %.0f%%)" % (100 * payout) if payout else ""))
        else:
            c5 = hist["cagr5"] if hist["cagr5"] is not None else hist["cagr3"]
            add("Growth", "Total return a year (5y)" if hist["cagr5"] is not None else "Total return a year (3y)", c5, _lin(c5, 0, 0.12), pctf)
        rel = mom - bmom if mom is not None and bmom is not None else None
        add("Trend", "12-month return vs %s" % ("S&P 500" if bname == "SPY" else bname), rel, _lin(rel, -0.2, 0.2), lambda x: "%+.0f pts" % (100 * x))
        if s200:
            add("Trend", "Price vs 200-day average", c[-1] / s200 - 1, 100.0 if c[-1] > s200 else 0.0, pctf)
        add("Trend", "Worst fall in 3 years", dd3, _lin(dd3, -0.6, -0.2), pctf)
        W = {"Quality": 25, "Growth": 20, "Valuation": 20, "Balance sheet": 15, "Dividend": 5, "Trend": 15}
        if has_fa and "Dividend" not in groups:
            W["Growth"] += W.pop("Dividend")
        gs = {g: sum(x) / len(x) for g, x in groups.items()}
        wsum = sum(W[g] for g in gs if g in W)
        score = round(sum(gs[g] * W[g] for g in gs if g in W) / wsum) if wsum else None
        if has_fa:
            band = (None if score is None else "Core quality" if score >= 75 else "Good" if score >= 60 else "Fair" if score >= 45 else "Speculative")
        else:  # ETFs and non-US listings: judged on track record only
            band = (None if score is None else "Strong record" if score >= 75 else "Solid record" if score >= 60 else "Mixed record" if score >= 45 else "Weak record")
            if meta.get("instrumentType") not in ("ETF", "MUTUALFUND"):
                band = (band or "") + " · price only"  # no company figures for this listing

        # buy zone for accumulating
        pe_pct = None
        if has_fa and len(fa.get("earnings") or []) >= 7:
            q = fa["earnings"]
            pts = []
            for k in range(3, len(q)):
                ttm = sum(x["eps"] for x in q[k - 3:k + 1] if x.get("eps") is not None)
                ts_q = calendar.timegm(time.strptime(q[k]["date"], "%Y-%m-%d"))
                prior = [j for j in range(n) if t[j] <= ts_q]
                if ttm > 0 and prior:
                    pts.append(raw[min(prior[-1], len(raw) - 1)] / ttm if len(raw) == n else c[prior[-1]] / ttm)
            pe_now = fa["valuation"].get("peTTM")
            if len(pts) >= 4 and pe_now:
                pe_pct = round(100.0 * sum(1 for x in pts if x <= pe_now) / len(pts))
        reasons = []
        # on sale = the price itself has come down, not just "below an old peak" after a big run
        cheap = ((z200 is not None and z200 <= -0.05) or (pe_pct is not None and pe_pct <= 33)
                 or (dd_now <= -0.15 and (z200 is None or z200 <= 0.05)))
        dear = (z200 is not None and z200 >= 0.25) or (pe_pct is not None and pe_pct >= 90 and ((fa or {}).get("analyst") or {}).get("upside", 0) < 0)
        if z200 is not None:
            reasons.append("%s%% %s its 200-day average" % (abs(round(100 * z200)), "above" if z200 >= 0 else "below"))
        reasons.append("at its all-time high" if dd_now > -0.01 else "%d%% below its all-time high" % round(-100 * dd_now))
        if pe_pct is not None:
            reasons.append("P/E in the %s of its ~2-year range" % ("bottom third" if pe_pct <= 33 else "top 10%" if pe_pct >= 90 else "middle"))
        if score is not None and score < 45 and has_fa:
            zone, zwhy = "Speculative", "Weak fundamentals or history: keep it a small satellite position, or research first."
        elif cheap and (score or 0) >= 60 and not has_fa and meta.get("instrumentType") not in ("ETF", "MUTUALFUND"):
            zone, zwhy = "Accumulate", "Below its usual price, but scored on price history only (no company figures for this listing): keep to your regular amount."
        elif cheap and (score or 0) >= 60:
            zone, zwhy = "Accumulate+", "Good business on sale: a good month to add a bit more than usual."
        elif dear:
            zone, zwhy = "Stretched", "Price ran ahead of the business: keep buying small, no need to rush."
        else:
            zone, zwhy = "Accumulate", "Fair price: keep your regular monthly buy."
        return {
            "symbol": sym, "name": meta.get("longName") or meta.get("shortName") or sym, "currency": meta.get("currency"),
            "price": r(price, 4 if price < 2 else 2), "score": score, "band": band, "groups": {g: round(x) for g, x in gs.items()},
            "why": why, "zone": zone, "zoneWhy": zwhy, "zoneReasons": reasons, "pePercentile": pe_pct,
            "z200": r(100 * z200, 1) if z200 is not None else None, "fromATH": r(100 * dd_now, 1),
            "range52": r(100 * (price - lo52) / (hi52 - lo52), 0) if hi52 > lo52 else None,
            "history": {k: (r(100 * v, 1) if v is not None else None) for k, v in hist.items()},
            "fundamentals": has_fa, "benchmark": bname,
            "sector": ((fa or {}).get("sector") if has_fa else None) or (fdb_info(sym) or {}).get("sector"),
            "industry": (fdb_info(sym) or {}).get("industry") or (fa or {}).get("industry"),
            "country": (fdb_info(sym) or {}).get("country") or (fa or {}).get("country"),
            "figuresFrom": (fa or {}).get("source", "Nasdaq.com") if has_fa else None,
        }
    return cached(("lt", sym), 3 * 3600, load)


def big_num(x):
    return "%.1fB" % (x / 1e9) if abs(x) >= 1e9 else "%.0fM" % (x / 1e6)


def lt_many(symbols):
    def one(s):
        try:
            return lt_profile(s)
        except Exception as e:
            return {"symbol": s, "error": str(e)[:200]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:  # own pool: lt_profile uses POOL inside
        return list(ex.map(one, symbols))


def _irr(flows):
    """Annual money-weighted return from [(years_from_start, amount)] (negative = money in)."""
    def npv(rate):
        return sum(a / (1 + rate) ** y for y, a in flows)
    lo, hi = -0.99, 5.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def lt_backtest(symbol):
    """Buy-and-hold (1/3/5/10y) and monthly investing (5y) on dividend-adjusted prices, vs the benchmark."""
    sym = symbol.upper()

    def run(s):
        adj = _adj(_chart(s, "range=10y&interval=1d", 3600))
        t = [x[0] for x in adj]
        c = [x[1] for x in adj]
        out = {"lump": {}, "dca": None}
        for yrs in (1, 3, 5, 10):
            target = t[-1] - int(yrs * 365.25 * 86400)
            idx = [i for i in range(len(t)) if t[i] >= target]
            if not idx or (t[idx[0]] - target) > 20 * 86400:
                continue
            i0 = idx[0]
            span = (t[-1] - t[i0]) / 31557600.0
            yearly = {}
            for k in range(i0, len(t)):
                yearly.setdefault(time.gmtime(t[k]).tm_year, []).append(c[k])
            worst = min((v[-1] / v[0] - 1 for v in yearly.values() if len(v) > 20), default=None)
            out["lump"][str(yrs)] = {"total": r(100 * (c[-1] / c[i0] - 1), 1), "cagr": r(100 * ((c[-1] / c[i0]) ** (1 / span) - 1), 1),
                                     "maxdd": r(100 * _max_drawdown(c[i0:]), 1), "worstYear": r(100 * worst, 1) if worst is not None else None}
        start = t[-1] - int(5 * 365.25 * 86400)
        units, invested, flows, seen, path = 0.0, 0.0, [], set(), []
        for k in range(len(t)):
            if t[k] < start:
                continue
            ym = time.strftime("%Y-%m", time.gmtime(t[k]))
            if ym not in seen:
                seen.add(ym)
                units += 100.0 / c[k]
                invested += 100.0
                flows.append(((t[k] - start) / 31557600.0, -100.0))
            if k % 5 == 0 or k == len(t) - 1:
                path.append([time.strftime("%Y-%m-%d", time.gmtime(t[k])), round(invested, 2), round(units * c[k], 2)])
        if invested:
            value = units * c[-1]
            irr = _irr(flows + [((t[-1] - start) / 31557600.0, value)])
            yr = [k for k in range(len(t)) if t[k] >= start]
            ups = sum(1 for k in yr if k >= 252 and c[k] > c[k - 252])
            tot = sum(1 for k in yr if k >= 252)
            out["dca"] = {"months": len(seen), "invested": round(invested, 2), "value": round(value, 2),
                          "irr": r(100 * irr, 1) if irr is not None else None, "path": path,
                          "positiveYears": round(100.0 * ups / tot) if tot else None}
        return out

    def load():
        b = benchmark_for(sym)
        me, bench = POOL.map(run, [sym, b if b != sym else "SPY"])
        return {"symbol": sym, "benchmark": b, "me": me, "bench": bench,
                "note": "Dividends reinvested (adjusted prices). Monthly plan: 100 invested on the first trading day of each month for 5 years. Ignores fees, FX and taxes."}
    return cached(("ltbt", sym), 6 * 3600, load)


_divs = {"key": None, "items": [], "at": 0}


def t212_dividends(max_pages=4):
    """Dividends paid into the Trading 212 account (read-only)."""
    key = (T212["key"], T212["env"])
    with _t212_lock:
        if _divs["key"] == key and time.time() - _divs["at"] < 3600:
            return _divs["items"]
        items, path = [], "/history/dividends?limit=50"
        for _ in range(max_pages):
            try:
                page = t212_get(path.replace("/api/v0", ""))
            except urllib.error.HTTPError as e:
                if e.code in (404, 429):
                    break
                raise
            for d in page.get("items", []):
                ts = _iso_ts(d.get("paidOn") or d.get("paidAt") or d.get("createdAt"))
                amt = num(d.get("amount"), d.get("amountInEuro"))
                if ts and amt is not None:
                    items.append({"symbol": t212_to_yahoo(d.get("ticker") or ""), "ts": ts, "date": _day(ts), "amount": amt,
                                  "perShare": num(d.get("grossAmountPerShare")), "qty": num(d.get("quantity"))})
            path = page.get("nextPagePath")
            if not path:
                break
        _divs.update(key=key, items=items, at=time.time())
        return items


def dividend_summary():
    items = t212_dividends()
    now = time.time()
    year = time.gmtime().tm_year
    months, by_sym = {}, {}
    for d in items:
        m = d["date"][:7]
        months[m] = months.get(m, 0) + d["amount"]
        by_sym[d["symbol"]] = by_sym.get(d["symbol"], 0) + (d["amount"] if now - d["ts"] < 365 * 86400 else 0)
    return {"last12": round(sum(d["amount"] for d in items if now - d["ts"] < 365 * 86400), 2),
            "thisYear": round(sum(d["amount"] for d in items if d["date"].startswith(str(year))), 2),
            "total": round(sum(d["amount"] for d in items), 2),
            "months": [{"month": k, "amount": round(v, 2)} for k, v in sorted(months.items())][-24:],
            "bySymbol": sorted([{"symbol": k, "amount": round(v, 2)} for k, v in by_sym.items() if v], key=lambda x: -x["amount"]),
            "recent": sorted(items, key=lambda x: -x["ts"])[:12]}


# ---------------------------------------------------------------- logos

LOGO_DIR = os.path.join(HERE, ".logo-cache")  # git-ignored; logos are their owners' trademarks
LOGO_SOURCES = ("https://financialmodelingprep.com/image-stock/%s.png",
                "https://assets.parqet.com/logos/symbol/%s?format=png")
_logo_lock = threading.Lock()


def _monogram(sym):
    """A generated badge for symbols without a logo (indices, FX, unknown tickers)."""
    label = re.sub(r"[^A-Z0-9]", "", sym.upper().split(".")[0].split("=")[0])[:3] or "?"
    hue = int(hashlib.md5(sym.encode()).hexdigest()[:4], 16) % 360
    size = 34 if len(label) <= 2 else 26
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" '
            'fill="hsl(%d,45%%,32%%)"/><text x="32" y="33" text-anchor="middle" dominant-baseline="central" '
            'font-family="Inter,Arial,sans-serif" font-weight="700" font-size="%d" fill="#fff">%s</text></svg>' % (hue, size, label)).encode()


def get_logo(symbol):
    """(bytes, content_type) from the disk cache, the logo sources, or a monogram."""
    sym = symbol.upper()
    if not re.match(r"^[A-Z0-9.\-^=]{1,15}$", sym):
        return _monogram("?"), "image/svg+xml"
    if sym.startswith("^") or "=" in sym:
        return _monogram(sym), "image/svg+xml"
    os.makedirs(LOGO_DIR, exist_ok=True)
    safe = re.sub(r"[^A-Z0-9_-]", "_", sym)
    png, miss = os.path.join(LOGO_DIR, safe + ".png"), os.path.join(LOGO_DIR, safe + ".miss")
    now = time.time()
    if os.path.exists(png) and now - os.path.getmtime(png) < 30 * 86400:
        with open(png, "rb") as f:
            return f.read(), "image/png"
    if os.path.exists(miss) and now - os.path.getmtime(miss) < 7 * 86400:
        return _monogram(sym), "image/svg+xml"
    with _logo_lock:  # one fetch at a time: be gentle with the free sources
        for url in LOGO_SOURCES:
            try:
                req = urllib.request.Request(url % urllib.parse.quote(sym), headers={"User-Agent": UA, "Accept": "image/*"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    ctype = resp.headers.get("Content-Type", "")
                    data = resp.read(300000)
                if ctype.startswith("image/") and data[:8] == b"\x89PNG\r\n\x1a\n":
                    with open(png, "wb") as f:
                        f.write(data)
                    return data, "image/png"
            except Exception:
                continue
            finally:
                time.sleep(0.15)
        open(miss, "w").close()
    return _monogram(sym), "image/svg+xml"


# ---------------------------------------------------------------- live day trend, trending, directory

def spark(symbols):
    """Today's intraday closes (5-minute) plus price and change, for many symbols (Yahoo, 20 per request)."""
    out, need = {}, []
    for s in symbols:
        with _cache_lock:
            hit = _cache.get(("spark", s))
        if hit and time.time() - hit[0] < 60:
            out[s] = hit[1]
        else:
            need.append(s)

    def chunk(group):
        try:
            d = yahoo("/v8/finance/spark?symbols=%s&range=1d&interval=5m" % urllib.parse.quote(",".join(group), safe=","))
        except Exception:
            return {}
        res = {}
        for s in group:
            x = d.get(s) or {}
            closes = [c for c in (x.get("close") or []) if c is not None]
            prev = x.get("chartPreviousClose") or x.get("previousClose")
            price = x.get("fulldayPrice") or (closes[-1] if closes else None)
            if price is None:
                continue
            step = max(1, len(closes) // 60)
            res[s] = {"symbol": s, "price": r(price, 4 if price < 2 else 2), "prev": r(prev, 4) if prev else None,
                      "change": r(x.get("fulldayChange") if x.get("fulldayChange") is not None else (price - prev if prev else None), 4),
                      "changePct": r(x.get("fulldayChangePercent") if x.get("fulldayChangePercent") is not None else (100 * (price / prev - 1) if prev else None)),
                      "spark": [r(c, 4) for c in closes[::step]] + ([r(closes[-1], 4)] if closes and (len(closes) - 1) % step else []),
                      "time": x.get("end")}
        return res
    groups = [need[i:i + 20] for i in range(0, len(need), 20)]
    for res in POOL.map(chunk, groups):
        for s, v in res.items():
            with _cache_lock:
                _cache[("spark", s)] = (time.time(), v)
            out[s] = v
    names = directory_names()
    for s, v in out.items():
        v.setdefault("name", names.get(s))
    return [out[s] for s in symbols if s in out]


def trending(region="US", count=12):
    def load():
        d = yahoo("/v1/finance/trending/%s?count=%d" % (region, count + 6))
        quotes = (((d.get("finance") or {}).get("result") or [{}])[0]).get("quotes") or []
        return [q["symbol"] for q in quotes if q.get("symbol") and "=" not in q["symbol"] and not q["symbol"].startswith("^")][:count]
    syms = cached(("trending", region), 300, load)
    return spark(syms)


# ---------------------------------------------------------------- day runners (momentum scanner)
# Small caps up big today on heavy volume, each with a rule-based day-trade plan: entry, stop, two
# targets. The levels come from today's 5-minute bars (high of day, pre-market high, VWAP, recent
# lows). They are rules a momentum trader would follow, not a forecast.

RUNNER_LISTS = ("small_cap_gainers", "day_gainers", "most_actives", "aggressive_small_caps")
OTC = re.compile(r"OTC|PNK|Pink|Other OTC", re.I)


def _screen(scr_id):
    def load():
        d = yahoo("/v1/finance/screener/predefined/saved?scrIds=%s&count=100" % scr_id)
        return (((d.get("finance") or {}).get("result") or [{}])[0]).get("quotes") or []
    try:
        return cached(("screen", scr_id), 120, load)
    except Exception:
        return []


def _session(state):
    s = (state or "").upper()
    return "pre" if s in ("PRE", "PREPRE") else "open" if s == "REGULAR" else "closed"


def runner_quote(q):
    """A Yahoo screener quote in one shape. Pre-market, price and change are the pre-market ones."""
    state = q.get("marketState")
    price, prev, chg = q.get("regularMarketPrice"), q.get("regularMarketPreviousClose"), q.get("regularMarketChangePercent")
    if _session(state) == "pre" and q.get("preMarketPrice"):
        price, prev, chg = q["preMarketPrice"], q.get("regularMarketPrice"), q.get("preMarketChangePercent")
    vol, avg = q.get("regularMarketVolume") or 0, q.get("averageDailyVolume3Month") or q.get("averageDailyVolume10Day")
    return {"symbol": q.get("symbol"), "name": q.get("longName") or q.get("shortName") or q.get("symbol"),
            "price": price, "prev": prev, "changePct": chg, "volume": vol, "avgVolume": avg,
            "relVol": r(vol / avg, 1) if avg else None, "shares": q.get("sharesOutstanding"), "marketCap": q.get("marketCap"),
            "exchange": q.get("fullExchangeName") or q.get("exchange"), "type": q.get("quoteType"), "state": state}


def runner_ok(x, min_pct=10):
    """Worth a look: a listed stock (not OTC), $0.50 or more, up min_pct% or more, real volume."""
    if x.get("type") not in (None, "EQUITY") or OTC.search(x.get("exchange") or ""):
        return False
    if not x.get("price") or x["price"] < 0.5 or (x.get("changePct") or 0) < min_pct:
        return False
    return _session(x.get("state")) == "pre" or (x.get("volume") or 0) >= 300000


def runner_levels(rows, prev, gmtoffset, session):
    """Plan from today's 5-minute bars [(t, o, h, l, c, v)] (pre-market included).

    Setups, in the order a momentum trader checks them:
      pre       pre-market: buy only above the pre-market high
      breakout  above VWAP and within 3% of the high of day: buy the break of the high
      pullback  above VWAP, 3-20% under the high: buy the first 5-minute candle to make a new high
      below     under VWAP: no trade unless it gets back above VWAP
      faded     25%+ under the high of day (or 15%+ and under VWAP): the move is over for today
      next      market closed: tomorrow, buy only above today's high
    Stop: the lowest low of the last 30 minutes (at least 1.5% below entry). Targets: 2R and 3R."""
    if not rows:
        return None
    day = time.gmtime(rows[-1][0] + gmtoffset)[:3]
    rows = [x for x in rows if time.gmtime(x[0] + gmtoffset)[:3] == day]
    mins = lambda t: (lambda g: g.tm_hour * 60 + g.tm_min)(time.gmtime(t + gmtoffset))
    pre = [x for x in rows if mins(x[0]) < 570]
    reg = [x for x in rows if 570 <= mins(x[0]) < 960]
    base = reg or pre or rows
    last = rows[-1][4] if session != "closed" or not reg else reg[-1][4]
    hod, lod = max(x[2] for x in base), min(x[3] for x in base)
    pm_high = max((x[2] for x in pre), default=None)
    vv = sum(x[5] for x in base)
    vwap = sum((x[2] + x[3] + x[4]) / 3 * x[5] for x in base) / vv if vv else None
    rngs = [x[2] - x[3] for x in base[-12:]]
    atr5 = sum(rngs) / len(rngs) if rngs else 0
    tick = 0.01 if last >= 1 else 0.0001
    from_high = last / hod - 1 if hod else 0
    under_vwap = vwap is not None and last < vwap

    if session == "pre" and not reg:
        setup, entry = "pre", (pm_high or hod) + tick
    elif from_high <= -0.25 or (from_high <= -0.15 and under_vwap):
        setup, entry = "faded", None
    elif session == "closed":
        setup, entry = "next", hod + tick
    elif under_vwap:
        setup, entry = "below", vwap + tick
    elif from_high >= -0.03:
        setup, entry = "breakout", hod + tick
    else:
        setup, entry = "pullback", base[-1][2] + tick  # break of the latest 5-minute candle

    plan = None
    if entry:
        recent = [x[3] for x in base[-6:]]
        stop = min(min(recent), entry * 0.985)
        if session == "closed" and vwap and vwap < entry:
            stop = min(stop, vwap)  # overnight: give it room down to today's VWAP
        stop = min(stop, entry - max(atr5, tick))
        risk = entry - stop
        d = 4 if entry < 2 else 2
        plan = {"entry": r(entry, d), "stop": r(stop, d), "t1": r(entry + 2 * risk, d), "t2": r(entry + 3 * risk, d),
                "riskPct": r(100 * risk / entry, 1), "wide": risk / entry > 0.12}
    d = 4 if last < 2 else 2
    return {"setup": setup, "last": r(last, d), "hod": r(hod, d), "lod": r(lod, d), "pmHigh": r(pm_high, d),
            "vwap": r(vwap, d), "fromHighPct": r(100 * from_high, 1), "gapPct": r(100 * (reg[0][1] / prev - 1), 1) if reg and prev else None,
            "highPct": r(100 * (hod / prev - 1), 1) if prev else None, "plan": plan,
            "spark": [r(x[4], 4) for x in base][-78:]}


def runner_score(x):
    """0-100: how much this looks like a stock that can keep running today (the classic momentum checklist)."""
    s, why = 0, []
    chg, rv, sh, px = x.get("changePct") or 0, x.get("relVol"), x.get("shares"), x.get("price") or 0
    if chg >= 40: s += 25; why.append("up %d%% today" % chg)
    elif chg >= 20: s += 18; why.append("up %d%% today" % chg)
    elif chg >= 10: s += 10
    if rv is not None:
        if rv >= 10: s += 25; why.append("%.0f× normal volume" % rv)
        elif rv >= 5: s += 18; why.append("%.0f× normal volume" % rv)
        elif rv >= 2: s += 8
    if sh:
        if sh < 20e6: s += 20; why.append("few shares (%.1fM)" % (sh / 1e6))
        elif sh < 50e6: s += 12
        elif sh < 100e6: s += 5
    if 1 <= px <= 20: s += 10
    elif 0.5 <= px < 1 or 20 < px <= 50: s += 4
    if x.get("news"): s += 10; why.append("fresh news")
    lv = x.get("levels") or {}
    if lv.get("setup") in ("breakout", "pullback", "pre", "next"): s += 10
    elif lv.get("setup") in ("faded", "below"): s -= 15
    return max(0, min(100, s)), why


def _runner_detail(x):
    try:
        res = _chart(x["symbol"], "range=1d&interval=5m&includePrePost=true", 60)
        meta = res.get("meta", {})
        if x.get("price") is None:  # a ticker the user added: fill the quote from the chart
            x.update({"name": meta.get("longName") or meta.get("shortName") or x["symbol"], "price": meta.get("regularMarketPrice"),
                      "prev": meta.get("chartPreviousClose") or meta.get("previousClose"), "volume": meta.get("regularMarketVolume") or 0,
                      "exchange": meta.get("fullExchangeName")})
            if x["price"] and x["prev"]:
                x["changePct"] = r(100 * (x["price"] / x["prev"] - 1))
        x["levels"] = runner_levels(_rows(res), x.get("prev"), meta.get("gmtoffset") or 0, _session(x.get("state")))
    except Exception as e:
        x["levels"], x["error"] = None, str(e)[:120]
    try:
        cut = time.time() - 36 * 3600
        news = [n for n in cached(("news", x["symbol"]), 300, lambda: _rss(x["symbol"])) if (n.get("providerPublishTime") or 0) > cut]
        x["news"] = [{"title": n.get("title"), "link": n.get("link"), "time": n.get("providerPublishTime"),
                      "publisher": (n.get("publisher") or "").replace("www.", "")} for n in news[:3]]
    except Exception:
        x["news"] = []
    x["score"], x["why"] = runner_score(x)
    return x


def runners(extra=(), min_pct=10, limit=20):
    """Today's runners, best first, plus any tickers the user added (always shown, marked mine)."""
    def load():
        seen, rows = set(), []
        for quotes in POOL.map(_screen, RUNNER_LISTS):
            for q in quotes:
                x = runner_quote(q)
                if x["symbol"] and x["symbol"] not in seen and runner_ok(x, min_pct):
                    seen.add(x["symbol"])
                    rows.append(x)
        state = next((x["state"] for x in rows if x.get("state")), None)
        if state is None:
            state = next((q.get("marketState") for q in _screen(RUNNER_LISTS[0])), None)
        rows.sort(key=lambda x: -(x["changePct"] or 0) * min(x.get("relVol") or 1, 20))
        rows = rows[:limit]
        for s in extra:
            if s not in seen:
                rows.append({"symbol": s, "price": None, "prev": None, "changePct": None, "relVol": None, "shares": None, "state": state})
        mine = set(extra)
        for x in rows:
            x["mine"] = x["symbol"] in mine
            x.setdefault("state", state)
        out = list(POOL.map(_runner_detail, rows))
        out.sort(key=lambda x: (not x["mine"], -x["score"]))
        return {"session": _session(state), "marketState": state, "asOf": int(time.time()), "minPct": min_pct, "rows": out}
    return cached(("runners", tuple(extra), min_pct), 60, load)


DIR_FILE = os.path.join(HERE, ".symbols-cache.json")  # git-ignored, refreshed daily
with open(os.path.join(HERE, "world.json")) as _f:
    WORLD = json.load(_f)
EXCH = {"Q": "Nasdaq", "N": "NYSE", "A": "NYSE American", "P": "NYSE Arca", "Z": "Cboe BZX", "V": "IEX"}
SKIP_NAME = re.compile(r"\b(warrants?|rights?|units?|notes? due|debentures?|preferred|pfd|%|depositary shares? each representing a fraction)\b", re.I)
_dir_lock = threading.Lock()
_dir = {"at": 0, "rows": [], "names": {}}


def _load_directory():
    """Every US-listed stock and ETF (Nasdaq Trader symbol directory) plus the curated world list."""
    rows = []
    if os.path.exists(DIR_FILE) and time.time() - os.path.getmtime(DIR_FILE) < 86400:
        with open(DIR_FILE) as f:
            rows = json.load(f)
    else:
        try:
            for fname, sym_col, exch in (("nasdaqlisted.txt", "Symbol", None), ("otherlisted.txt", "ACT Symbol", "Exchange")):
                req = urllib.request.Request("https://www.nasdaqtrader.com/dynamic/SymDir/" + fname, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=40) as resp:
                    lines = resp.read().decode("utf-8", "replace").splitlines()
                head = lines[0].split("|")
                for line in lines[1:]:
                    rec = dict(zip(head, line.split("|")))
                    sym, name = rec.get(sym_col, ""), rec.get("Security Name", "")
                    if not sym or rec.get("Test Issue") == "Y" or "File Creation" in sym or "$" in sym:
                        continue
                    if SKIP_NAME.search(name):
                        continue
                    if "." in sym:
                        base, cls_ = sym.split(".", 1)
                        if len(cls_) != 1:
                            continue
                        sym = base + "-" + cls_  # BRK.B -> BRK-B (Yahoo style)
                    name = re.sub(r"\s*-?\s*(Class [A-Z] )?(Common Stock|Ordinary Shares?|Common Shares|American Depositary Shares|Shares of Beneficial Interest)\b.*$", "", name).strip() or name
                    rows.append({"s": sym, "n": name[:90], "t": "ETF" if rec.get("ETF") == "Y" else "Stock",
                                 "x": "Nasdaq" if exch is None else EXCH.get(rec.get(exch), rec.get(exch)), "r": "United States"})
            tmp = DIR_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(rows, f)
            os.replace(tmp, DIR_FILE)
        except Exception:
            if os.path.exists(DIR_FILE):
                with open(DIR_FILE) as f:
                    rows = json.load(f)
    seen = {x["s"] for x in rows}
    for region, items in WORLD["regions"].items():
        for it in items:
            if it["s"] not in seen:
                rows.append({"s": it["s"], "n": it["n"], "t": it.get("t", "Stock"), "x": it.get("x", ""), "r": region})
                seen.add(it["s"])
    return rows


def directory():
    with _dir_lock:
        if not _dir["rows"] or time.time() - _dir["at"] > 86400:
            rows = _load_directory()
            _dir.update(at=time.time(), rows=rows, names={x["s"]: x["n"] for x in rows})
        return _dir["rows"]


def directory_names():
    if not _dir["names"]:
        try:
            directory()
        except Exception:
            return {}
    return _dir["names"]


def directory_page(q="", kind="", region="", page=1, size=50):
    rows = directory()
    ql = q.strip().lower()
    def match(x):
        if kind and x["t"] != kind:
            return False
        if region and x["r"] != region:
            return False
        if ql and not (x["s"].lower().startswith(ql) or ql in x["n"].lower()):
            return False
        return True
    hits = [x for x in rows if match(x)]
    core = {sym for grp in ("stocks", "etfs") for lst in UNIVERSE[grp].values() for sym in lst}
    rank = lambda x: 0 if x["s"] in core else 1 if x["r"] != "United States" else 2  # well-known names first
    if ql:  # exact symbol first, then symbol prefix, then well-known, then name
        hits.sort(key=lambda x: (x["s"].lower() != ql, not x["s"].lower().startswith(ql), rank(x), len(x["s"])))
    else:
        hits.sort(key=lambda x: (rank(x), x["s"]))
    total = len(hits)
    start = max(0, (page - 1) * size)
    regions = {}
    for x in rows:
        regions[x["r"]] = regions.get(x["r"], 0) + 1
    return {"total": total, "page": page, "size": size, "rows": hits[start:start + size],
            "regions": sorted(regions.items(), key=lambda kv: -kv[1]), "all": len(rows)}


# ---------------------------------------------------------------- compare 2-3 stocks

def _daily_adj(sym, rng="10y"):
    res = _chart(sym, "range=%s&interval=1d" % rng, 3600)
    return {_day(t): c for t, c in _adj(res)}, (res.get("meta") or {}).get("currency")


def _stats(rets):
    n = len(rets)
    if n < 2:
        return None, None
    m = sum(rets) / n
    return m, math.sqrt(sum((x - m) ** 2 for x in rets) / (n - 1))


def _corr(a, b):
    ma, sa = _stats(a)
    mb, sb = _stats(b)
    if not sa or not sb:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / ((len(a) - 1) * sa * sb)


CRASHES = [("COVID crash", "2020-02-19", "2020-03-23"), ("2022 bear market", "2022-01-03", "2022-10-12"),
           ("2025 tariff drop", "2025-02-19", "2025-04-08")]


def compare_risk(symbols, bench="SPY", base=None, portfolio=None, add_frac=0.1):
    """Risk, crash and correlation numbers for 2-3 picks on shared trading days (5 years, dividends in).
    base: the investor's currency (returns also shown converted). portfolio: {symbol: weight} of holdings."""
    syms = [s.upper() for s in symbols][:3]
    pf = {k.upper(): v for k, v in (portfolio or {}).items() if v > 0}
    need = list(dict.fromkeys(syms + [bench] + list(pf)))
    loaded = dict(POOL.map(lambda s: (s, _try_daily(s)), need))
    for s in syms + [bench]:
        if not loaded.get(s) or not loaded[s][0]:
            raise ValueError("no price history for %s" % s)
    cut = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 5 * 365.25 * 86400))
    days = sorted(d for d in set.intersection(*[set(loaded[s][0]) for s in syms + [bench]]) if d >= cut)
    if len(days) < 120:
        raise ValueError("not enough shared price history to compare")
    px = {s: [loaded[s][0][d] for d in days] for s in syms + [bench]}
    rets = {s: [px[s][i] / px[s][i - 1] - 1 for i in range(1, len(days))] for s in px}
    years = (calendar.timegm(time.strptime(days[-1], "%Y-%m-%d")) - calendar.timegm(time.strptime(days[0], "%Y-%m-%d"))) / 31557600.0
    mb, sb = _stats(rets[bench])
    out, rf = {}, 0.03  # 3% a year cash rate for Sharpe / Sortino

    def fx_series(ccy):
        unit, scale = (ccy, 1.0) if ccy not in ("GBp", "GBX") else ("GBP", 0.01)
        if not base or unit == base:
            return None
        try:
            return _daily_adj("%s%s=X" % (unit, base))[0]
        except Exception:
            return None
    for s in syms:
        r_, p = rets[s], px[s]
        m, sd = _stats(r_)
        cov = sum((a - m) * (b - mb) for a, b in zip(r_, rets[bench])) / (len(r_) - 1)
        cagr = (p[-1] / p[0]) ** (1 / years) - 1
        down = [x for x in r_ if x < 0]
        dsd = math.sqrt(sum(x * x for x in down) / len(r_)) * math.sqrt(252) if down else None
        vol = sd * math.sqrt(252)
        peak, peak_i, worst, worst_i, worst_peak = p[0], 0, 0.0, 0, 0
        for i, c in enumerate(p):
            if c > peak:
                peak, peak_i = c, i
            dd = c / peak - 1
            if dd < worst:
                worst, worst_i, worst_peak = dd, i, peak_i
        rec = next((i for i in range(worst_i, len(p)) if p[i] >= p[worst_peak]), None)
        mon = {}
        for i, d in enumerate(days):
            mon[d[:7]] = i
        idx = [mon[k] for k in sorted(mon)]
        mr = [(p[idx[k]] / p[idx[k - 1]] - 1, px[bench][idx[k]] / px[bench][idx[k - 1]] - 1) for k in range(1, len(idx))]
        upm = [(a, b) for a, b in mr if b > 0]
        dnm = [(a, b) for a, b in mr if b < 0]
        cap = lambda xs: 100 * (sum(a for a, _ in xs) / len(xs)) / (sum(b for _, b in xs) / len(xs)) if xs and sum(b for _, b in xs) else None
        roll = [p[i] / p[i - 252] - 1 for i in range(252, len(p))]
        own = loaded[s][0]
        crashes = {}
        for name, a, b in CRASHES:
            ks = sorted(k for k in own if a <= k <= b)
            crashes[name] = r(100 * (own[ks[-1]] / own[ks[0]] - 1), 1) if len(ks) > 5 else None
        ccy = loaded[s][1]
        fxs = fx_series(ccy)
        cagr_base = None
        if fxs:
            f0 = next((fxs[d] for d in days if d in fxs), None)
            f1 = next((fxs[d] for d in reversed(days) if d in fxs), None)
            if f0 and f1:
                cagr_base = ((p[-1] * f1) / (p[0] * f0)) ** (1 / years) - 1
        out[s] = {
            "cagr": r(100 * cagr, 1), "cagrBase": r(100 * cagr_base, 1) if cagr_base is not None else None,
            "vol": r(100 * vol, 1), "beta": r(cov / (sb * sb), 2),
            "sharpe": r((cagr - rf) / vol, 2) if vol else None, "sortino": r((cagr - rf) / dsd, 2) if dsd else None,
            "maxdd": r(100 * worst, 1), "ddDate": days[worst_i], "recoveryDays": (rec - worst_peak) if rec is not None else None,
            "recovered": rec is not None, "upCapture": r(cap(upm), 0), "downCapture": r(cap(dnm), 0),
            "worst12m": r(100 * min(roll), 1) if roll else None, "best12m": r(100 * max(roll), 1) if roll else None,
            "median12m": r(100 * sorted(roll)[len(roll) // 2], 1) if roll else None,
            "positiveMonths": round(100.0 * sum(1 for a, _ in mr if a > 0) / len(mr)) if mr else None,
            "crashes": crashes, "currency": ccy,
            "historyYears": round((time.time() - calendar.timegm(time.strptime(min(own), "%Y-%m-%d"))) / 31557600.0, 1) if own else None,
        }
    corr = {"%s|%s" % (a, b): r(_corr(rets[a], rets[b]), 2) for i, a in enumerate(syms) for b in syms[i + 1:]}
    # split the money equally, rebalanced every month
    level, lv, last_m, wts = 1.0, [1.0], days[0][:7], {s: 1.0 / len(syms) for s in syms}
    for i in range(1, len(days)):
        g = sum(wts[s] * (1 + rets[s][i - 1]) for s in syms)
        level *= g
        wts = {s: wts[s] * (1 + rets[s][i - 1]) / g for s in syms}
        if days[i][:7] != last_m:
            wts, last_m = {s: 1.0 / len(syms) for s in syms}, days[i][:7]
        lv.append(level)
    bpeak, bworst = 1.0, 0.0
    for c in lv:
        bpeak = max(bpeak, c)
        bworst = min(bworst, c / bpeak - 1)
    br = [lv[i] / lv[i - 1] - 1 for i in range(1, len(lv))]
    bvol = _stats(br)[1] * math.sqrt(252)
    bcagr = lv[-1] ** (1 / years) - 1
    # every pair at many splits (weight of the first symbol), monthly rebalanced, for core + satellite advice
    def blend_stats(wmap):
        lev, path, lm, w = 1.0, [1.0], days[0][:7], dict(wmap)
        for i in range(1, len(days)):
            g = sum(w[k] * (1 + rets[k][i - 1]) for k in wmap)
            lev *= g
            w = {k: w[k] * (1 + rets[k][i - 1]) / g for k in wmap}
            if days[i][:7] != lm:
                w, lm = dict(wmap), days[i][:7]
            path.append(lev)
        pk, wd = 1.0, 0.0
        for c in path:
            pk = max(pk, c)
            wd = min(wd, c / pk - 1)
        rr = [path[i] / path[i - 1] - 1 for i in range(1, len(path))]
        roll = [path[i] / path[i - 252] - 1 for i in range(252, len(path))]
        crash = {}
        for name, _, _ in CRASHES:
            parts = [(wmap[k], out[k]["crashes"].get(name)) for k in wmap]
            crash[name] = r(sum(a * b for a, b in parts), 1) if all(b is not None for _, b in parts) else None
        return {"cagr": r(100 * (path[-1] ** (1 / years) - 1), 1), "maxdd": r(100 * wd, 1), "vol": r(100 * _stats(rr)[1] * math.sqrt(252), 1),
                "worst12m": r(100 * min(roll), 1) if roll else None, "median12m": r(100 * sorted(roll)[len(roll) // 2], 1) if roll else None, "crashes": crash}
    pair_blend = {}
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            pair_blend["%s|%s" % (a, b)] = {("%.2f" % wa): blend_stats({a: wa, b: 1 - wa}) for wa in
                                            (0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9)}
    inv = {s: 1 / out[s]["vol"] for s in syms if out[s]["vol"]}
    tot = sum(inv.values())
    step = max(1, len(days) // 260)
    res = {"symbols": syms, "benchmark": bench, "from": days[0], "to": days[-1], "years": round(years, 1), "base": base,
           "stats": out, "bench": {"cagr": r(100 * ((px[bench][-1] / px[bench][0]) ** (1 / years) - 1), 1), "vol": r(100 * sb * math.sqrt(252), 1)},
           "corr": corr, "dates": days[::step],
           "norm": {s: [r(100 * px[s][i] / px[s][0], 2) for i in range(0, len(days), step)] for s in syms + [bench]},
           "drawdown": {s: _dd_series(px[s])[::step] for s in syms},
           "blend": [r(100 * x, 2) for x in lv[::step]],
           "blendStats": {"cagr": r(100 * bcagr, 1), "maxdd": r(100 * bworst, 1), "vol": r(100 * bvol, 1),
                          "sharpe": r((bcagr - rf) / bvol, 2) if bvol else None},
           "equalRisk": {s: round(100 * inv[s] / tot) for s in inv} if tot else None, "pairBlend": pair_blend}
    # fit with the current portfolio: correlation and volatility before / after adding each pick
    pfs = [k for k in pf if loaded.get(k) and loaded[k][0]]
    if pfs:
        wsum = sum(pf[k] for k in pfs)
        pdays = [d for d in days if all(d in loaded[k][0] for k in pfs)]
        if len(pdays) > 120:
            pr = []
            for i in range(1, len(pdays)):
                pr.append(sum(pf[k] / wsum * (loaded[k][0][pdays[i]] / loaded[k][0][pdays[i - 1]] - 1) for k in pfs))
            vol_now = _stats(pr)[1] * math.sqrt(252)
            fit = {}
            for s in syms:
                sr = [loaded[s][0][pdays[i]] / loaded[s][0][pdays[i - 1]] - 1 for i in range(1, len(pdays))]
                after = [(1 - add_frac) * a + add_frac * b for a, b in zip(pr, sr)]
                fit[s] = {"corr": r(_corr(pr, sr), 2), "volAfter": r(100 * _stats(after)[1] * math.sqrt(252), 1)}
            res["portfolio"] = {"volNow": r(100 * vol_now, 1), "addPct": round(100 * add_frac), "fit": fit, "holdings": len(pfs)}
    return res


def _try_daily(s):
    try:
        return _daily_adj(s)
    except Exception:
        return ({}, None)


def _dd_series(p):
    out, peak = [], p[0]
    for c in p:
        peak = max(peak, c)
        out.append(r(100 * (c / peak - 1), 1))
    return out


# ---------------------------------------------------------------- HTTP

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
# ---------------------------------------------------------------- news impact (rules, no AI key needed)

BULL = [(r"\bbeats?\b|\btops? (estimates|expectations|forecasts)|record (revenue|profit|sales|quarter)|better[- ]than[- ]expected", 2),
        (r"\bupgrade[sd]?\b|raises? (its )?price target|price target (raised|hike)|\boutperform\b|\bbuy rating\b", 2),
        (r"raises? (its )?(guidance|outlook|forecast)|boosts? (guidance|outlook|forecast)|lifts? (guidance|outlook|forecast)", 3),
        (r"\bsurge[sd]?\b|\bsoar(s|ed)?\b|\bjump(s|ed)?\b|\brall(y|ies|ied)\b|\bclimb(s|ed)?\b|\bgains?\b|\brises?\b|\bhighs?\b", 1),
        (r"buyback|repurchase|dividend (hike|increase)|raises? (its )?dividend", 1),
        (r"\bwins?\b.{0,30}\b(contract|deal|order)|partnership|\bapprov(al|es|ed)\b|strong demand", 1)]
BEAR = [(r"\bmiss(es|ed)?\b|falls? short|below (estimates|expectations)|worse[- ]than[- ]expected", 2),
        (r"\bdowngrade[sd]?\b|cuts? (its )?price target|price target (cut|lowered)|\bunderperform\b|\bsell rating\b", 2),
        (r"cuts? (its )?(guidance|outlook|forecast)|lowers? (its )?(guidance|outlook|forecast)|profit warning|\bwarns?\b", 3),
        (r"\bplunge[sd]?\b|\bsinks?\b|\btumble[sd]?\b|\bslump(s|ed)?\b|\bcrash(es|ed)?\b|\bsell-?off\b|\bslides?\b|\bdrops?\b|\bfalls?\b|\blows?\b", 1),
        (r"lawsuit|\bprobe\b|investigation|\bfraud\b|\brecall\b|antitrust|\bban(s|ned)?\b|export (curbs|controls|restrictions)", 1),
        (r"layoffs?|job cuts|bankrupt|\bdefault\b|delist|short seller", 2)]
HIGH = r"earnings|results|guidance|outlook|forecast|acquir|merger|buyout|takeover|\bFDA\b|bankrupt|downgrade|upgrade|\bSEC\b|fraud|recall|\bCEO\b|tariff|export (ban|curbs|controls)|\bFed\b|rate (cut|hike)|profit warning"


def news_impact(title, summary=""):
    """('bullish'|'bearish'|'neutral', 'high'|'medium'|'low') from simple keyword rules."""
    def score(text, w):
        s = 0.0
        for pat, pts in BULL:
            if re.search(pat, text, re.I):
                s += pts * w
        for pat, pts in BEAR:
            if re.search(pat, text, re.I):
                s -= pts * w
        return s
    s = score(title or "", 1.0) + score(summary or "", 0.4)
    mood = "bullish" if s >= 1 else "bearish" if s <= -1 else "neutral"
    big = re.search(HIGH, title or "", re.I)
    impact = "high" if big and abs(s) >= 1 else "medium" if big or abs(s) >= 2 else "low"
    return mood, impact


# ---------------------------------------------------------------- economic calendar

ECON_WHY = [
    (r"CPI|Inflation", "Inflation: hotter than expected usually hits growth and tech stocks (rates stay high for longer)."),
    (r"Non-Farm|NFP|Employment Change|Unemployment Rate", "Jobs: a very strong or very weak number moves rate expectations and the whole market."),
    (r"Federal Funds|FOMC|Fed Chair|Powell", "US central bank: rate decisions and hints move every stock, the dollar and bonds."),
    (r"Main Refinancing|ECB|Lagarde|Deposit Facility", "European Central Bank: moves the euro, European stocks and your EUR returns on US shares."),
    (r"Official Bank Rate|BOE|MPC", "Bank of England: moves the pound and UK stocks."),
    (r"BOJ|Policy Rate", "Bank of Japan: can shake global markets through the yen."),
    (r"PCE", "The Fed's favourite inflation gauge."),
    (r"GDP", "Economic growth: a big miss raises recession worries."),
    (r"PMI|ISM", "Business surveys: an early sign of growth or slowdown."),
    (r"Retail Sales", "Consumer spending: about two thirds of the US economy."),
    (r"Unemployment Claims", "Weekly layoffs: a sudden jump is an early recession signal."),
]


def econ_calendar():
    def load():
        out = []
        for feed in ("thisweek", "nextweek"):
            try:
                req = urllib.request.Request("https://nfs.faireconomy.media/ff_calendar_%s.json" % feed, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read())
            except Exception:
                if feed == "thisweek":
                    raise
                continue
            for e in data:
                if e.get("country") not in ("USD", "EUR", "GBP", "JPY", "CNY") or e.get("impact") not in ("High", "Medium"):
                    continue
                try:
                    ts = int(datetime.datetime.fromisoformat(e["date"]).timestamp())
                except (KeyError, ValueError):
                    continue
                why = next((w for pat, w in ECON_WHY if re.search(pat, e.get("title") or "")), "")
                out.append({"title": e.get("title"), "country": e.get("country"), "ts": ts, "impact": e.get("impact").lower(),
                            "forecast": e.get("forecast") or None, "previous": e.get("previous") or None,
                            "actual": e.get("actual") or None, "why": why})
        seen, uniq = set(), []
        for e in sorted(out, key=lambda x: x["ts"]):
            k = (e["title"], e["country"], e["ts"])
            if k not in seen:
                seen.add(k)
                uniq.append(e)
        return uniq
    return cached(("econ",), 3600, load)


def calendar_for(symbols):
    try:
        econ = econ_calendar()
        err = None
    except Exception as e:
        econ, err = [], "Economic calendar unavailable (%s)" % str(e)[:80]
    earn = []
    for s, e in zip(symbols[:60], POOL.map(lambda x: next_earnings(x, True), symbols[:60])):
        if e and e["days"] <= 45:
            earn.append({"symbol": s, "date": e["date"], "days": e["days"]})
    earn.sort(key=lambda x: x["days"])
    return {"econ": econ, "earnings": earn, "error": err}


# ---------------------------------------------------------------- morning briefing (rules, no AI key needed)

def briefing(symbols, weights=None):
    """A short plain-English summary: market, your biggest moves, news that matters, earnings and events."""
    weights = weights or {}
    now = time.time()
    lines = []
    idx = {q["symbol"]: q for q in spark(["SPY", "QQQ", "^STOXX50E", "VWRL.L", "^VIX"])}
    spy, qqq, eu, vix = (idx.get(s) or {} for s in ("SPY", "QQQ", "^STOXX50E", "^VIX"))
    if spy.get("changePct") is not None:
        mood = "up" if spy["changePct"] > 0.3 else "down" if spy["changePct"] < -0.3 else "flat"
        txt = "US market %s: S&P 500 %+.1f%%, Nasdaq 100 %+.1f%%" % (mood, spy["changePct"], qqq.get("changePct") or 0)
        if eu.get("changePct") is not None:
            txt += ", Europe %+.1f%%" % eu["changePct"]
        if vix.get("price"):
            txt += ". Fear gauge (VIX) %.0f%s" % (vix["price"], " (nervous market)" if vix["price"] >= 25 else " (calm)" if vix["price"] < 16 else "")
        lines.append({"kind": "market", "tone": "up" if mood == "up" else "down" if mood == "down" else "flat", "text": txt + "."})
    quotes = [q for q in spark(symbols[:60]) if q.get("changePct") is not None] if symbols else []
    if quotes:
        tw = sum(weights.get(q["symbol"], 0) for q in quotes)
        if tw > 0:
            day = sum(weights.get(q["symbol"], 0) * q["changePct"] for q in quotes) / tw
            lines.append({"kind": "portfolio", "tone": "up" if day > 0 else "down", "text": "Your holdings today: about %+.1f%% on average (weighted by size)." % day})
        movers = sorted(quotes, key=lambda q: -abs(q["changePct"]))
        big = [q for q in movers if abs(q["changePct"]) >= 3][:4]
        if big:
            lines.append({"kind": "movers", "tone": "flat", "text": "Big moves: " + ", ".join("%s %+.1f%%" % (q["symbol"], q["changePct"]) for q in big) + ".",
                          "symbols": [q["symbol"] for q in big]})
        else:
            lines.append({"kind": "movers", "tone": "flat", "text": "No holding moved more than 3% today: a quiet day."})
    names = directory_names()
    stop = {"the", "inc", "corp", "group", "holdings", "company", "international", "technologies", "energy", "applied", "advanced"}

    def about(n):
        """Yahoo's per-ticker feed mixes in general headlines: keep the ones that name a holding."""
        title, text = n.get("title") or "", "%s %s" % (n.get("title") or "", n.get("summary") or "")
        hit = []
        for s in symbols[:20]:
            word = next((w for w in re.findall(r"[A-Za-z][A-Za-z&]+", names.get(s) or "") if w.lower() not in stop and len(w) > 2), None)
            if re.search(r"\(%s\)|\b%s\b" % (re.escape(s.split(".")[0]), re.escape(s.split(".")[0])), title) or \
                    re.search(r"\(%s\)" % re.escape(s.split(".")[0]), text) or (word and re.search(r"\b%s\b" % re.escape(word), title, re.I)):
                hit.append(s)
        return hit
    news = []
    for n in (get_news(symbols[:20]) if symbols else []):
        if (n.get("time") or 0) >= now - 36 * 3600:
            hit = about(n)
            if hit:
                n["tickers"] = hit
                news.append(n)
    news.sort(key=lambda n: ({"high": 0, "medium": 1, "low": 2}[n["impact"]], -(n.get("time") or 0)))
    picked = [n for n in news if n["impact"] != "low"][:5]
    for n in picked:
        lines.append({"kind": "news", "tone": {"bullish": "up", "bearish": "down"}.get(n["mood"], "flat"), "text": n["title"],
                      "link": n.get("link"), "publisher": n.get("publisher"), "time": n.get("time"), "mood": n["mood"], "impact": n["impact"],
                      "symbols": n.get("tickers") or []})
    cal = calendar_for(symbols)
    soon = [e for e in cal["earnings"] if e["days"] <= 7]
    if soon:
        lines.append({"kind": "earnings", "tone": "flat", "text": "Earnings this week: " + ", ".join(
            "%s %s" % (e["symbol"], "today" if e["days"] == 0 else "tomorrow" if e["days"] == 1 else "in %d days" % e["days"]) for e in soon[:6])
            + ". Expect bigger swings around these dates.", "symbols": [e["symbol"] for e in soon[:6]]})
    ev, seen = [], set()
    for e in sorted((e for e in cal["econ"] if now - 3600 <= e["ts"] <= now + 48 * 3600 and e["impact"] == "high" and e["country"] in ("USD", "EUR")),
                    key=lambda e: ({"USD": 0, "EUR": 1}.get(e["country"], 2), e["ts"])):
        if (e["country"], e["ts"]) not in seen:
            seen.add((e["country"], e["ts"]))
            ev.append(e)
    for e in sorted(ev[:3], key=lambda e: e["ts"]):
        when = time.strftime("%a %H:%M UTC", time.gmtime(e["ts"]))
        lines.append({"kind": "event", "tone": "flat", "text": "%s %s (%s)%s" % (e["country"], e["title"], when, ": " + e["why"] if e["why"] else ""),
                      "ts": e["ts"]})
    if not picked and symbols:
        lines.append({"kind": "news", "tone": "flat", "text": "No important headlines on your holdings in the last 36 hours."})
    return {"lines": lines, "at": int(now)}


# ---------------------------------------------------------------- correlation of your holdings

def holdings_correlation(symbols, weeks=104):
    """Correlation of weekly returns (2 years). Weekly steps hide the different closing hours of
    US, European and Asian exchanges, which make daily correlations look too low."""
    def load(s):
        try:
            return s, _daily_adj(s, "2y")[0]
        except Exception:
            return s, None
    series = {s: p for s, p in POOL.map(load, symbols[:30]) if p}
    syms = [s for s in symbols if s in series]
    if len(syms) < 2:
        return {"symbols": syms, "matrix": [], "avg": None, "pairs": []}
    weekly = lambda ds: ds[::-5][::-1][-(weeks + 1):]
    common = weekly(sorted(set.intersection(*[set(series[s]) for s in syms])))
    if len(common) < 30:  # a young listing: fall back to each pair's own overlap
        common = None
    rets = {}

    def r_of(s, dates):
        p = series[s]
        return [p[dates[i]] / p[dates[i - 1]] - 1 for i in range(1, len(dates)) if p[dates[i - 1]]]
    m, pairs = [], []
    for i, a in enumerate(syms):
        row = []
        for j, b in enumerate(syms):
            if i == j:
                row.append(1.0)
                continue
            if j < i:
                row.append(m[j][i])
                continue
            dates = common or weekly(sorted(set(series[a]) & set(series[b])))
            c = _corr(r_of(a, dates), r_of(b, dates)) if len(dates) > 20 else None
            row.append(round(c, 2) if c is not None else None)
            if c is not None:
                pairs.append({"a": a, "b": b, "corr": round(c, 2)})
        m.append(row)
    vals = [p["corr"] for p in pairs]
    pairs.sort(key=lambda p: -p["corr"])
    return {"symbols": syms, "matrix": m, "avg": round(sum(vals) / len(vals), 2) if vals else None,
            "pairs": pairs[:5], "low": sorted(pairs, key=lambda p: p["corr"])[:3], "weeks": len(common) - 1 if common else None}


# ---------------------------------------------------------------- Revolut: import the statement file (no API exists)

REVOLUT_FILE = os.path.join(HERE, ".revolut.json")  # git-ignored, stays on this computer
_rev_lock = threading.Lock()
CCY_SIGNS = {"$": "USD", "€": "EUR", "£": "GBP", "CHF": "CHF", "USD": "USD", "EUR": "EUR", "GBP": "GBP"}
REV_COLS = {
    "date": ("date", "time", "date/time", "completed date", "trade date", "datetime"),
    "ticker": ("ticker", "symbol", "ticker symbol", "instrument", "isin/ticker"),
    "type": ("type", "transaction type", "action", "side"),
    "qty": ("quantity", "shares", "qty", "no. of shares", "units", "amount of shares"),
    "price": ("price per share", "price", "share price", "average price", "avg price", "avg. price", "average cost"),
    "amount": ("total amount", "amount", "total", "value", "net amount"),
    "ccy": ("currency", "ccy"),
    "name": ("name", "company", "description", "security name"),
}


def num_text(s):
    """'USD 1,234.50', '$1,234.50', '-€12.30', '1.234,50 €', '0,5' -> float (None if empty)."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip()
    neg = t.startswith("-") or t.startswith("(") or bool(re.match(r"^[A-Z$€£ ]{1,5}-", t))
    t = re.sub(r"[^0-9,.]", "", t)
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        parts = t.split(",")
        t = t.replace(",", ".") if len(parts) == 2 and len(parts[1]) != 3 else t.replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _ccy_of(s):
    t = str(s or "").strip()
    for k, v in CCY_SIGNS.items():
        if t.startswith(k) or t.endswith(k):
            return v
    m = re.match(r"^([A-Z]{3})\b", t)
    return m.group(1) if m else None


def _xlsx_rows(data):
    import zipfile
    import io
    z = zipfile.ZipFile(io.BytesIO(data))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
    sheet = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
    rows = []
    for row in ET.fromstring(z.read(sheet)).iter("{%s}row" % ns["m"]):
        out = {}
        for c in row.findall("m:c", ns):
            ref = re.match(r"([A-Z]+)", c.get("r") or "A").group(1)
            col = 0
            for ch in ref:
                col = col * 26 + ord(ch) - 64
            v = c.find("m:v", ns)
            if c.get("t") == "s" and v is not None:
                val = shared[int(v.text)]
            elif c.get("t") == "inlineStr":
                val = "".join(t.text or "" for t in c.iter("{%s}t" % ns["m"]))
            else:
                val = v.text if v is not None else ""
            out[col - 1] = val
        if out:
            rows.append([out.get(i, "") for i in range(max(out) + 1)])
    return rows


def _rev_date(s):
    if s is None or s == "":
        return None
    try:
        f = float(s)
        if 20000 < f < 80000:  # an Excel date number
            return int((f - 25569) * 86400)
    except (TypeError, ValueError):
        pass
    t = str(s).strip().replace("Z", "+00:00")
    try:
        d = datetime.datetime.fromisoformat(t[:32].replace(" ", "T", 1) if re.match(r"^\d{4}-\d\d-\d\d \d", t) else t[:32])
        return int(d.timestamp() if d.tzinfo else calendar.timegm(d.timetuple()))
    except ValueError:
        pass
    base = re.sub(r"(\.\d+)?(\+00:00)?$", "", t)
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y",
                "%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%d %b %Y", "%b %d, %Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return calendar.timegm(time.strptime(base, fmt))
        except ValueError:
            continue
    try:
        return calendar.timegm(time.strptime(t[:10], "%Y-%m-%d"))
    except ValueError:
        return None


def _rev_symbol(t):
    t = (t or "").strip().upper()
    if re.match(r"^[A-Z]{1,5}\.[A-Z]$", t):  # BRK.B -> BRK-B (Yahoo style)
        t = t.replace(".", "-")
    return t


def parse_revolut(rows):
    """Rows (header first) from a Revolut trading statement, or any broker's holdings list -> trades."""
    head_i = next((i for i, r in enumerate(rows[:15]) if any(str(c).strip().lower() in REV_COLS["ticker"] for c in r)), None)
    if head_i is None:
        raise ValueError("Couldn't find a Ticker or Symbol column. Export the Revolut trading account statement (Excel/CSV), not the PDF.")
    head = [str(c).strip().lower() for c in rows[head_i]]
    col = {k: next((head.index(a) for a in al if a in head), None) for k, al in REV_COLS.items()}
    if col["qty"] is None:
        raise ValueError("Couldn't find a Quantity column in the file.")
    trades, skipped, types = [], 0, {}
    snapshot = col["type"] is None
    for r in rows[head_i + 1:]:
        g = lambda k: (r[col[k]] if col[k] is not None and col[k] < len(r) else "")
        raw_type = str(g("type")).strip().upper()
        sym = _rev_symbol(str(g("ticker")))
        qty, price, amount = num_text(g("qty")), num_text(g("price")), num_text(g("amount"))
        ccy = (str(g("ccy")).strip().upper()[:3] or None) or _ccy_of(g("price")) or _ccy_of(g("amount"))
        ts = _rev_date(g("date")) or int(time.time())
        if snapshot:
            kind = "buy"
        elif "BUY" in raw_type:
            kind = "buy"
        elif "SELL" in raw_type:
            kind = "sell"
        elif "DIVIDEND" in raw_type:
            kind = "dividend"
        elif "SPLIT" in raw_type:
            kind = "split"
        elif "TOP" in raw_type or "DEPOSIT" in raw_type:
            kind = "deposit"
        elif "WITHDRAW" in raw_type:
            kind = "withdrawal"
        elif "FEE" in raw_type or "TAX" in raw_type:
            kind = "fee"
        elif "TRANSFER" in raw_type and sym and qty:
            kind = "buy"  # shares moved in from another account
        else:
            skipped += 1
            types[raw_type or "?"] = types.get(raw_type or "?", 0) + 1
            continue
        if kind in ("buy", "sell") and (not sym or not qty):
            skipped += 1
            continue
        if kind in ("buy", "sell") and not price and amount and qty:
            price = abs(amount) / abs(qty)
        trades.append({"ts": ts, "kind": kind, "symbol": sym or None, "qty": abs(qty) if qty and kind != "split" else qty,
                       "price": abs(price) if price else None, "amount": amount, "ccy": ccy,
                       "name": str(g("name")).strip() or None})
    if not any(t["kind"] in ("buy", "sell") for t in trades):
        raise ValueError("No share trades found in the file. Use the trading account statement covering all your history.")
    trades.sort(key=lambda t: t["ts"])
    return {"trades": trades, "skipped": skipped, "otherTypes": types, "snapshot": snapshot}


def revolut_load():
    if not os.path.exists(REVOLUT_FILE):
        return None
    with open(REVOLUT_FILE) as f:
        return json.load(f)


def revolut_save(d):
    fd = os.open(REVOLUT_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(d, f)


def revolut_import(body):
    import base64
    import csv
    import io
    data = body.get("data") or ""
    name = str(body.get("name") or "statement.csv")[:120]
    raw = base64.b64decode(data.split(",", 1)[-1]) if body.get("base64") else data.encode("utf-8")
    if raw[:2] == b"PK":
        rows = _xlsx_rows(raw)
    elif raw[:4] == b"%PDF":
        raise ValueError("That's the PDF statement. In Revolut choose Excel instead, then import that file.")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
        first = text.splitlines()[0] if text else ""
        delim = ";" if first.count(";") > first.count(",") else "\t" if first.count("\t") > first.count(",") else ","
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    out = parse_revolut(rows)
    acct = (body.get("currency") or "EUR").upper()[:3]
    with _rev_lock:
        old = revolut_load() if body.get("merge") else None
        trades = out["trades"]
        if old:
            seen = {(t["ts"], t["kind"], t["symbol"], t["qty"]) for t in old["trades"]}
            trades = sorted(old["trades"] + [t for t in trades if (t["ts"], t["kind"], t["symbol"], t["qty"]) not in seen], key=lambda t: t["ts"])
        revolut_save({"currency": acct, "trades": trades, "file": name, "imported": int(time.time()),
                      "skipped": out["skipped"], "otherTypes": out["otherTypes"], "snapshot": out["snapshot"]})
    purge(lambda k: k[0] == "revolut")
    return {"ok": True, "trades": len([t for t in trades if t["kind"] in ("buy", "sell")]), "skipped": out["skipped"],
            "otherTypes": out["otherTypes"], "positions": len(revolut_holdings(trades))}


def _rev_book(trades):
    """Average-cost book from the trade list: {symbol: {qty, cost, realized, ccy, name, opened}} (closed ones too)."""
    pos = {}
    for t in trades:
        s = t.get("symbol")
        if not s or t["kind"] not in ("buy", "sell", "split"):
            continue
        p = pos.setdefault(s, {"qty": 0.0, "cost": 0.0, "realized": 0.0, "ccy": t.get("ccy"), "name": t.get("name"), "opened": t["ts"]})
        q = t.get("qty") or 0.0
        if t["kind"] == "buy":
            if p["qty"] <= 1e-9:
                p["opened"] = t["ts"]
            p["qty"] += q
            p["cost"] += q * (t.get("price") or 0)
        elif t["kind"] == "sell":
            avg = p["cost"] / p["qty"] if p["qty"] > 1e-9 else 0
            q = min(q, p["qty"])
            p["realized"] += q * ((t.get("price") or 0) - avg)
            p["qty"] -= q
            p["cost"] -= q * avg
        else:  # split: extra (or fewer) shares, same cost
            p["qty"] = max(0.0, p["qty"] + q)
        p["ccy"] = p["ccy"] or t.get("ccy")
        p["name"] = p["name"] or t.get("name")
    return pos


def revolut_holdings(trades):
    return {s: p for s, p in _rev_book(trades).items() if p["qty"] > 1e-6}


def _resolve(sym):
    try:
        return sym, get_bars(sym, "5d")
    except Exception:
        pass
    try:
        d = yahoo("/v1/finance/search?q=%s&quotesCount=3&newsCount=0" % urllib.parse.quote(sym))
        for qt in d.get("quotes") or []:
            if qt.get("symbol") and qt.get("quoteType") in ("EQUITY", "ETF"):
                return qt["symbol"], get_bars(qt["symbol"], "5d")
    except Exception:
        pass
    return sym, None


def revolut_portfolio():
    d = revolut_load()
    if not d:
        return {"linked": False}

    def load():
        acct = d.get("currency") or "EUR"
        held = revolut_holdings(d["trades"])
        found = dict(zip(held, POOL.map(_resolve, list(held))))
        positions, warn = [], []
        tot = {"value": 0.0, "cost": 0.0, "realized": 0.0, "dividends": 0.0, "deposits": 0.0, "fees": 0.0}
        rates = {}

        def rate(c):
            c = c or acct
            if c not in rates:
                rates[c] = fx_rate(c, acct)
            return rates[c] if rates[c] is not None else 1.0
        for s, p in held.items():
            ysym, bars = found[s]
            price = bars["bars"][-1]["c"] if bars else None
            qccy = (bars or {}).get("meta", {}).get("currency") or p["ccy"] or "USD"
            if not bars:
                warn.append("No live price for %s: shown at cost" % s)
            avg = p["cost"] / p["qty"] if p["qty"] else 0
            px = price if price is not None else avg
            # Yahoo quotes some listings in pence while Revolut reports pounds
            px_trade = px / 100 if qccy in ("GBp", "GBX") and (p["ccy"] or "") == "GBP" else px
            fx = rate(p["ccy"] or qccy)
            value = p["qty"] * px_trade * fx
            cost = p["cost"] * fx
            tot["value"] += value
            tot["cost"] += cost
            positions.append({"symbol": ysym, "revolut": s, "name": (bars or {}).get("meta", {}).get("name") or p["name"] or s,
                              "qty": round(p["qty"], 8), "avgPrice": round(avg, 4), "price": px_trade, "currency": p["ccy"] or qccy,
                              "value": round(value, 2), "valueAcct": round(value, 2), "ppl": round(value - cost, 2),
                              "opened": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(p["opened"]))})
        for p in _rev_book(d["trades"]).values():
            tot["realized"] += p["realized"] * rate(p["ccy"])
        for t in d["trades"]:
            amt = abs(t.get("amount") or 0) * rate(t.get("ccy"))
            if t["kind"] == "dividend":
                tot["dividends"] += amt
            elif t["kind"] == "deposit":
                tot["deposits"] += amt
            elif t["kind"] == "withdrawal":
                tot["deposits"] -= amt
            elif t["kind"] == "fee":
                tot["fees"] += amt
        positions.sort(key=lambda x: -x["value"])
        return {"linked": True, "broker": "Revolut", "currency": acct, "positions": positions, "file": d.get("file"),
                "imported": d.get("imported"), "warnings": warn, "snapshot": d.get("snapshot"),
                "totals": {k: round(v, 2) for k, v in tot.items()}, "ppl": round(tot["value"] - tot["cost"], 2),
                "fetched": int(time.time())}
    return cached(("revolut", d.get("imported")), 60, load)


def revolut_lots():
    d = revolut_load()
    if not d:
        return [], None
    pf = revolut_portfolio()
    sym_map = {p["revolut"]: p["symbol"] for p in pf.get("positions", [])}
    lots = []
    for t in d["trades"]:
        if t["kind"] in ("buy", "sell") and t.get("symbol") and t.get("qty"):
            lots.append({"symbol": sym_map.get(t["symbol"], t["symbol"]), "ts": t["ts"],
                         "qty": t["qty"] if t["kind"] == "buy" else -t["qty"], "price": t.get("price") or 0})
        elif t["kind"] == "split" and t.get("symbol") and t.get("qty"):
            lots.append({"symbol": sym_map.get(t["symbol"], t["symbol"]), "ts": t["ts"], "qty": t["qty"], "price": 0})
    return lots, d.get("currency")


# ---------------------------------------------------------------- long-term entry check: buy now, in parts, or wait?

ENTRY_STATES = {
    "falling": ("Still falling", "down", "The price is below its 50-day average, that average is pointing down, and it made a new 1-month low in the last few days."),
    "steadying": ("Steadying after a drop", "flat", "It fell, but it hasn't made a new 1-month low for two weeks and it's back above its 20-day average."),
    "pullback": ("Pullback in an uptrend", "up", "A dip below the 50-day average while the long-term (200-day) trend is still rising."),
    "uptrend": ("Rising trend", "up", "Above its 50-day and 200-day averages: no discount, but no sign of trouble."),
    "sideways": ("No clear trend", "flat", "Moving sideways around its averages."),
}


def _entry_state(c, s20, s50, s200, i):
    if i < 220 or s50[i] is None or s200[i] is None or s50[i - 20] is None or s200[i - 20] is None:
        return None
    px = c[i]
    low20 = min(c[i - 19:i + 1])
    new_low_5 = min(c[i - 4:i + 1]) <= low20 * 1.0001
    new_low_10 = min(c[i - 9:i + 1]) <= low20 * 1.0001
    slope50 = s50[i] / s50[i - 20] - 1
    slope200 = s200[i] / s200[i - 20] - 1
    drop3m = px / max(c[i - 62:i + 1]) - 1
    if px < s50[i] and slope50 < 0 and new_low_5:
        return "falling"
    if (px < s200[i] or drop3m < -0.10) and not new_low_10 and s20[i] and px > s20[i]:
        return "steadying"
    if px < s50[i] and px > s200[i] and slope200 > 0:
        return "pullback"
    if px > s50[i] > s200[i]:
        return "uptrend"
    return "sideways"


def _q(xs, f):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(f * len(xs))))] if xs else None


def lt_entry(symbol):
    """Is this a good moment to buy for the long term, and at which prices to add if it keeps falling?
    Uses 10 years of dividend-adjusted daily closes: today's trend state, and what happened after
    every past day in the same state (how much further it dipped within 3 months, the 12-month result)."""
    sym = symbol.upper()

    def load():
        res = _chart(sym, "range=10y&interval=1d", 3600)
        pts = _adj(res)
        if len(pts) < 300:
            raise ValueError("Not enough price history for %s (needs about 15 months)" % sym)
        c = [p for _, p in pts]
        s20, s50, s200 = sma(c, 20), sma(c, 50), sma(c, 200)
        n = len(c)
        i = n - 1
        state = _entry_state(c, s20, s50, s200, i)
        dips, rets, same_dips, same_rets, same_idx = [], [], [], [], []
        for j in range(220, n - 63):
            dip = min(c[j + 1:j + 64]) / c[j] - 1
            ret = c[j + 252] / c[j] - 1 if j + 252 < n else None
            dips.append(dip)
            if ret is not None:
                rets.append(ret)
            if _entry_state(c, s20, s50, s200, j) == state:
                same_idx.append(j)
                same_dips.append(dip)
                if ret is not None:
                    same_rets.append(ret)

        def episodes(idx):
            """Separate stretches (more than a month apart): neighbouring days are not independent."""
            return sum(1 for k, j in enumerate(idx) if k == 0 or j - idx[k - 1] > 21)

        def stats(d, r, eps):
            if len(d) < 40 or eps < 3:
                return None
            enough = len(r) >= 40 and eps >= 8  # the 12-month figure needs enough separate episodes
            return {"days": len(d), "episodes": eps, "typicalDip": round(100 * _q(d, 0.5), 1), "deepDip": round(100 * _q(d, 0.2), 1),
                    "up12m": round(100.0 * sum(1 for x in r if x > 0) / len(r), 0) if enough else None,
                    "median12m": round(100 * _q(r, 0.5), 1) if enough else None}
        anyday = stats(dips, rets, max(1, (n - 283) // 252))
        same = stats(same_dips, same_rets, episodes(same_idx))
        if anyday:
            anyday["episodes"] = None
        ref = same or anyday
        px = c[i]
        # where to add more: the typical and the deep further dip seen after days like today
        lv2 = px * (1 + min(-0.03, ref["typicalDip"] / 100)) if ref else px * 0.93
        lv3 = px * (1 + min(-0.06, ref["deepDip"] / 100)) if ref else px * 0.85
        if lv3 > lv2 * 0.97:
            lv3 = lv2 * 0.95
        supports = []
        if s200[i] and s200[i] < px * 0.98:
            supports.append({"name": "200-day average", "price": r(s200[i])})
        low52 = min(c[-252:])
        if low52 < px * 0.98:
            supports.append({"name": "52-week low", "price": r(low52)})
        title, tone, why = ENTRY_STATES.get(state, ENTRY_STATES["sideways"])
        plan = {"falling": [("Now", 1 / 3), ("If it drops to", 1 / 3, lv2), ("If it drops to", 1 / 3, lv3)],
                "steadying": [("Now", 1 / 2), ("If it drops to", 1 / 2, lv2)],
                "pullback": [("Now", 2 / 3), ("If it drops to", 1 / 3, lv2)],
                "uptrend": [("Now", 1.0)], "sideways": [("Now", 1 / 2), ("If it drops to", 1 / 2, lv2)]}[state or "sideways"]
        return {"symbol": sym, "price": r(px), "currency": (res.get("meta") or {}).get("currency"), "state": state,
                "title": title, "tone": tone, "why": why,
                "sma50": r(s50[i]), "sma200": r(s200[i]), "fromHigh3m": round(100 * (px / max(c[-63:]) - 1), 1),
                "same": same, "any": anyday, "years": round(n / 252.0, 1),
                "ladder": [{"label": p[0], "share": round(p[1], 4), "price": r(p[2]) if len(p) > 2 else None} for p in plan],
                "stopAdding": r(lv3 * 0.95) if len(plan) > 2 else r(lv2 * 0.92),
                "supports": supports}
    out = dict(cached(("entry", sym), 3600, load))
    e = next_earnings(sym, wait=False)
    if e and e["days"] <= 14:
        out["earnings"] = e
    try:
        reg = market_regime()
        if reg.get("level") == "red":
            out["marketWeak"] = reg.get("label")
    except Exception:
        pass
    try:
        p = lt_profile(sym)
        out.update(zone=p.get("zone"), zoneWhy=p.get("zoneWhy"), score=p.get("score"), band=p.get("band"))
    except Exception:
        pass
    out["verdict"] = _entry_verdict(out)
    return out


def _entry_verdict(e):
    """One plain sentence combining the trend state with the long-term buy zone."""
    st, zone = e.get("state"), e.get("zone")
    if zone == "Speculative":
        v = ("Careful", "down", "Weak long-term score: if you buy, keep it small, whatever the timing.")
    elif st in ("falling", "steadying", "sideways") and (e.get("same") or {}).get("median12m") is not None and \
            (e["same"]["median12m"] < 0 or (e["same"]["up12m"] or 0) < 50):
        v = ("Wait, or buy only a small part", "down", "After past days like today this stock was more often lower than higher a year later. "
             "Keep it small until the trend turns up.")
    elif st == "falling":
        v = ("Don't buy it all at once", "down", "It's still falling. Split your amount: a third now, the rest only if it drops to the levels below.")
    elif st == "steadying":
        v = ("A reasonable moment to start, in parts", "flat", "The drop seems to be slowing. Buy half now and keep half for a lower price.")
    elif st == "pullback":
        v = ("Historically one of the better moments", "up", "A dip in a rising trend. Most of your amount now, a little kept back in case it dips further.")
    elif zone == "Stretched":
        v = ("Fine, but no discount", "flat", "Rising and priced above its usual range: keep to small regular amounts rather than one big buy.")
    elif st == "uptrend":
        v = ("Fine for your regular amount", "up", "Rising trend and no warning signs. Waiting for a dip often means paying more later.")
    else:
        v = ("Your regular amount is fine", "flat", "No clear trend either way. Splitting into two buys smooths the price.")
    notes = []
    if e.get("earnings"):
        notes.append("Results on %s (in %d days): prices often move 5-15%% that day. Consider buying only part before, the rest after." %
                     (e["earnings"]["date"], e["earnings"]["days"]))
    if e.get("marketWeak"):
        notes.append("The whole market is weak right now: dips can go further than usual.")
    if zone == "Accumulate+" and st in ("falling", "steadying", "pullback"):
        notes.append("The business also scores well and trades below its usual price: a good candidate for adding over the next weeks.")
    return {"title": v[0], "tone": v[1], "text": v[2], "notes": notes}



# ---------------------------------------------------------------- Compare: a challenger that beats every pick

def _quick_stats(sym, years=5):
    """Yearly growth, worst fall and return per unit of downside risk over the last `years` (dividends in)."""
    def load():
        d, _ = _daily_adj(sym, "10y")
        days = sorted(d)[-(252 * years + 1):]
        if len(days) < 252 * 3:
            return None
        c = [d[x] for x in days]
        rets = [c[k] / c[k - 1] - 1 for k in range(1, len(c)) if c[k - 1]]
        yrs = len(rets) / 252.0
        cagr = (c[-1] / c[0]) ** (1 / yrs) - 1
        down = [x for x in rets if x < 0]
        dd = math.sqrt(sum(x * x for x in down) / len(rets)) * math.sqrt(252) if down else None
        peak, worst = c[0], 0.0
        for x in c:
            peak = max(peak, x)
            worst = min(worst, x / peak - 1)
        return {"cagr": round(100 * cagr, 1), "maxdd": round(100 * worst, 1),
                "sortino": round((cagr - 0.03) / dd, 2) if dd else None, "years": round(yrs, 1)}
    return cached(("qstats", sym, years), 6 * 3600, load)


def _peers(symbols):
    """Stocks in the same themes (radar lists) or the same sector lists as the compared ones."""
    themes = list(RADAR_THEMES.items()) + list(LT_EXTRA_THEMES.items())
    same = set()
    for _, lst in themes:
        if any(s in lst for s in symbols):
            same.update(lst)
    for grp in ("stocks", "etfs"):
        for lst in UNIVERSE.get(grp, {}).values():
            if any(s in lst for s in symbols):
                same.update(lst)
    return [s for s in same if s not in symbols]


def _outside_ai():
    ai = set()
    for th, lst in list(RADAR_THEMES.items()) + list(LT_EXTRA_THEMES.items()):
        if th in AI_RADAR_THEMES:
            ai.update(lst)
    pool = set()
    for th, lst in RADAR_THEMES.items():
        if th not in AI_RADAR_THEMES:
            pool.update(lst)
    for lst in UNIVERSE.get("stocks", {}).values():
        pool.update(lst)
    for e in ("VWCE.DE", "VWRL.L", "IWDA.AS", "CSPX.L"):
        pool.add(e)
    return [s for s in pool if s not in ai]


def challenger(symbols):
    """For 2-3 compared stocks: the best stock that beats ALL of them on long-term score and on return per unit of
    downside risk (5 years), without a deeper worst fall. One from the same group, one from outside the AI theme."""
    syms = [s.upper() for s in symbols][:3]
    if len(syms) < 2:
        raise ValueError("Compare at least two stocks first.")

    def info(s):
        try:
            p = lt_profile(s)
            q = _quick_stats(s)
        except Exception:
            return s, None
        if not q or p.get("score") is None:
            return s, None
        return s, {"symbol": s, "name": p.get("name"), "score": p["score"], "zone": p.get("zone"), "band": p.get("band"),
                   "fundamentals": p.get("fundamentals"), **q}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:  # own pool: lt_profile uses POOL inside
        mine = dict(ex.map(info, syms))
    picks = [v for v in mine.values() if v]
    if len(picks) < 2:
        raise ValueError("Not enough history to judge these picks.")
    bar = {"score": max(p["score"] for p in picks), "sortino": max((p["sortino"] or -9) for p in picks),
           "maxdd": max(p["maxdd"] for p in picks) - 5}  # worst fall: no more than 5 points deeper than the mildest pick

    def search(pool, limit):
        pool = sorted(set(pool))[:limit]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            rows = [v for _, v in ex.map(info, pool) if v]
        win, near = [], []
        for c in rows:
            ok = {"score": c["score"] > bar["score"], "sortino": (c["sortino"] or -9) > bar["sortino"], "maxdd": c["maxdd"] >= bar["maxdd"]}
            c["beats"] = ok
            c["rank"] = round(c["score"] + 20 * (c["sortino"] or 0), 1)
            (win if all(ok.values()) else near).append(c)
        win.sort(key=lambda c: -c["rank"])
        near.sort(key=lambda c: (-sum(c["beats"].values()), -c["rank"]))
        return {"winner": win[0] if win else None, "others": win[1:3], "closest": None if win else (near[0] if near else None),
                "searched": len(rows)}
    if FDB["rows"]:
        same_pool = list(dict.fromkeys(fdb_peers(syms, 30) + _peers(syms)))
        semis = {FDB["rows"][s][2] for s in syms if s in FDB["rows"]} | {"Semiconductors & Chip Equipment"}
        ai_syms = {x for t, lst in list(RADAR_THEMES.items()) + list(LT_EXTRA_THEMES.items()) if t in AI_RADAR_THEMES for x in lst}
        out_pool = [x for x in dict.fromkeys(fdb_mega_outside(semis, 70) + _outside_ai()) if x not in ai_syms]
    else:
        same_pool, out_pool = _peers(syms), _outside_ai()
    same = search(same_pool, 45)
    other = search(out_pool, 90)
    return {"picks": picks, "bar": bar, "sameGroup": same, "outsideAI": other,
            "note": "Beats all = higher long-term score, better 5-year return per unit of downside risk, and a worst fall no more than "
                    "5 points deeper than your mildest pick. " + ("Searches large and mega companies worldwide in the same industry (FinanceDatabase) plus the stocks this dashboard tracks."
                    if FDB["rows"] else "Searches the stocks and ETFs this dashboard tracks, not the whole market.")}


# ---------------------------------------------------------------- Financial Modeling Prep (optional key): company figures outside the US

FMP_FILE = os.path.join(HERE, ".fmp.json")          # the key, git-ignored, never sent to the browser
FMP_CACHE_FILE = os.path.join(HERE, ".fmp-cache.json")  # answers kept 7 days: the free plan allows about 250 calls a day
FMP = {"key": None, "calls": 0, "day": None, "lastError": None}
_fmp_lock = threading.Lock()
_fmp_cache = {}


def fmp_load():
    if os.environ.get("FMP_API_KEY"):
        FMP["key"] = os.environ["FMP_API_KEY"].strip()
    elif os.path.exists(FMP_FILE):
        try:
            with open(FMP_FILE) as f:
                FMP["key"] = json.load(f).get("key")
        except (OSError, ValueError):
            pass
    if os.path.exists(FMP_CACHE_FILE):
        try:
            with open(FMP_CACHE_FILE) as f:
                _fmp_cache.update(json.load(f))
        except (OSError, ValueError):
            pass


def fmp_save_key(key):
    FMP["key"] = key or None
    if key:
        fd = os.open(FMP_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"key": key}, f)
    elif os.path.exists(FMP_FILE):
        os.remove(FMP_FILE)


def _fmp_persist():
    try:
        tmp = FMP_CACHE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_fmp_cache, f)
        os.replace(tmp, FMP_CACHE_FILE)
    except OSError:
        pass


class FmpRefused(Exception):
    """FMP answered but won't give this data (plan limit, unknown symbol, bad key)."""


def fmp_get(endpoint, symbol=None, ttl=7 * 86400, **params):
    """GET https://financialmodelingprep.com/stable/<endpoint>, cached on disk."""
    if not FMP["key"]:
        raise FmpRefused("no FMP key")
    q = dict(params)
    if symbol:
        q["symbol"] = symbol
    ck = endpoint + "?" + urllib.parse.urlencode(sorted(q.items()))
    hit = _fmp_cache.get(ck)
    if hit and time.time() - hit[0] < ttl:
        if isinstance(hit[1], dict) and hit[1].get("__refused"):
            raise FmpRefused(hit[1]["__refused"])
        return hit[1]
    q["apikey"] = FMP["key"]
    url = "https://financialmodelingprep.com/stable/%s?%s" % (endpoint, urllib.parse.urlencode(q))
    req = urllib.request.Request(url, headers={"User-Agent": "TraderDash/1.0"})
    today = time.strftime("%Y-%m-%d")
    with _fmp_lock:
        if FMP["day"] != today:
            FMP.update(day=today, calls=0)
        FMP["calls"] += 1
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("Error Message") or ""
        except (ValueError, AttributeError):
            msg = ""
        why = {401: "FMP rejected the key", 402: "not included in your FMP plan", 403: "not included in your FMP plan",
               429: "FMP daily limit reached"}.get(e.code, "FMP error %s" % e.code)
        FMP["lastError"] = (why + (": " + msg[:120] if msg else "")).strip()
        if e.code in (402, 403):  # remember plan refusals for a day, so we don't spend calls on them
            _fmp_cache[ck] = (time.time() - ttl + 86400, {"__refused": why})
        raise FmpRefused(why)
    if isinstance(data, dict) and data.get("Error Message"):
        FMP["lastError"] = data["Error Message"][:160]
        raise FmpRefused(data["Error Message"][:160])
    _fmp_cache[ck] = (time.time(), data)
    _fmp_persist()
    return data


def _num(d, *names):
    """First present numeric field among several spellings (FMP renamed fields between API versions)."""
    for n in names:
        v = (d or {}).get(n)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                continue
    return None


def _first(x):
    return x[0] if isinstance(x, list) and x else (x if isinstance(x, dict) else {})


def fmp_figures(symbol):
    """Company figures from FMP in the same shape the long-term score reads from Nasdaq.com."""
    sym = symbol.upper()
    prof = _first(fmp_get("profile", sym))
    if not prof:
        raise FmpRefused("FMP has no profile for %s" % sym)
    if prof.get("isEtf") or prof.get("isFund"):
        return {"symbol": sym, "available": False, "why": "fund"}
    ratios = _first(fmp_get("ratios-ttm", sym))
    try:
        km = _first(fmp_get("key-metrics-ttm", sym))
    except FmpRefused:
        km = {}
    try:
        inc = fmp_get("income-statement", sym, limit=5, period="annual") or []
    except FmpRefused:
        inc = []
    mcap = _num(prof, "marketCap", "mktCap") or _num(km, "marketCap", "marketCapTTM")
    pct = lambda x: 100 * x if x is not None else None
    fcf_y = _num(km, "freeCashFlowYieldTTM", "freeCashFlowYield")
    ann = []
    for row in sorted([x for x in inc if isinstance(x, dict)], key=lambda x: x.get("date") or ""):
        ann.append({"revenue": _num(row, "revenue"), "netIncome": _num(row, "netIncome"), "year": (row.get("date") or "")[:4]})
    rev_ttm = ann[-1]["revenue"] if ann else None
    eps = _num(ratios, "netIncomePerShareTTM") or _num(km, "netIncomePerShareTTM")
    pe = _num(ratios, "priceToEarningsRatioTTM", "priceEarningsRatioTTM", "peRatioTTM")
    peg = _num(ratios, "priceToEarningsGrowthRatioTTM", "priceEarningsToGrowthRatioTTM", "pegRatioTTM")
    dy = _num(ratios, "dividendYieldTTM", "dividendYielTTM")
    de = _num(ratios, "debtToEquityRatioTTM", "debtEquityRatioTTM")
    cash = _num(km, "cashAndCashEquivalentsTTM")
    net_debt = _num(km, "netDebtTTM")
    debt = (net_debt + cash) if net_debt is not None and cash is not None else None
    roe = _num(km, "returnOnEquityTTM", "roeTTM") or _num(ratios, "returnOnEquityTTM")
    om = _num(ratios, "operatingProfitMarginTTM")
    out = {
        "symbol": sym, "available": True, "source": "Financial Modeling Prep",
        "sector": prof.get("sector"), "industry": prof.get("industry"), "country": prof.get("country"),
        "valuation": {"peTTM": pe if pe and pe > 0 else None, "forwardPE": None, "peg": peg if peg and peg > 0 else None, "marketCap": mcap},
        "highlights": {"roe": pct(roe), "operatingMargin": pct(om), "freeCashFlow": fcf_y * mcap if fcf_y is not None and mcap else None,
                       "revenueTTM": rev_ttm, "debtEquity": pct(de), "totalCash": cash, "totalDebt": debt,
                       "dividendYield": pct(dy), "dividend": _num(prof, "lastDividend", "lastDiv"), "epsTTM": eps},
        "revVsEarnings": {"annual": ann}, "earnings": [], "analyst": {},
    }
    filled = sum(1 for v in list(out["valuation"].values()) + list(out["highlights"].values()) if v is not None)
    if filled < 3 and not ann:
        raise FmpRefused("FMP returned too few figures for %s" % sym)
    return out


def fmp_next_earnings(symbol):
    rows = fmp_get("earnings", symbol.upper(), ttl=12 * 3600, limit=8) or []
    today = time.strftime("%Y-%m-%d")
    future = sorted(r_.get("date") for r_ in rows if isinstance(r_, dict) and (r_.get("date") or "") >= today)
    if not future:
        return None
    ts = calendar.timegm(time.strptime(future[0][:10], "%Y-%m-%d"))
    return {"date": future[0][:10], "ts": ts}


def fmp_status():
    return {"hasKey": bool(FMP["key"]), "fromEnv": bool(os.environ.get("FMP_API_KEY")), "callsToday": FMP["calls"] if FMP["day"] == time.strftime("%Y-%m-%d") else 0,
            "cached": len(_fmp_cache), "lastError": FMP["lastError"]}


def fmp_test():
    """Try one US and three non-US stocks so the user sees what the key's plan covers."""
    out = []
    for sym in ("AAPL", "ASML.AS", "6857.T", "000660.KS"):
        try:
            f = fmp_figures(sym)
            n = sum(1 for v in list(f["valuation"].values()) + list(f["highlights"].values()) if v is not None)
            out.append({"symbol": sym, "ok": True, "text": "%d company figures, %d years of results" % (n, len(f["revVsEarnings"]["annual"]))})
        except FmpRefused as e:
            out.append({"symbol": sym, "ok": False, "text": str(e)})
        except Exception as e:
            out.append({"symbol": sym, "ok": False, "text": str(e)[:120]})
    return {"results": out, "status": fmp_status()}


def company_figures(sym):
    """Nasdaq.com for US stocks (free, no key); Financial Modeling Prep for the rest when a key is set."""
    fa = None
    try:
        fa = fundamentals(sym)
    except Exception:
        fa = None
    if fa and fa.get("available"):
        return fa
    if FMP["key"]:
        try:
            return fmp_figures(sym)
        except Exception:
            pass
    return fa


# ---------------------------------------------------------------- FinanceDatabase (MIT, Jeroen Bouma): 120,000+ companies worldwide

FDB_URL = "https://raw.githubusercontent.com/JerBouma/FinanceDatabase/main/compression/equities.bz2"
FDB_FILE = os.path.join(HERE, ".fdb-equities.bz2")  # git-ignored, refreshed monthly
FDB = {"rows": {}, "byIndustry": {}, "state": "not loaded", "at": 0, "error": None}
_fdb_lock = threading.Lock()
FDB_MAJOR = {"NMS", "NYQ", "NGM", "NCM", "ASE", "AMS", "GER", "PAR", "MIL", "MCE", "EBS", "LSE", "CPH", "STO", "HEL", "OSL", "BRU", "LIS", "VIE", "JPX", "KSC", "TAI", "HKG"}


ASIA_SUFFIX = (".KS", ".KQ", ".T", ".TW", ".TWO", ".HK", ".SS", ".SZ")


def fdb_main_listing(sym, name):
    """Skip preferred shares, odd share classes and cross-listing codes (e.g. 0ACJ.L, 1AMZN.MI, BAC-PB)."""
    if re.search(r"-P[A-Z]?$|\.(PR|WS)", sym) or re.search(r"preferred|depositary|\bnotes?\b|warrant", name or "", re.I):
        return False
    base, _, suf = sym.partition(".")
    if suf and base[:1].isdigit() and ("." + suf) not in ASIA_SUFFIX:
        return False
    if not suf and len(base) == 5 and base[-1] in "MNPQ":  # e.g. GOOGM, MCHPP: not the ordinary share
        return False
    return True


def _company_key(rec):
    """Same company listed twice (Alphabet A and C, ASML in Amsterdam and New York): first two name words."""
    words = re.findall(r"[a-z0-9]+", (rec[0] or "").lower())
    return " ".join(w for w in words if w not in ("the", "inc", "corp", "corporation", "co", "plc", "ag", "sa", "nv", "se", "ltd", "class", "a", "b", "c", "holdings"))[:24]


def fdb_parse(path):
    import bz2
    import csv
    import io
    rows, by_ind = {}, {}
    with bz2.open(path, "rb") as raw:
        rd = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
        head = next(rd)
        ix = {k: i for i, k in enumerate(head)}
        need = ("symbol", "name", "sector", "industry", "country", "market_cap", "exchange")
        if any(k not in ix for k in need):
            raise ValueError("unexpected FinanceDatabase columns")
        get = lambda r, k: r[ix[k]] if ix.get(k) is not None and ix[k] < len(r) else ""
        for r in rd:
            sym = get(r, "symbol")
            if not sym or get(r, "delisted").lower() == "true":
                continue
            rec = (get(r, "name"), get(r, "sector"), get(r, "industry"), get(r, "country"), get(r, "market_cap"), get(r, "exchange"), get(r, "isin"))
            rows[sym] = rec
            if rec[4] in ("Mega Cap", "Large Cap") and rec[5] in FDB_MAJOR and rec[2] and fdb_main_listing(sym, rec[0]):
                by_ind.setdefault(rec[2], []).append(sym)
    return rows, by_ind


def fdb_refresh(force=False):
    """Download (monthly) and load the FinanceDatabase equities file. Runs in the background at start-up."""
    with _fdb_lock:
        if FDB["state"] == "loading":
            return
        FDB["state"] = "loading"
    try:
        fresh = os.path.exists(FDB_FILE) and time.time() - os.path.getmtime(FDB_FILE) < 30 * 86400
        if force or not fresh:
            tmp = FDB_FILE + ".tmp"
            req = urllib.request.Request(FDB_URL, headers={"User-Agent": "TraderDash/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, FDB_FILE)
        rows, by_ind = fdb_parse(FDB_FILE)
        FDB.update(rows=rows, byIndustry=by_ind, state="ready", at=int(os.path.getmtime(FDB_FILE)), error=None)
    except Exception as e:
        FDB.update(state="ready" if FDB["rows"] else "failed", error=str(e)[:160])


def fdb_info(sym):
    rec = FDB["rows"].get(sym)
    if not rec:
        return None
    return {"name": rec[0], "sector": rec[1] or None, "industry": rec[2] or None, "country": rec[3] or None, "size": rec[4] or None, "exchange": rec[5] or None}


def fdb_peers(symbols, limit=40):
    """Large and mega companies in the same industries as `symbols`, one listing per company (by ISIN)."""
    inds = {FDB["rows"][s][2] for s in symbols if s in FDB["rows"] and FDB["rows"][s][2]}
    rows = FDB["rows"]
    out, seen = [], {rows[s][6] for s in symbols if s in rows} | {_company_key(rows[s]) for s in symbols if s in rows}
    for ind in inds:
        for s in sorted(FDB["byIndustry"].get(ind, []), key=lambda x: (0 if rows[x][4] == "Mega Cap" else 1, "." in x, x)):
            isin, ck = rows[s][6], _company_key(rows[s])
            if s in symbols or (isin and isin in seen) or ck in seen:
                continue
            seen.update({isin, ck})
            out.append(s)
    return out[:limit]


def fdb_mega_outside(exclude_industries, limit=80):
    """Mega companies across every sector except the given industries, spread evenly over sectors."""
    by_sector, seen = {}, set()
    for ind, syms in FDB["byIndustry"].items():
        if ind in exclude_industries:
            continue
        for s in sorted(syms, key=lambda x: ("." in x, x)):
            rec = FDB["rows"][s]
            ck = _company_key(rec)
            if rec[4] != "Mega Cap" or (rec[6] and rec[6] in seen) or ck in seen:
                continue
            seen.update({rec[6], ck})
            by_sector.setdefault(rec[1], []).append(s)
    for v in by_sector.values():
        v.sort(key=lambda x: ("." in x, x))
    out, k = [], 0
    while len(out) < limit and any(len(v) > k for v in by_sector.values()):
        for v in by_sector.values():
            if len(v) > k and len(out) < limit:
                out.append(v[k])
        k += 1
    return out


def fdb_status():
    return {"state": FDB["state"], "companies": len(FDB["rows"]), "updated": FDB["at"], "error": FDB["error"]}


# ---------------------------------------------------------------- Tailscale: reach the dashboard away from home

def tailscale_ip():
    """This computer's Tailscale address (100.64.0.0/10) when Tailscale is running, else None. No traffic is sent."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("100.100.100.100", 53))  # Tailscale's own resolver: only routed through the Tailscale interface
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    parts = [int(x) for x in ip.split(".")] if ip.count(".") == 3 else []
    return ip if parts and parts[0] == 100 and 64 <= parts[1] <= 127 else None


MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json", ".ico": "image/x-icon",
        ".webmanifest": "application/manifest+json", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    server_version = "TraderDashboard/1.0"

    def log_message(self, fmt, *args):
        if os.environ.get("DASH_DEBUG"):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _is_local(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in LOCAL_HOSTS and self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def _token_ok(self):
        tok = getattr(self.server, "phone_token", None)
        if not tok:
            return False
        if getattr(self, "_new_cookie", None):
            return True
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "td_key" and hmac.compare_digest(v.encode(), tok.encode()):
                return True
        return False

    def _local_ok(self):
        """This computer always; other devices (phone mode) only with the secret key, same-origin."""
        origin = self.headers.get("Origin")
        if self._is_local():
            if origin and (urllib.parse.urlparse(origin).hostname or "") not in {"127.0.0.1", "localhost", "::1"}:
                return False
            return True
        if not self._token_ok():
            return False
        if origin and urllib.parse.urlparse(origin).netloc != (self.headers.get("Host") or ""):
            return False
        return True

    def _phone_login(self, q):
        """http://<pc>:8212/?key=SECRET unlocks this device. The key stays in the address so that
        'Add to Home Screen' keeps it (iPhone home-screen apps don't share Safari's cookies)."""
        tok = getattr(self.server, "phone_token", None)
        key = q.get("key")
        if tok and key and hmac.compare_digest(key.encode(), tok.encode()):
            self._new_cookie = tok
            return True
        return False

    def end_headers(self):
        tok = getattr(self, "_new_cookie", None)
        if tok:
            self.send_header("Set-Cookie", "td_key=%s; Max-Age=31536000; Path=/; HttpOnly; SameSite=Lax" % tok)
            self._new_cookie = None
        super().end_headers()

    def _locked(self):
        body = (b"<!DOCTYPE html><meta name=viewport content='width=device-width'><body style='font:16px system-ui;"
                b"background:#0d0d0d;color:#f0efec;padding:24px'><h2>TraderDash is locked</h2><p>On your computer open the "
                b"dashboard, tap <b>Use on iPhone</b> at the bottom of the page and scan the QR code with this phone's camera.</p>")
        self.send_response(403)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        self._new_cookie = None
        if not self._is_local() and q.get("key"):
            self._phone_login(q)
        if not self._local_ok():
            if not u.path.startswith("/api/") and getattr(self.server, "phone_token", None):
                return self._locked()
            return self.send_json({"error": "forbidden host"}, 403)
        try:
            if u.path.startswith("/api/"):
                return self.api(u.path, q)
            if u.path.startswith("/logo/"):
                data, ctype = get_logo(urllib.parse.unquote(u.path[6:]))
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "max-age=86400")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
            return self.static(u.path)
        except PermissionError as e:
            self.send_json({"error": str(e)}, 401)
        except urllib.error.HTTPError as e:
            msg = {401: "Trading 212 rejected the API key", 403: "This API key lacks the needed permission",
                   429: "Rate limited, try again in a few seconds"}.get(e.code, "Upstream error %s" % e.code)
            self.send_json({"error": msg}, 502)
        except Exception as e:
            self.send_json({"error": str(e)[:300]}, 500)

    def api(self, path, q):
        syms = lambda s: [x.strip().upper() for x in (s or "").split(",") if x.strip()][:150]
        if q.get("fresh"):  # the refresh buttons: skip the short-term cache for this request
            one = [q.get("symbol", "").upper()] if q.get("symbol") else []
            if path in ("/api/quotes", "/api/analysis", "/api/intraday", "/api/performance", "/api/fundamentals"):
                purge_symbols(syms(q.get("symbols")) + one + ["SPY"])
            elif path == "/api/screener":
                purge(lambda k: k[0] == "bars")
            elif path == "/api/spark":
                ss = syms(q.get("symbols"))
                purge(lambda k: k[0] == "spark" and k[1] in ss)
            elif path == "/api/trending":
                purge(lambda k: k[0] in ("trending", "spark"))
            elif path == "/api/news":
                purge(lambda k: k[0] == "news")
            elif path == "/api/lt":
                ss = syms(q.get("symbols")) + one
                purge(lambda k: k[0] == "lt" and k[1] in ss)
            elif path == "/api/ltentry":
                purge(lambda k: k[0] in ("entry", "lt") and k[1] in one)
            elif path == "/api/t212/dividends":
                _divs["at"] = 0
            elif path == "/api/regime":
                purge(lambda k: k[0] == "regime" or (k[0] == "bars" and k[1] in ("SPY", "QQQ", "^VIX")))
            elif path == "/api/t212/journal":
                _orders["at"] = 0
            elif path == "/api/runners":
                purge(lambda k: k[0] in ("screen", "runners", "news") or (k[0] == "chart" and "interval=5m" in k[2]))
            elif path == "/api/radar":
                purge(lambda k: k[0] in ("radar", "bars") or (k[0] == "chart" and "range=2y&interval=1d" == k[2]))
            elif path == "/api/t212/portfolio":
                purge(lambda k: k[0] == "t212")
        if path == "/api/phone":
            # the computer itself, also when opened through its own network address
            own = self._is_local() or self.client_address[0] in (lan_ip(), tailscale_ip(), "127.0.0.1", "::1")
            if not own:
                return self.send_json({"error": "Open this from the computer running the dashboard", "onPhone": True}, 403)
            tok = getattr(self.server, "phone_token", None)
            port = self.server.server_address[1]
            ip, ts = lan_ip(), tailscale_ip()
            return self.send_json({"enabled": bool(tok), "ip": ip, "port": port,
                                   "url": "http://%s:%d/?key=%s" % (ip, port, tok) if tok and ip else None,
                                   "tailscaleIp": ts, "awayUrl": "http://%s:%d/?key=%s" % (ts, port, tok) if tok and ts else None})
        if path == "/api/universe":
            return self.send_json(UNIVERSE)
        if path == "/api/compare":
            ss = syms(q.get("symbols"))[:3]
            if len(ss) < 2:
                return self.send_json({"error": "pick at least two symbols"}, 400)
            base = (q.get("base") or "").upper()[:3] or None
            pf = {}
            for part in (q.get("pf") or "").split(","):
                k, _, w = part.partition(":")
                try:
                    if k.strip():
                        pf[k.strip().upper()] = float(w)
                except ValueError:
                    pass
            try:
                add = min(0.5, max(0.01, float(q.get("add", "0.1"))))
            except ValueError:
                add = 0.1
            key = ("compare", tuple(ss), base, tuple(sorted(pf.items())), add)
            return self.send_json(cached(key, 1800, lambda: compare_risk(ss, base=base, portfolio=pf, add_frac=add)))
        if path == "/api/spark":
            return self.send_json(spark(syms(q.get("symbols"))[:100]))
        if path == "/api/trending":
            return self.send_json(trending(q.get("region", "US").upper()[:2]))
        if path == "/api/directory":
            try:
                page = max(1, int(q.get("page", "1")))
            except ValueError:
                page = 1
            return self.send_json(directory_page(q.get("q", ""), q.get("type", ""), q.get("region", ""), page))
        if path == "/api/challenger":
            return self.send_json(challenger(syms(q.get("symbols"))))
        if path == "/api/themes":
            return self.send_json({sym: th for th, lst in list(RADAR_THEMES.items()) + list(LT_EXTRA_THEMES.items()) for sym in lst})
        if path == "/api/ltthemes":
            th = {sym: t for t, lst in list(RADAR_THEMES.items()) + list(LT_EXTRA_THEMES.items()) for sym in lst}
            for sym in syms(q.get("symbols")):
                inf = fdb_info(sym)
                if sym not in th and inf and inf.get("industry") == "Semiconductors & Chip Equipment":
                    th[sym] = "AI chips"  # any chip maker or chip-equipment company rides the same AI cycle
            return self.send_json({"themes": th, "groups": AI_BUILDOUT})
        if path == "/api/fmp/status":
            return self.send_json(fmp_status())
        if path == "/api/fmp/test":
            return self.send_json(fmp_test())
        if path == "/api/fdb/status":
            return self.send_json(fdb_status())
        if path == "/api/lookthrough":
            return self.send_json(LOOKTHROUGH)
        if path == "/api/quotes":
            return self.send_json(analyse_many(syms(q.get("symbols"))))
        if path == "/api/analysis":
            return self.send_json(analyse(q.get("symbol", "SPY").upper(), with_series=True))
        if path == "/api/screener":
            lst = q.get("list", "all")
            items = []
            for group in ("stocks", "etfs"):
                if lst in (group, "all"):
                    for sector, symbols in UNIVERSE[group].items():
                        items += [(s, sector, group) for s in symbols]
            res = analyse_many([s for s, _, _ in items])
            for row, (_, sector, group) in zip(res, items):
                row["sector"], row["group"] = sector, group
            return self.send_json(res)
        if path == "/api/search":
            d = yahoo("/v1/finance/search?q=%s&quotesCount=10&newsCount=0" % urllib.parse.quote(q.get("q", "")))
            return self.send_json([{"symbol": x.get("symbol"), "name": x.get("longname") or x.get("shortname"),
                                    "type": x.get("typeDisp") or x.get("quoteType"), "exchange": x.get("exchDisp")}
                                   for x in d.get("quotes", []) if x.get("quoteType") in ("EQUITY", "ETF", "INDEX", "MUTUALFUND")])
        if path == "/api/news":
            s = syms(q.get("symbols")) or ["stock market news", "SPY", "QQQ"]
            return self.send_json(get_news(s[:25]))
        if path == "/api/intraday":
            return self.send_json(intraday(q.get("symbol", "SPY").upper()))
        if path == "/api/performance":
            return self.send_json(performance(q.get("symbol", "SPY").upper()))
        if path == "/api/fundamentals":
            return self.send_json(fundamentals(q.get("symbol", "SPY").upper()))
        if path == "/api/radar":
            return self.send_json(radar())
        if path == "/api/runners":
            pct = q.get("min", "10")
            return self.send_json(runners(tuple(syms(q.get("extra")))[:15], int(pct) if pct.isdigit() and 5 <= int(pct) <= 100 else 10))
        if path == "/api/lt":
            if q.get("symbols"):
                return self.send_json(lt_many(syms(q.get("symbols"))[:120]))
            return self.send_json(lt_profile(q.get("symbol", "SPY").upper()))
        if path == "/api/ltentry":
            return self.send_json(lt_entry(q.get("symbol", "SPY")))
        if path == "/api/ltbacktest":
            return self.send_json(lt_backtest(q.get("symbol", "SPY").upper()))
        if path == "/api/t212/dividends":
            return self.send_json(dividend_summary())
        if path == "/api/backtest":
            return self.send_json(backtest(q.get("symbol", "SPY").upper()))
        if path == "/api/regime":
            return self.send_json(market_regime())
        if path == "/api/fx":
            return self.send_json({"from": q.get("from"), "to": q.get("to"), "rate": fx_rate(q.get("from"), q.get("to"))})
        if path == "/api/t212/journal":
            return self.send_json(trade_journal())
        if path == "/api/t212/status":
            return self.send_json({"linked": bool(T212["key"]), "env": T212["env"],
                                   "source": "env" if os.environ.get("T212_API_KEY") else ("file" if os.path.exists(CRED_FILE) else "memory")})
        if path == "/api/t212/portfolio":
            return self.send_json(t212_portfolio())
        if path == "/api/revolut/portfolio":
            return self.send_json(revolut_portfolio())
        if path == "/api/calendar":
            return self.send_json(calendar_for(syms(q.get("symbols"))))
        if path == "/api/briefing":
            w = {}
            for part in (q.get("w") or "").split(","):
                k, _, v = part.partition(":")
                try:
                    w[k.strip().upper()] = float(v)
                except ValueError:
                    pass
            return self.send_json(briefing(syms(q.get("symbols")), w))
        if path == "/api/correlation":
            return self.send_json(holdings_correlation(syms(q.get("symbols"))[:30]))
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._local_ok():
            return self.send_json({"error": "forbidden host"}, 403)
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self.send_json({"error": "JSON only"}, 415)
        path = urllib.parse.urlparse(self.path).path
        limit = 12 * 1024 * 1024 if path == "/api/revolut/import" else 10000
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            return self.send_json({"error": "file too large"}, 413)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.send_json({"error": "bad JSON"}, 400)
        if path == "/api/revolut/import":
            try:
                return self.send_json(revolut_import(body))
            except Exception as e:
                return self.send_json({"error": str(e)[:300]}, 400)
        if path == "/api/fmp/key":
            k = str(body.get("key") or "").strip()
            if k and not re.match(r"^[A-Za-z0-9]{16,64}$", k):
                return self.send_json({"error": "That doesn't look like an FMP API key (letters and digits only)."}, 400)
            if os.environ.get("FMP_API_KEY"):
                return self.send_json({"error": "The key is set by the FMP_API_KEY environment variable."}, 400)
            fmp_save_key(k)
            purge(lambda k_: k_[0] in ("lt", "entry", "earnings"))
            return self.send_json(fmp_status())
        if path == "/api/revolut/clear":
            with _rev_lock:
                if os.path.exists(REVOLUT_FILE):
                    os.remove(REVOLUT_FILE)
            purge(lambda k: k[0] == "revolut")
            return self.send_json({"linked": False})
        if path == "/api/t212/connect":
            key, secret = (body.get("key") or "").strip(), (body.get("secret") or "").strip() or None
            env = "demo" if body.get("env") == "demo" else "live"
            if not key:
                return self.send_json({"error": "API key is required"}, 400)
            old = dict(T212)
            T212.update(key=key, secret=secret, env=env)
            try:
                with _cache_lock:
                    for k in [k for k in _cache if k[0] == "t212"]:
                        del _cache[k]
                t212_portfolio()
            except urllib.error.HTTPError as e:
                T212.update(old)
                return self.send_json({"error": "Trading 212 said %s. Check the key, secret and Live/Demo choice." % e.code}, 400)
            except Exception as e:
                T212.update(old)
                return self.send_json({"error": "Could not reach Trading 212: %s" % str(e)[:150]}, 400)
            if body.get("remember"):
                fd = os.open(CRED_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    json.dump({"key": key, "secret": secret, "env": env}, f)
            return self.send_json({"linked": True, "env": env})
        if path == "/api/portfolio/history":
            if body.get("fresh"):
                purge(lambda k: k[0] == "t212" or (k[0] == "chart" and "period1=" in str(k[2]) and "interval=1d" in str(k[2])))
                _orders["at"] = 0
            lots, base, notes = build_lots(body.get("manual") or [], include_t212=bool(body.get("t212", True)),
                                           include_revolut=bool(body.get("revolut", True)))
            base = base or (body.get("base") or "USD").upper()[:3]
            out = portfolio_history(lots, base)
            out.setdefault("base", base)
            out["warnings"] = notes + out["warnings"]
            return self.send_json(out)
        if path == "/api/t212/disconnect":
            T212.update(key=None, secret=None)
            if os.path.exists(CRED_FILE):
                os.remove(CRED_FILE)
            return self.send_json({"linked": False})
        self.send_json({"error": "not found"}, 404)

    def static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.realpath(os.path.join(STATIC, path.lstrip("/")))
        if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
            full = os.path.join(STATIC, "index.html")
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(os.path.splitext(full)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)


def lan_ip():
    """This computer's address on the home network (no traffic is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def access_token(new=False):
    if not new:
        try:
            with open(ACCESS_FILE) as f:
                tok = json.load(f).get("token")
            if tok and len(tok) >= 20:
                return tok
        except (OSError, ValueError):
            pass
    tok = secrets.token_urlsafe(24)
    fd = os.open(ACCESS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"token": tok}, f)
    return tok


def main(argv=None):
    p = argparse.ArgumentParser(description="Trader Dashboard: stocks, ETFs, news, entries and your Trading 212 portfolio.")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8212)))
    p.add_argument("--phone", action="store_true", help="also serve your phone on the same Wi-Fi (protected by a secret key)")
    p.add_argument("--new-key", action="store_true", help="with --phone: make a new secret key (logs out phones)")
    p.add_argument("--host", default=None, help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    load_creds()
    fmp_load()
    threading.Thread(target=fdb_refresh, daemon=True).start()
    phone = a.phone or (a.host not in (None, "127.0.0.1", "localhost", "::1"))
    host = a.host or ("0.0.0.0" if phone else "127.0.0.1")
    srv = ThreadingHTTPServer((host, a.port), Handler)
    srv.phone_token = access_token(a.new_key) if phone else None
    print("Trader Dashboard on http://127.0.0.1:%d  (Ctrl+C to stop)" % a.port)
    if phone:
        ip = lan_ip()
        print("Phone mode ON. On your iPhone (same Wi-Fi), open the dashboard on this computer,")
        print("click 'Use on iPhone' at the bottom and scan the QR code, or open:")
        print("    http://%s:%d/?key=%s" % (ip or "<this-computer-ip>", a.port, srv.phone_token))
        print("Keep that link private: it unlocks your dashboard.")
    print("Trading 212: %s" % ("linked (%s)" % T212["env"] if T212["key"] else "not linked, connect it from the Portfolio page"))
    print("Financial Modeling Prep: %s" % ("key set" if FMP["key"] else "no key (optional: add it on the Portfolio page for non-US company figures)"))
    ts = tailscale_ip() if phone else None
    if ts:
        print("Tailscale found: away from home, open http://%s:%d/?key=%s" % (ts, a.port, srv.phone_token))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
