#!/usr/bin/env python3
"""Zerodha Kite Connect as a price source for the trader skills. Standard library only.

Off by default: the tools read Yahoo Finance (RELIANCE -> RELIANCE.NS), which is free.
Set TRADER_DATA_SOURCE=kite to read one symbol's bars from Kite Connect instead.

    export TRADER_DATA_SOURCE=kite
    export KITE_API_KEY=...            # from your Kite Connect app
    export KITE_ACCESS_TOKEN=...       # from your daily login; Zerodha expires it every morning

This module never logs in and never sees your password or TOTP. You run Zerodha's login
flow yourself (kite.trade/docs/connect/v3/user) and export the access token it gives you.

What it answers: the single-symbol chart paths of the Yahoo v8 API (the ones entry, exit,
timemachine, alerts and news ask for), re-shaped from Kite's candles into Yahoo's JSON so
the callers do not change. Anything else (the scanner's whole-market spark requests) is
not answered here: Kite's historical API takes one symbol a request, 3 requests a second.
The scanner shortlists on Yahoo and confirms each hit through Kite.

Kite endpoints (https://kite.trade/docs/connect/v3/):
  GET /instruments/NSE                          CSV of instruments; tradingsymbol -> instrument_token
  GET /instruments/historical/<token>/<interval>?from=YYYY-MM-DD+HH:MM:SS&to=...
      interval minute | 5minute | day; candles [ISO time, open, high, low, close, volume]
  Header  Authorization: token <api_key>:<access_token>   and   X-Kite-Version: 3
Historical data is a separate paid Kite Connect entitlement: without it Kite answers 403.
"""

import csv
import datetime
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.kite.trade"
UA = "day-trader-skills-nse/1.0 (+kitefeed)"
PAUSE = 0.35                      # Kite allows 3 historical requests a second
IST = datetime.timedelta(hours=5, minutes=30)
EPOCH = datetime.datetime(1970, 1, 1)
KITE_INTERVAL = {"1m": "minute", "5m": "5minute", "1d": "day"}
SECONDS = {"1m": 60, "5m": 300, "1d": 86400}
RANGE_DAYS = {"1d": 5, "5d": 8, "1mo": 32, "60d": 62, "3mo": 95}   # calendar days to ask for
CHART = re.compile(r"^/v8/finance/chart/([^?]+)\?range=([^&]+)&interval=([^&]+)$")


class KiteError(Exception):
    pass


def enabled():
    return os.environ.get("TRADER_DATA_SOURCE", "").strip().lower() == "kite"


def _headers():
    key, tok = os.environ.get("KITE_API_KEY", ""), os.environ.get("KITE_ACCESS_TOKEN", "")
    if not key or not tok:
        raise KiteError("TRADER_DATA_SOURCE=kite needs KITE_API_KEY and KITE_ACCESS_TOKEN in the environment "
                        "(the access token expires every morning: log in to Kite again)")
    return {"User-Agent": UA, "X-Kite-Version": "3", "Authorization": "token %s:%s" % (key, tok)}


