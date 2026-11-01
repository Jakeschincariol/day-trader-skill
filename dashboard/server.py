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
import calendar
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
UA = "Mozilla/5.0 (compatible; day-trader-skill-dashboard/1.0; +https://github.com/Jakeschincariol/day-trader-skill)"

with open(os.path.join(HERE, "universe.json")) as _f:
    UNIVERSE = json.load(_f)

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
            },
            "bars": bars,
        }
    return cached(("bars", symbol, rng), 120, load)


def spy_return_63():
    try:
        c = [b["c"] for b in get_bars("SPY")["bars"]]
        return c[-1] / c[-64] - 1 if len(c) > 64 else None
    except Exception:
        return None


def analyse(symbol, with_series=False):
    data = get_bars(symbol)
    bars = data["bars"]
    c = [b["c"] for b in bars]
    h = [b["h"] for b in bars]
    l = [b["l"] for b in bars]
    v = [b["v"] for b in bars]
    s20, s50, s200 = sma(c, 20), sma(c, 50), sma(c, 200)
    rs = rsi(c)
    ml, ms, mh = macd(c)
    at = atr(h, l, c)
    vavg = sma(v, 20)
    i = len(c) - 1
    price, prev = c[i], c[i - 1]
    last = lambda xs, k=0: xs[i - k] if i - k >= 0 else None

    # ---- rating: each signal adds or removes points, shown to the user
    reasons, score, maxpts = [], 0.0, 0.0

    def sig(points, ok, good, bad):
        nonlocal score, maxpts
        maxpts += abs(points)
        if ok is None:
            return
        if ok:
            score += points
            reasons.append({"ok": True, "text": good, "pts": points})
        else:
            reasons.append({"ok": False, "text": bad, "pts": 0})

    a20, a50, a200 = last(s20), last(s50), last(s200)
    sig(2, None if a50 is None else price > a50, "Price above its 50-day average", "Price below its 50-day average")
    sig(2, None if a200 is None else price > a200, "Price above its 200-day average (long-term uptrend)",
        "Price below its 200-day average (long-term downtrend)")
    sig(1.5, None if a50 is None or a200 is None else a50 > a200, "50-day above 200-day average (golden cross zone)",
        "50-day below 200-day average (death cross zone)")
    sig(1, None if a20 is None else price > a20, "Price above its 20-day average (short-term strength)",
        "Price below its 20-day average (short-term weakness)")
    rv = last(rs)
    if rv is not None:
        sig(1.5, 45 <= rv <= 68, "RSI %.0f: healthy momentum" % rv,
            "RSI %.0f: %s" % (rv, "overbought, stretched" if rv > 68 else "weak momentum"))
    hv, hp = last(mh), last(mh, 1)
    sig(1, None if hv is None else hv > 0, "MACD above its signal line", "MACD below its signal line")
    sig(0.5, None if hv is None or hp is None else hv > hp, "MACD momentum rising", "MACD momentum fading")
    r63 = c[i] / c[i - 63] - 1 if i >= 63 else None
    sig(1, None if r63 is None else r63 > 0, "Up %.1f%% over 3 months" % (100 * (r63 or 0)),
        "Down %.1f%% over 3 months" % (-100 * (r63 or 0)))
    spy = spy_return_63() if symbol != "SPY" else None
    if r63 is not None and spy is not None:
        sig(1, r63 > spy, "Beating the S&P 500 over 3 months", "Lagging the S&P 500 over 3 months")
    va = last(vavg)
    if va:
        up_vol = price > prev and v[i] > 1.2 * va
        sig(0.5, up_vol, "Buyers stepping in: up day on above-average volume", "No volume confirmation today")
    pct = 100 * score / maxpts if maxpts else 50
    if pct >= 78:
        rating = "Strong Buy"
    elif pct >= 60:
        rating = "Buy"
    elif pct >= 40:
        rating = "Hold"
    elif pct >= 22:
        rating = "Sell"
    else:
        rating = "Strong Sell"

    # ---- entry timing
    av = last(at) or price * 0.02
    hi20 = max(h[max(0, i - 20):i]) if i > 1 else price
    lo10 = min(l[max(0, i - 10):i + 1])
    downtrend = a50 is not None and a200 is not None and price < a50 and a50 < a200
    breakout = price > hi20 and va and v[i] > 1.3 * va
    near20 = a20 is not None and abs(price - a20) <= 0.75 * av
    extended = (a20 is not None and price > a20 + 2 * av) or (rv is not None and rv > 72)
    if downtrend:
        status, entry = "Avoid", None
        why = "Downtrend: price is below the 50-day and the 50-day is below the 200-day. Wait for a close back above the 50-day average at %.2f." % a50
        trigger = a50
    elif breakout:
        status, entry, trigger = "Buy now: breakout", price, hi20
        why = "Broke above the 20-day high (%.2f) on %.1fx normal volume. Breakouts work best bought the same day, not chased days later." % (hi20, v[i] / va)
    elif near20 and pct >= 55 and (rv is None or rv < 65):
        status, entry, trigger = "Buy zone: pullback", price, a20
        why = "Uptrend pulled back to its 20-day average (%.2f). Buying the dip near support keeps the stop close." % a20
    elif extended:
        status, entry, trigger = "Wait: extended", a20 + 0.5 * av if a20 else None, a20
        why = "Price has run %.1f ATRs above the 20-day average%s. Chasing here means a wide stop; a limit near %.2f is the better spot." % (
            (price - a20) / av if a20 else 0, " and RSI is %.0f" % rv if rv and rv > 70 else "", (a20 + 0.5 * av) if a20 else price)
    elif pct >= 55:
        status, entry, trigger = "Watch", None, hi20
        why = "Trend is fine but price is between levels. Buy a pullback to %.2f or a breakout above %.2f on strong volume." % (a20 or price, hi20)
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
        "avgVolume": r(va, 0),
        "high52": r(max(h[-252:])),
        "low52": r(min(l[-252:])),
        "ret1m": r(100 * (c[i] / c[i - 21] - 1)) if i >= 21 else None,
        "ret3m": r(100 * r63) if r63 is not None else None,
        "ret1y": r(100 * (c[i] / c[max(0, i - 252)] - 1)),
        "rsi": r(rv, 1),
        "atr": r(av),
        "sma20": r(a20), "sma50": r(a50), "sma200": r(a200),
        "score": round(pct),
        "rating": rating,
        "reasons": reasons,
        "entryStatus": status,
        "entryWhy": why,
        "plan": plan,
        "asOf": bars[-1]["t"],
    }
    if with_series:
        out["series"] = {
            "t": [b["t"] for b in bars], "o": [r(b["o"], 4) for b in bars], "h": [r(x, 4) for x in h],
            "l": [r(x, 4) for x in l], "c": [r(x, 4) for x in c], "v": v,
            "sma20": [r(x) for x in s20], "sma50": [r(x) for x in s50], "sma200": [r(x) for x in s200],
            "rsi": [r(x, 1) for x in rs], "macd": [r(x, 3) for x in ml], "signal": [r(x, 3) for x in ms],
            "hist": [r(x, 3) for x in mh],
        }
        out["forecast"] = forecast(c)
    return out


