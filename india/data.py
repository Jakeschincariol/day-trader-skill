"""Free public data for NSE/BSE stocks, with an on-disk cache and an offline
mode for tests and replays.

Sources (all unofficial or public files; they can lag or change):
  Yahoo chart v8   https://query2.finance.yahoo.com/v8/finance/chart/TCS.NS?range=5y&interval=1d
  Yahoo spark v7   https://query2.finance.yahoo.com/v7/finance/spark?symbols=...&range=1y&interval=1d
  NSE list         https://archives.nseindia.com/content/equities/EQUITY_L.csv
  NSE price bands  https://archives.nseindia.com/content/equities/sec_list.csv
  NSE bhavcopy     https://archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv

A Bar is a dict: {"d": "YYYY-MM-DD" (IST), "o", "h", "l", "c": float, "v": int}, oldest first.
"""

import csv
import datetime
import gzip
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional

from india import market, symbols
from india.symbols import Sym

UA = "day-trader-skill (+https://github.com/Ibrahimhass/day-trader-skill)"
YAHOO_HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")
ARCHIVES = "https://archives.nseindia.com"
SPARK_BATCH = 20


class DataError(RuntimeError):
    pass


class Fetcher:
    """GET with a polite pause, one retry on 429/5xx, Yahoo host fallback,
    an on-disk cache (ttl seconds) and an offline mode.

    offline: a folder (files named by cache_key, optionally .gz) or a single
    file used for every request. Offline never touches the network."""

    def __init__(self, cache_dir: Optional[str], offline: Optional[str] = None,
                 pause: float = 0.3, ttl: int = 900):
        self.cache_dir, self.offline, self.pause, self.ttl = cache_dir, offline, pause, ttl
        self._last = 0.0

    def _offline(self, cache_key: str) -> bytes:
        if os.path.isfile(self.offline):
            path = self.offline
        else:
            path = os.path.join(self.offline, cache_key)
            if not os.path.exists(path) and os.path.exists(path + ".gz"):
                path += ".gz"
        if not os.path.exists(path):
            raise DataError("offline: no file %s" % path)
        with open(path, "rb") as fh:
            raw = fh.read()
        return gzip.decompress(raw) if path.endswith(".gz") else raw

    def _open(self, url: str) -> bytes:
        wait = self.pause - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return raw

    def _urls(self, url: str) -> List[str]:
        for host in YAHOO_HOSTS:
            if "//%s/" % host in url:
                return [url.replace("//%s/" % host, "//%s/" % h) for h in YAHOO_HOSTS]
        return [url]

    def get(self, url: str, cache_key: str) -> bytes:
        if self.offline:
            return self._offline(cache_key)
        cpath = os.path.join(self.cache_dir, cache_key) if self.cache_dir else None
        if cpath and os.path.exists(cpath) and time.time() - os.path.getmtime(cpath) < self.ttl \
                and not _crossed_bar_final(os.path.getmtime(cpath)):
            with open(cpath, "rb") as fh:
                return fh.read()
        last_err = None
        for u in self._urls(url):
            for attempt in (0, 1):
                try:
                    raw = self._open(u)
                    if cpath:
                        os.makedirs(self.cache_dir, exist_ok=True)
                        with open(cpath, "wb") as fh:
                            fh.write(raw)
                    return raw
                except urllib.error.HTTPError as e:
                    last_err = e
                    if e.code == 404:
                        raise DataError("not found: %s" % u)
                    if e.code == 429 or e.code >= 500:
                        if attempt == 0:
                            time.sleep(self.pause * 10)
                            continue
                    break
                except (urllib.error.URLError, OSError) as e:
                    last_err = e
                    break
        raise DataError("could not fetch %s: %s" % (url, last_err))


def _crossed_bar_final(mtime: float) -> bool:
    """True when a cache file was written before today's 15:50 IST and it is
    now after it: the day's bar may have changed from forming to final."""
    now = market.now_ist()
    written = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=mtime, hours=5, minutes=30)
    return (written.date() == now.date() and market.is_trading_day(now.date())
            and written.time() < market.BAR_FINAL <= now.time())


def cache_key_for(kind: str, s: Sym, rng: str) -> str:
    return "%s-%s-%s.json" % (kind, symbols.safe_filename(s), rng)


def spark_key(syms: List[Sym], rng: str) -> str:
    joined = ",".join(symbols.to_yahoo(s) for s in syms)
    return "spark-%s-%s.json" % (rng, hashlib.sha1(joined.encode("utf-8")).hexdigest()[:10])


def _day(ts: int, offset: int) -> str:
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=ts + offset)).date().isoformat()


def _bars_from(ts, quote, offset) -> List[Dict]:
    out = {}
    for k, t in enumerate(ts or []):
        c = (quote.get("close") or [None])[k] if k < len(quote.get("close") or []) else None
        if c is None:
            continue
        def g(key, default):
            arr = quote.get(key) or []
            v = arr[k] if k < len(arr) else None
            return default if v is None else v
        out[_day(t, offset)] = {"d": _day(t, offset), "o": float(g("open", c)), "h": float(g("high", c)),
                                "l": float(g("low", c)), "c": float(c), "v": int(g("volume", 0) or 0)}
    return [out[d] for d in sorted(out)]


