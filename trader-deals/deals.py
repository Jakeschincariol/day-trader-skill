#!/usr/bin/env python3
"""Bulk and block deals for trader-deals: who bought and sold big on NSE, from NSE's own daily
files. Standard library only. The India stand-in for the US skill that read Congress's trades.

    python3 deals.py                                  # every bulk and block deal in the latest files
    python3 deals.py --symbols RELIANCE TCS           # only these
    python3 deals.py --min-value-cr 5 --json
    python3 deals.py --offline tests/fixtures/trader-deals

Files (no key, no login):
  https://archives.nseindia.com/content/equities/bulk.csv    bulk deals of the latest session
  https://nsearchives.nseindia.com/content/equities/block.csv   block deals of the latest session
Bulk deals are large day totals a buyer or seller must disclose; block deals are single large
trades. Both name the client. Each file holds ONE trading day, so run it every evening if you
want a history: --append FILE adds the rows to a JSON-lines file, once per date and row.

A deal shows who traded and at what price. It does not show why, and a seller one day is not a
signal for the next. Amounts are shown in crore rupees (1 crore = 10 million).
"""

import argparse
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.request

UA = "day-trader-skills-nse/1.0 (personal research tool)"
URLS = {"bulk": "https://archives.nseindia.com/content/equities/bulk.csv",
        "block": "https://nsearchives.nseindia.com/content/equities/block.csv"}
CRORE = 1e7


class DealsError(Exception):
    pass


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        code = e.code
        e.close()
        raise DealsError("NSE answered HTTP %d for %s" % (code, url))
    except (urllib.error.URLError, OSError) as e:
        raise DealsError("could not reach %s: %s" % (url, getattr(e, "reason", e)))


def parse(text, kind):
    """A bulk.csv or block.csv -> rows. A file with 'NO RECORDS' is a quiet day, not an error."""
    rows = []
    for r in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        r = {(k or "").strip(): (v or "").strip() for k, v in r.items()}
        if not r.get("Symbol") or r.get("Date", "").upper().startswith("NO RECORDS") or r["Symbol"].upper() == "NO RECORDS":
            continue
        try:
            qty = int(r["Quantity Traded"].replace(",", ""))
            price = float(r["Trade Price / Wght. Avg. Price"].replace(",", ""))
        except (KeyError, ValueError):
            raise DealsError("a %s row is not in the shape this tool knows: %r" % (kind, r))
        side = r.get("Buy/Sell", "").upper()
        rows.append({"kind": kind, "date": r["Date"], "symbol": r["Symbol"].upper(), "name": r.get("Security Name", ""),
                     "client": r.get("Client Name", ""), "side": side, "qty": qty, "price": price,
                     "value_cr": round(qty * price / CRORE, 2), "remarks": r.get("Remarks", "")})
    if not rows and "Symbol" not in text.split("\n", 1)[0]:
        raise DealsError("not an NSE %s deals file" % kind)
    return rows


def net_by_symbol(rows):
    net = {}
    for r in rows:
        n = net.setdefault(r["symbol"], {"symbol": r["symbol"], "bought_cr": 0.0, "sold_cr": 0.0})
        n["bought_cr" if r["side"] == "BUY" else "sold_cr"] += r["value_cr"]
    out = []
    for n in net.values():
        n["bought_cr"], n["sold_cr"] = round(n["bought_cr"], 2), round(n["sold_cr"], 2)
        n["net_cr"] = round(n["bought_cr"] - n["sold_cr"], 2)
        out.append(n)
    return sorted(out, key=lambda n: -abs(n["net_cr"]))


def render(rows, net):
    if not rows:
        return "No bulk or block deals match. The files hold one session; a quiet day is normal."
    out = ["%-11s %-6s %-12s %-4s %-5s %12s %10s %9s  %s" % ("date", "kind", "symbol", "side", "", "qty", "price", "cr", "client")]
    for r in sorted(rows, key=lambda r: -r["value_cr"]):
        out.append("%-11s %-6s %-12s %-4s %-5s %12s %10.2f %9.2f  %s" % (
            r["date"], r["kind"], r["symbol"], r["side"], "", "{:,}".format(r["qty"]), r["price"], r["value_cr"], r["client"]))
    out.append("")
    out.append("Net by stock (crore rupees, bought minus sold):")
    for n in net[:15]:
        out.append("  %-12s bought %9.2f  sold %9.2f  net %+9.2f" % (n["symbol"], n["bought_cr"], n["sold_cr"], n["net_cr"]))
    out.append("")
    out.append("Public data, not inside information. Who traded is not why they traded. Not financial advice.")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="NSE bulk and block deals (trader-deals).")
    ap.add_argument("--symbols", nargs="+")
    ap.add_argument("--min-value-cr", type=float, default=0.0, help="hide deals under this many crore rupees")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--offline", metavar="DIR", help="read bulk.csv and block.csv from DIR")
    ap.add_argument("--append", metavar="FILE", help="add new rows to this JSON-lines history file")
    a = ap.parse_args(argv)
    try:
        rows = []
        for kind in ("bulk", "block"):
            if a.offline:
                p = os.path.join(a.offline, kind + ".csv")
                if not os.path.exists(p):
                    raise DealsError("no %s.csv in %s" % (kind, a.offline))
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
            else:
                text = fetch(URLS[kind])
            rows += parse(text, kind)
    except DealsError as e:
        print("deals.py: %s" % e, file=sys.stderr)
        return 1
    want = {s.upper() for s in a.symbols} if a.symbols else None
    rows = [r for r in rows if (want is None or r["symbol"] in want) and r["value_cr"] >= a.min_value_cr]
    net = net_by_symbol(rows)
    if a.append:
        seen = set()
        if os.path.exists(a.append):
            with open(a.append, encoding="utf-8") as fh:
                seen = {line.strip() for line in fh if line.strip()}
        new = [json.dumps(r, sort_keys=True) for r in rows if json.dumps(r, sort_keys=True) not in seen]
        d = os.path.dirname(a.append)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(a.append, "a", encoding="utf-8") as fh:
            for line in new:
                fh.write(line + "\n")
    print(json.dumps({"deals": rows, "net": net}, indent=2) if a.json else render(rows, net))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