def forecast(closes, days=63, lookback=126, shrink=0.5):
    """Statistical projection, not a prediction.

    Centre: the last 6 months' log-linear trend, halved (trends fade).
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
    drift = slope * shrink
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
        daily = [(x[0], x[4]) for x in _rows(dres)]
        weekly = [(x[0], x[4]) for x in _rows(wres)]
        if daily and weekly and weekly[-1][0] < daily[-1][0]:
            weekly.append(daily[-1])
        return daily, weekly
    me, spy = POOL.map(lambda s: series(s), [symbol, "SPY"])
    first = me[1][0][0] if me[1] else None
    return {"symbol": symbol, "since": first, "returns": _ret_table(*me), "spy": _ret_table(*spy)}


# ---------------------------------------------------------------- fundamentals (Nasdaq, US listings)

def nasdaq(path, ttl=6 * 3600):
    def load():
        d = http_get("https://api.nasdaq.com/api/" + path, headers={"User-Agent": "Mozilla/5.0 (compatible; day-trader-skill-dashboard/1.0)"}, timeout=25)
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

RADAR_WINNERS = ["NVDA", "MU", "SNDK", "ASML", "WDC", "PLTR", "APP", "AVGO"]
RADAR_THEMES = {
    "Memory & storage": ["MU", "SNDK", "WDC", "STX"],
    "Chip equipment": ["ASML", "AMAT", "LRCX", "KLAC", "TER", "ONTO", "ACMR"],
    "AI chips": ["NVDA", "AMD", "AVGO", "MRVL", "ARM", "ALAB", "CRDO", "INTC"],
    "Networking & optics": ["ANET", "CIEN", "COHR", "LITE", "AAOI", "FN", "CLS"],
    "Power & data centers": ["VRT", "VST", "CEG", "OKLO", "NBIS", "CRWV", "IREN", "BE"],
    "Quantum & space": ["IONQ", "RGTI", "QBTS", "RKLB", "ASTS"],
    "AI software": ["PLTR", "APP", "SNOW", "CRWD", "NET", "DDOG"],
}
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
            "themes": sorted([{"theme": k, "avg": round(sum(v) / len(v)), "n": len(v), "top": max(v)} for k, v in themes.items()], key=lambda x: -x["avg"]),
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
        return {"env": T212["env"], "currency": info.get("currencyCode") or cash.get("currency"),
                "cash": cash_out, "positions": positions, "fetched": int(time.time())}
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
    return out


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
        if partial and V[0] == 0:
            bought = sum(f for f in F if f > 0)
            out[k] = {"gain": round(V[-1] - sum(F), 2), "pct": round(100 * (V[-1] - sum(F)) / bought, 2) if bought > 0 else None, "partial": True}
            continue
        out[k] = {"gain": round(gain, 2), "pct": round(100 * gain / denom, 2) if denom > 0 else None, "partial": partial}
    bought = sum(f for f in F if f > 0)
    total_gain = V[-1] - sum(F)
    out["Max"] = {"gain": round(total_gain, 2), "pct": round(100 * total_gain / bought, 2) if bought > 0 else None}
    return out


def build_lots(manual, include_t212=True):
    lots, notes = [], []
    for m in manual or []:
        try:
            ts = _iso_ts(m.get("date")) or int(time.time()) - 86400
            lots.append({"symbol": str(m["symbol"]).upper(), "ts": ts, "qty": float(m["qty"]), "price": float(m["avgPrice"])})
        except (KeyError, TypeError, ValueError):
            continue
    base = None
    if include_t212 and T212["key"]:
        pf = t212_portfolio()
        base = pf.get("currency")
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


# ---------------------------------------------------------------- HTTP

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json", ".ico": "image/x-icon",
        ".webmanifest": "application/manifest+json"}


class Handler(BaseHTTPRequestHandler):
    server_version = "TraderDashboard/1.0"

    def log_message(self, fmt, *args):
        if os.environ.get("DASH_DEBUG"):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _local_ok(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if self.server.allow_any_host:
            return True
        if host not in LOCAL_HOSTS:
            return False
        origin = self.headers.get("Origin")
        if origin:
            oh = urllib.parse.urlparse(origin).hostname or ""
            if oh not in {"127.0.0.1", "localhost", "::1"}:
                return False
        return True

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._local_ok():
            return self.send_json({"error": "forbidden host"}, 403)
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path.startswith("/api/"):
                return self.api(u.path, q)
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
            elif path == "/api/news":
                purge(lambda k: k[0] == "news")
            elif path == "/api/radar":
                purge(lambda k: k[0] in ("radar", "bars") or (k[0] == "chart" and "range=2y&interval=1d" == k[2]))
            elif path == "/api/t212/portfolio":
                purge(lambda k: k[0] == "t212")
        if path == "/api/universe":
            return self.send_json(UNIVERSE)
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
        if path == "/api/t212/status":
            return self.send_json({"linked": bool(T212["key"]), "env": T212["env"],
                                   "source": "env" if os.environ.get("T212_API_KEY") else ("file" if os.path.exists(CRED_FILE) else "memory")})
        if path == "/api/t212/portfolio":
            return self.send_json(t212_portfolio())
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._local_ok():
            return self.send_json({"error": "forbidden host"}, 403)
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self.send_json({"error": "JSON only"}, 415)
        n = min(int(self.headers.get("Content-Length") or 0), 10000)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.send_json({"error": "bad JSON"}, 400)
        path = urllib.parse.urlparse(self.path).path
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
            lots, base, notes = build_lots(body.get("manual") or [], include_t212=bool(body.get("t212", True)))
            base = base or (body.get("base") or "USD").upper()[:3]
            out = portfolio_history(lots, base)
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


def main(argv=None):
    p = argparse.ArgumentParser(description="Trader Dashboard: stocks, ETFs, news, entries and your Trading 212 portfolio.")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8212)))
    p.add_argument("--host", default="127.0.0.1", help="keep 127.0.0.1 unless you know why (your keys live here)")
    a = p.parse_args(argv)
    load_creds()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    srv.allow_any_host = a.host not in ("127.0.0.1", "localhost", "::1")
    print("Trader Dashboard on http://%s:%d  (Ctrl+C to stop)" % ("127.0.0.1" if a.host == "0.0.0.0" else a.host, a.port))
    print("Trading 212: %s" % ("linked (%s)" % T212["env"] if T212["key"] else "not linked, connect it from the Portfolio page"))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
