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
