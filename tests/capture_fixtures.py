#!/usr/bin/env python3
"""Cut the offline test fixtures from live data. Needs the network; the test
suite never runs or imports this file.

    python3 tests/capture_fixtures.py --date 2026-11-18
    python3 tests/capture_fixtures.py --rss          # news feeds only (swing-news tests)

Writes into tests/fixtures/india/, each file named by the cache key the
tools use, so Fetcher(offline=that folder) finds it:
  chart-<SYM>.NS-5y.json.gz   5 years of daily bars, the four detailed stocks
  chart-<SYM>.NS-1y.json.gz   1 year of daily bars, every fixture stock
  spark-1y-<hash>.json.gz     1 year of closes, the 20 fixture stocks in one batch
  EQUITY_L.csv, sec_list.csv  NSE lists cut to the fixture stocks plus a few others
  sec_bhavdata_full_DDMMYYYY.csv  bhavcopy cut to the fixture stocks
"""

import argparse
import datetime
import gzip
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from _load import FIXTURE_SYMBOLS, INDIA_FIX  # noqa: E402
from india import data, symbols  # noqa: E402

DETAILED = ["TCS", "M&M", "IDEA", "RELIANCE"]
EXTRA_ROWS = 25   # unrelated rows kept in the CSV excerpts (to exercise filters)


def save(name, raw, gz=False):
    path = os.path.join(INDIA_FIX, name + (".gz" if gz else ""))
    with open(path, "wb") as fh:
        fh.write(gzip.compress(raw, mtime=0) if gz else raw)
    print("wrote %s (%d bytes)" % (os.path.relpath(path), os.path.getsize(path)))


def cut_csv(raw, key_col, keep):
    lines = raw.decode("utf-8-sig").splitlines()
    head = [h.strip() for h in lines[0].split(",")]
    k = head.index(key_col)
    out, extra = [lines[0]], 0
    for line in lines[1:]:
        cell = line.split(",")[k].strip() if line.count(",") >= k else ""
        if cell in keep:
            out.append(line)
        elif extra < EXTRA_ROWS:
            out.append(line)
            extra += 1
    return ("\n".join(out) + "\n").encode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-11-18")
    ap.add_argument("--rss", action="store_true")
    a = ap.parse_args()
    os.makedirs(INDIA_FIX, exist_ok=True)
    f = data.Fetcher(cache_dir=None, pause=0.5)
    if a.rss:
        return capture_rss(f)
    syms = [symbols.parse(s) for s in FIXTURE_SYMBOLS]
    for s in syms:
        for rng in (["5y", "1y"] if s.code in DETAILED else ["1y"]):
            url = "https://query2.finance.yahoo.com/v8/finance/chart/%s?range=%s&interval=1d" % (
                symbols.yahoo_path_part(s), rng)
            save(data.cache_key_for("chart", s, rng), f.get(url, "x"), gz=True)
    q = ",".join(symbols.yahoo_path_part(s) for s in syms)
    url = "https://query2.finance.yahoo.com/v7/finance/spark?symbols=%s&range=1y&interval=1d" % q
    save(data.spark_key(syms, "1y"), f.get(url, "x"), gz=True)
    keep = set(FIXTURE_SYMBOLS)
    save("EQUITY_L.csv", cut_csv(f.get(data.ARCHIVES + "/content/equities/EQUITY_L.csv", "x"), "SYMBOL", keep))
    save("sec_list.csv", cut_csv(f.get(data.ARCHIVES + "/content/equities/sec_list.csv", "x"), "Symbol", keep))
    d = datetime.date.fromisoformat(a.date)
    name = "sec_bhavdata_full_%s.csv" % d.strftime("%d%m%Y")
    save(name, cut_csv(f.get(data.ARCHIVES + "/products/content/" + name, "x"), "SYMBOL", keep))
    closes = {}
    for s in syms:
        bars = [b for b in data.yahoo_daily(data.Fetcher(None, offline=INDIA_FIX), s, "1y") if b["d"] <= a.date]
        closes[s.code] = bars[-1]["c"] if bars else None
    under = [k for k, v in closes.items() if v is not None and v < 250]
    print("closed under Rs 250 on %s: %s" % (a.date, ", ".join(under) or "NONE (warning: no 0.01 tick case)"))


def capture_rss(f):
    import urllib.parse
    for code in ("TCS",):
        s = symbols.parse(code)
        url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s&region=IN&lang=en-IN" % symbols.yahoo_path_part(s)
        save("rss-yahoo-%s.xml" % symbols.safe_filename(s), f.get(url, "x"))
        q = urllib.parse.quote('"Tata Consultancy Services" share')
        url = "https://news.google.com/rss/search?q=%s&hl=en-IN&gl=IN&ceid=IN:en" % q
        save("rss-google-%s.xml" % symbols.safe_filename(s), f.get(url, "x"))


if __name__ == "__main__":
    main()
