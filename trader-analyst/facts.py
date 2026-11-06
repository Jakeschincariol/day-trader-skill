#!/usr/bin/env python3
"""Quarterly results reader for trader-analyst. Standard library only.

Lays out an NSE company's reported quarters side by side: revenue, operating income, net
income, diluted EPS, margins, and growth against the same quarter a year earlier. Numbers
come from Yahoo Finance's fundamentals time series (unofficial, free, no key), in rupees
and shown in crore (1 crore = 10 million). A company that reports in another currency
(Infosys reports in US dollars in this feed) is shown in millions of that currency and labelled so.

    python3 facts.py RELIANCE
    python3 facts.py RELIANCE TCS --quarters 8
    python3 facts.py INFY --json
    python3 facts.py RELIANCE TCS INFY --metrics trader/metrics.json
    python3 facts.py RELIANCE --offline tests/fixtures/trader-analyst

How the quarters are built:
  - A quarter is a value Yahoo marks as a 3-month period (periodType 3M), keyed by its
    period-end date. Nothing is filled in: a quarter Yahoo does not have shows as missing,
    and a growth figure needs BOTH the quarter and the same quarter a year earlier.
  - Yahoo reports consolidated figures for most companies. Standalone results can differ a
    lot for holding companies. The tool cannot tell which one a quarter is: the filing can.
  - Margins are operating income / revenue and net income / revenue. Banks and NBFCs report
    "revenue" differently, so their margins are not comparable and may be blank.
  - TTM (last four quarters) is shown only when the four latest quarters are consecutive.

Yahoo's coverage of Indian companies has gaps and can lag a fresh filing by days. For any
quarter that matters, open the filing (/trader-news links it) and read the numbers there.

--metrics FILE merges one row per ticker into a JSON file. --offline DIR reads
DIR/<SYMBOL>.json (a saved timeseries answer) instead of the network.

Numbers only: this tool never says whether a stock is a buy.
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "day-trader-skills-nse/1.0 (personal research tool)"
HOSTS = ("query2", "query1")
URL = ("https://%s.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/%s"
       "?type=%s&period1=%d&period2=%d&merge=false")
TYPES = ("TotalRevenue", "OperatingIncome", "NetIncome", "DilutedEPS")
CRORE = 1e7


class FactsError(Exception):
    pass


def fetch(sym, years=6):
    now = int(time.time())
    types = ",".join("quarterly" + t for t in TYPES)
    last = "no answer"
    for host in HOSTS:
        url = URL % (host, urllib.parse.quote(sym + ".NS", safe=""), types, now - years * 366 * 86400, now + 86400)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = "HTTP %d" % e.code
            e.close()
            if e.code == 404:
                raise FactsError("Yahoo has no fundamentals for %s.NS: check the symbol" % sym)
        except (urllib.error.URLError, OSError) as e:
            last = "could not connect: %s" % getattr(e, "reason", e)
        time.sleep(1)
    raise FactsError("Yahoo did not answer for %s (%s)" % (sym, last))


def parse(text, sym):
    """Timeseries JSON -> {period_end 'YYYY-MM-DD': {revenue, operating, net, eps}} (rupees)."""
    try:
        results = json.loads(text)["timeseries"]["result"] or []
    except (ValueError, KeyError, TypeError):
        raise FactsError("Yahoo returned something unexpected for %s" % sym)
    names = {"quarterlyTotalRevenue": "revenue", "quarterlyOperatingIncome": "operating",
             "quarterlyNetIncome": "net", "quarterlyDilutedEPS": "eps"}
    q, cur = {}, set()
    for res in results:
        for key, field in names.items():
            for row in res.get(key) or []:
                if not row or row.get("periodType") != "3M":
                    continue
                raw = (row.get("reportedValue") or {}).get("raw")
                if raw is not None and row.get("asOfDate"):
                    q.setdefault(row["asOfDate"], {})[field] = float(raw)
                    if field != "eps":
                        cur.add(row.get("currencyCode") or "INR")
    if not q:
        raise FactsError("Yahoo has no quarterly results for %s.NS" % sym)
    if len(cur) > 1:
        raise FactsError("%s reports in more than one currency (%s): read the filing" % (sym, ", ".join(sorted(cur))))
    return q, (cur.pop() if cur else "INR")


def _date(s):
    return datetime.date.fromisoformat(s)


def year_ago(quarters, end):
    """The same quarter a year earlier, matched by period end within 10 days, or None."""
    target = _date(end).replace(year=_date(end).year - 1) if not (end[5:] == "02-29") else None
    if target is None:
        return None
    for e in quarters:
        if abs((_date(e) - target).days) <= 10:
            return e
    return None


def growth(cur, old):
    if cur is None or old is None or old == 0:
        return None
    if old < 0:
        return None            # growth against a loss is not a meaningful percentage
    return (cur / old - 1.0) * 100.0


def consecutive(ends):
    """True if these period ends are about three months apart, oldest first."""
    gaps = [(_date(b) - _date(a)).days for a, b in zip(ends, ends[1:])]
    return all(80 <= g <= 100 for g in gaps)


def analyse(quarters, n, divisor=CRORE):
    ends = sorted(quarters)
    shown = ends[-n:]
    rows = []
    for e in shown:
        v = quarters[e]
        ya = year_ago(quarters, e)
        yv = quarters.get(ya) if ya else None
        row = {"period_end": e, "revenue": amt(v.get("revenue"), divisor), "operating_income": amt(v.get("operating"), divisor),
               "net_income": amt(v.get("net"), divisor), "eps": v.get("eps"),
               "operating_margin": margin(v.get("operating"), v.get("revenue")),
               "net_margin": margin(v.get("net"), v.get("revenue")),
               "revenue_yoy": growth(v.get("revenue"), (yv or {}).get("revenue")),
               "net_income_yoy": growth(v.get("net"), (yv or {}).get("net")),
               "eps_yoy": growth(v.get("eps"), (yv or {}).get("eps")),
               "year_ago_found": ya is not None}
        rows.append(row)
    ttm = None
    last4 = ends[-4:]
    if len(last4) == 4 and consecutive(last4) and all("revenue" in quarters[e] and "net" in quarters[e] for e in last4):
        ttm = {"through": last4[-1], "revenue": amt(sum(quarters[e]["revenue"] for e in last4), divisor),
               "net_income": amt(sum(quarters[e]["net"] for e in last4), divisor),
               "eps": round(sum(quarters[e]["eps"] for e in last4), 2) if all("eps" in quarters[e] for e in last4) else None}
    gaps = [(a, b) for a, b in zip(ends, ends[1:]) if not 80 <= (_date(b) - _date(a)).days <= 100]
    return rows, ttm, gaps


def amt(x, divisor):
    return None if x is None else round(x / divisor, 2)


def margin(a, b):
    return None if a is None or not b else round(a / b * 100.0, 1)


def fmt(x, nd=2, suffix=""):
    return "-" if x is None else ("{:,.%df}%s" % (nd, suffix)).format(x)


def render(sym, rows, ttm, gaps, unit):
    out = ["%s (NSE), quarterly results, %s (Yahoo Finance, unofficial)" % (sym, unit),
           "%-11s %12s %8s %12s %8s %7s %7s %7s" % ("quarter end", "revenue", "YoY", "net income", "YoY", "EPS", "op mgn", "net mgn")]
    for r in rows:
        out.append("%-11s %12s %8s %12s %8s %7s %7s %7s" % (
            r["period_end"], fmt(r["revenue"], 0), fmt(r["revenue_yoy"], 1, "%"), fmt(r["net_income"], 0),
            fmt(r["net_income_yoy"], 1, "%"), fmt(r["eps"]), fmt(r["operating_margin"], 1, "%"), fmt(r["net_margin"], 1, "%")))
    if ttm:
        out.append("Last four quarters (through %s): revenue %s, net income %s%s." % (
            ttm["through"], fmt(ttm["revenue"], 0), fmt(ttm["net_income"], 0),
            (", EPS %s" % fmt(ttm["eps"])) if ttm["eps"] is not None else ""))
    else:
        out.append("No four-quarter total: the latest four quarters are not all there and consecutive.")
    for a, b in gaps:
        out.append("MISSING: Yahoo has no quarter between %s and %s. Nothing is filled in." % (a, b))
    blank = [r["period_end"] for r in rows if not r["year_ago_found"]]
    if blank:
        out.append("No year-ago quarter in Yahoo for %s, so growth is blank there. Yahoo's free feed holds "
                   "only the latest few quarters; the filings have the rest." % ", ".join(blank))
    for r in rows:
        if r["net_income"] is not None and r["operating_income"] is not None \
                and r["net_income"] > r["operating_income"]:
            out.append("%s: net income is above operating income, so gains or tax items outside the "
                       "business are inside it. Read the filing." % r["period_end"])
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Quarterly results side by side (trader-analyst). Numbers only.")
    ap.add_argument("symbols", nargs="+", help="NSE symbols, e.g. RELIANCE TCS")
    ap.add_argument("--quarters", type=int, default=6, help="quarters to show (default 6)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--metrics", metavar="FILE", help="merge one row per ticker into this JSON file")
    ap.add_argument("--offline", metavar="DIR", help="read DIR/<SYMBOL>.json instead of the network")
    a = ap.parse_args(argv)
    docs, rc = [], 0
    for i, sym in enumerate(s.upper() for s in a.symbols):
        try:
            if a.offline:
                with open(os.path.join(a.offline, sym + ".json"), encoding="utf-8") as fh:
                    text = fh.read()
            else:
                if i:
                    time.sleep(0.5)
                text = fetch(sym)
            quarters, currency = parse(text, sym)
            divisor, unit = (CRORE, "INR crore (1 crore = 10 million)") if currency == "INR" else (1e6, "%s million: NOT rupees, this company reports in %s" % (currency, currency))
            rows, ttm, gaps = analyse(quarters, a.quarters, divisor)
            docs.append({"symbol": sym, "unit": unit, "currency": currency, "quarters": rows, "ttm": ttm, "gaps": gaps})
            if not a.json:
                print(render(sym, rows, ttm, gaps, unit) + "\n")
        except (FactsError, OSError) as e:
            print("facts.py: %s" % e, file=sys.stderr)
            rc = 1
    if a.json:
        print(json.dumps(docs, indent=2))
    if a.metrics and docs:
        cur = {}
        if os.path.exists(a.metrics):
            with open(a.metrics, encoding="utf-8") as fh:
                cur = json.load(fh)
        by = {c["ticker"]: c for c in cur.get("companies", [])}
        for d in docs:
            last = d["quarters"][-1]
            by[d["symbol"]] = {"ticker": d["symbol"], "period_end": last["period_end"], "unit": d["unit"], "revenue_ttm": (d["ttm"] or {}).get("revenue"),
                               "net_income_ttm": (d["ttm"] or {}).get("net_income"), "eps_ttm": (d["ttm"] or {}).get("eps"),
                               "revenue_growth_yoy": last["revenue_yoy"], "net_income_growth_yoy": last["net_income_yoy"],
                               "eps_growth_yoy": last["eps_yoy"], "operating_margin": last["operating_margin"],
                               "net_margin": last["net_margin"], "source": "Yahoo Finance fundamentals time series"}
        cur = {"as_of": datetime.date.today().isoformat(), "companies": [by[k] for k in sorted(by)]}
        d = os.path.dirname(a.metrics)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(a.metrics, "w", encoding="utf-8") as fh:
            json.dump(cur, fh, indent=2)
            fh.write("\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