def _get(path, timeout=30):
    req = urllib.request.Request(BASE + path, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
            msg = json.loads(body).get("message") or body[:120]
        except Exception:
            msg = ""
        finally:
            e.close()
        if e.code in (401, 403):
            raise KiteError("Kite refused the request (HTTP %d: %s). An expired access token or a missing "
                            "historical-data subscription are the usual causes." % (e.code, msg or "no message"))
        if e.code == 429:
            raise KiteError("Kite is rate limiting (HTTP 429): wait a few seconds and try again")
        raise KiteError("Kite answered HTTP %d: %s" % (e.code, msg))
    except (urllib.error.URLError, OSError) as e:
        raise KiteError("could not reach Kite: %s" % getattr(e, "reason", e))


def parse_instruments(text):
    """Kite's instruments CSV -> {tradingsymbol: instrument_token} for NSE cash equities."""
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("segment") == "NSE" and row.get("instrument_type") == "EQ":
            out[row["tradingsymbol"].upper()] = int(row["instrument_token"])
    if not out:
        raise KiteError("Kite's instrument list had no NSE equities")
    return out


def instrument_token(symbol, cache_dir=None):
    """The instrument token of an NSE symbol. The day's list is cached in cache_dir (default
    trader/state), because Kite's list is large and only changes overnight."""
    cache_dir = cache_dir or os.path.join("trader", "state")
    path = os.path.join(cache_dir, "kite_instruments_%s.csv" % (datetime.datetime.utcnow() + IST).date().isoformat())
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = _get("/instruments/NSE", timeout=60)
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    tokens = parse_instruments(text)
    tok = tokens.get(symbol.upper())
    if tok is None:
        raise KiteError("Kite has no NSE equity called %s" % symbol.upper())
    return tok


def _epoch(iso):
    """'2026-11-06T09:15:00+0530' -> unix seconds."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})([+-]\d{4})?$", iso)
    if not m:
        raise KiteError("unexpected candle time %r" % iso)
    naive = datetime.datetime(*[int(m.group(i)) for i in range(1, 7)])
    off = m.group(7)
    delta = IST if not off else datetime.timedelta(hours=int(off[1:3]), minutes=int(off[3:5])) * (1 if off[0] == "+" else -1)
    return int((naive - delta - EPOCH).total_seconds())


def to_yahoo_json(symbol, candles, interval, now_utc):
    """Kite candles -> Yahoo v8 chart JSON text. For intraday ranges Kite also sends the bar
    still forming, which is what Yahoo does too; callers drop bars that are not complete."""
    rows = []
    for c in candles:
        if c[4] is None:
            continue
        rows.append((_epoch(c[0]), c[1], c[2], c[3], c[4], c[5]))
    if not rows:
        raise KiteError("Kite returned no candles for %s" % symbol)
    last_day = (EPOCH + datetime.timedelta(seconds=rows[-1][0]) + IST).date()
    if interval != "1d":
        today = [r for r in rows if (EPOCH + datetime.timedelta(seconds=r[0]) + IST).date() == last_day]
        before = [r for r in rows if (EPOCH + datetime.timedelta(seconds=r[0]) + IST).date() < last_day]
    else:
        today, before = rows[-1:], rows[:-1]
    prev_close = before[-1][4] if before else None
    meta = {"currency": "INR", "symbol": symbol.upper() + ".NS", "exchangeName": "NSI", "timezone": "IST",
            "gmtoffset": 19800, "instrumentType": "EQUITY", "dataGranularity": interval,
            "regularMarketPrice": rows[-1][4], "regularMarketTime": rows[-1][0],
            "regularMarketDayHigh": max(r[2] for r in today), "regularMarketDayLow": min(r[3] for r in today),
            "regularMarketVolume": sum(r[5] or 0 for r in today), "chartPreviousClose": prev_close,
            "previousClose": prev_close}
    doc = {"chart": {"result": [{"meta": meta, "timestamp": [r[0] for r in rows], "indicators": {"quote": [{
        "open": [r[1] for r in rows], "high": [r[2] for r in rows], "low": [r[3] for r in rows],
        "close": [r[4] for r in rows], "volume": [r[5] for r in rows]}]}}], "error": None}}
    return json.dumps(doc)


def chart(symbol, rng, interval, now_utc=None, sleep=time.sleep):
    """One symbol's bars as Yahoo chart JSON, read from Kite."""
    if interval not in KITE_INTERVAL:
        raise KiteError("Kite feed supports intervals 1m, 5m and 1d, not %s" % interval)
    if rng not in RANGE_DAYS:
        raise KiteError("Kite feed does not know the range %s" % rng)
    now_utc = now_utc or datetime.datetime.utcnow()
    now = now_utc + IST
    start = now - datetime.timedelta(days=RANGE_DAYS[rng])
    fmt = "%Y-%m-%d+%H:%M:%S"
    sleep(PAUSE)
    path = "/instruments/historical/%d/%s?from=%s&to=%s" % (
        instrument_token(symbol), KITE_INTERVAL[interval], start.strftime(fmt), now.strftime(fmt))
    try:
        candles = json.loads(_get(path))["data"]["candles"]
    except (ValueError, KeyError, TypeError):
        raise KiteError("Kite returned something unexpected for %s" % symbol.upper())
    return to_yahoo_json(symbol, candles, interval, now_utc)


def maybe_get(path):
    """The Yahoo v8 chart path -> JSON text read from Kite, or None when Kite is not switched on
    or the path is not a single-symbol chart (the caller then asks Yahoo)."""
    if not enabled():
        return None
    m = CHART.match(path)
    if not m:
        return None
    sym = urllib.parse.unquote(m.group(1))
    sym = sym[:-3] if sym.upper().endswith(".NS") else sym
    return chart(sym, m.group(2), m.group(3))