def yahoo_daily(f: Fetcher, s: Sym, rng: str = "5y") -> List[Dict]:
    url = "https://%s/v8/finance/chart/%s?range=%s&interval=1d" % (
        YAHOO_HOSTS[0], symbols.yahoo_path_part(s), rng)
    doc = json.loads(f.get(url, cache_key_for("chart", s, rng)).decode("utf-8"))
    res = (doc.get("chart") or {}).get("result")
    if not res:
        err = (doc.get("chart") or {}).get("error") or {}
        raise DataError("Yahoo has no daily bars for %s: %s" % (symbols.to_yahoo(s), err.get("description", "")))
    r = res[0]
    offset = int((r.get("meta") or {}).get("gmtoffset", 19800))
    quote = dict(((r.get("indicators") or {}).get("quote") or [{}])[0])
    ts = r.get("timestamp") or []
    _fill_latest(ts, quote, r.get("meta") or {}, offset)
    return _bars_from(ts, quote, offset)


def _fill_latest(ts, quote, meta, offset):
    """Yahoo often leaves the latest day's close null; its meta carries the
    last price (and day high / low / volume). Fill that one bar from it."""
    closes = list(quote.get("close") or [])
    px, pt = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if not (ts and closes and closes[-1] is None and px is not None and pt is not None):
        return
    if _day(pt, offset) != _day(ts[-1], offset):
        return
    closes[-1] = px
    quote["close"] = closes
    for key, mkey in (("high", "regularMarketDayHigh"), ("low", "regularMarketDayLow"),
                      ("volume", "regularMarketVolume")):
        arr = list(quote.get(key) or [])
        if arr and arr[-1] is None and meta.get(mkey) is not None:
            arr[-1] = meta[mkey]
            quote[key] = arr


def yahoo_spark(f: Fetcher, syms: List[Sym], rng: str = "1y") -> Dict[str, List[Dict]]:
    """Daily closes for many symbols, 20 per request. Bars carry o=h=l=c, v=0."""
    out = {}
    by_yahoo = {symbols.to_yahoo(s): s for s in syms}
    for i in range(0, len(syms), SPARK_BATCH):
        batch = syms[i:i + SPARK_BATCH]
        q = ",".join(symbols.yahoo_path_part(s) for s in batch)
        url = "https://%s/v7/finance/spark?symbols=%s&range=%s&interval=1d" % (YAHOO_HOSTS[0], q, rng)
        try:
            doc = json.loads(f.get(url, spark_key(batch, rng)).decode("utf-8"))
        except DataError:
            continue
        for item in ((doc.get("spark") or {}).get("result") or []):
            s = by_yahoo.get(item.get("symbol"))
            resp = (item.get("response") or [None])[0]
            if not s or not resp:
                continue
            offset = int((resp.get("meta") or {}).get("gmtoffset", 19800))
            ts = resp.get("timestamp") or []
            quote = {"close": ((resp.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []}
            _fill_latest(ts, quote, resp.get("meta") or {}, offset)
            out[s.code] = _bars_from(ts, {"close": quote["close"]}, offset)
    return out


def drop_unfinished(bars: List[Dict], now: datetime.datetime) -> List[Dict]:
    last = market.last_final_bar_date(now).isoformat()
    return [b for b in bars if b["d"] <= last]


def _csv(raw: bytes) -> List[Dict[str, str]]:
    text = raw.decode("utf-8-sig", errors="replace")
    rows = csv.reader(io.StringIO(text))
    header = [h.strip() for h in next(rows, [])]
    return [{h: (v or "").strip() for h, v in zip(header, r)} for r in rows if r]


def nse_equity_list(f: Fetcher) -> List[Dict]:
    rows = _csv(f.get(ARCHIVES + "/content/equities/EQUITY_L.csv", "EQUITY_L.csv"))
    return [{"symbol": r.get("SYMBOL", ""), "name": r.get("NAME OF COMPANY", ""),
             "series": r.get("SERIES", ""), "isin": r.get("ISIN NUMBER", "")} for r in rows if r.get("SYMBOL")]


def nse_price_bands(f: Fetcher) -> Dict[str, str]:
    rows = _csv(f.get(ARCHIVES + "/content/equities/sec_list.csv", "sec_list.csv"))
    out = {}
    for r in rows:
        if r.get("Symbol"):
            band = (r.get("Band") or "").strip()
            out[r["Symbol"]] = band if band in ("2", "5", "10", "20") else "-"   # "No Band", "-", blank
    return out


def nse_delivery(f: Fetcher, d: datetime.date) -> Dict[str, float]:
    name = "sec_bhavdata_full_%s.csv" % d.strftime("%d%m%Y")
    try:
        rows = _csv(f.get(ARCHIVES + "/products/content/" + name, name))
    except DataError:
        return {}
    out = {}
    for r in rows:
        if r.get("SERIES") == "EQ":
            try:
                out[r["SYMBOL"]] = float(r.get("DELIV_PER", ""))
            except ValueError:
                pass
    return out
