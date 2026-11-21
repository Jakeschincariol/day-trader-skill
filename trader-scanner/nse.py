#!/usr/bin/env python3
"""Read public NSE stock and derivatives data for the Indian market adapter.

Uses public pages and JSON endpoints on https://www.nseindia.com. The NSE website
may change endpoints, return 403, delay data, or require a browser cookie. This
module performs no order and does not replace exchange official data feeds.
"""

import argparse
import datetime
import http.cookiejar
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.nseindia.com"
ALT_BASE = "https://www.nseindia.in"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


class NSEError(Exception):
    pass


def symbol_name(symbol):
    symbol = str(symbol or "").strip().upper()
    for suffix in (".NS", ".BO"):
        if symbol.endswith(suffix):
            symbol = symbol[:-len(suffix)]
    return symbol.replace(" ", "-")


def _cookie_opener():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    return opener


def fetch_json(path, opener=None, timeout=20):
    opener = opener or _cookie_opener()
    last_error = None
    for base in (BASE, ALT_BASE):
        try:
            opener.open(urllib.request.Request(base + "/", headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,*/*",
                "Accept-Language": "en-IN,en;q=0.9",
                "Cache-Control": "no-cache",
            }), timeout=timeout)
            referer = base + "/"
            if "symbol=" in path:
                sym = urllib.parse.quote(symbol_name(path.split("symbol=")[-1]))
                referer = base + "/get-quotes/equity?symbol=" + sym
            req = urllib.request.Request(base + path, headers={
                "User-Agent": UA,
                "Accept": "application/json,text/plain,*/*;q=0.8",
                "Referer": referer,
                "Accept-Language": "en-IN,en;q=0.9",
                "Connection": "keep-alive",
                "Cache-Control": "no-cache",
            })
            with opener.open(req, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
            return data
        except urllib.error.HTTPError as exc:
            last_error = "NSE answered HTTP %d for %s" % (exc.code, base + path)
        except (urllib.error.URLError, OSError) as exc:
            last_error = "could not reach NSE: %s" % getattr(exc, "reason", exc)
        except json.JSONDecodeError:
            last_error = "NSE returned invalid JSON for %s" % (base + path)
    raise NSEError(last_error or "NSE public data was unavailable")


def quote(symbol, offline_doc=None, opener=None):
    symbol = symbol_name(symbol)
    doc = offline_doc
    if doc is None:
        doc = fetch_json("/api/quote-equity?symbol=" + urllib.parse.quote(symbol), opener=opener)
    try:
        info = doc["info"]
        price = doc["priceInfo"]
    except (KeyError, TypeError):
        raise NSEError("NSE quote response has an unexpected shape")
    return {
        "symbol": info.get("symbol") or symbol,
        "company_name": info.get("companyName"),
        "industry": info.get("industry"),
        "exchange": "NSE",
        "currency": "INR",
        "last": price.get("lastPrice"),
        "change": price.get("change"),
        "pchange": price.get("pChange"),
        "open": price.get("open"),
        "day_high": price.get("intraDayHighLow", {}).get("max"),
        "day_low": price.get("intraDayHighLow", {}).get("min"),
        "previous_close": price.get("previousClose"),
        "week_52_high": doc.get("securityWiseDP", {}).get("secWiseQuotes", {}).get("max")
                       or price.get("weekHighLow", {}).get("max"),
        "week_52_low": doc.get("securityWiseDP", {}).get("secWiseQuotes", {}).get("min")
                      or price.get("weekHighLow", {}).get("min"),
        "vwap": price.get("vwap"),
        "source": "NSE public website",
        "timestamp": doc.get("metadata", {}).get("lastUpdateTime"),
    }


def option_chain(symbol, expiry=None, offline_doc=None, opener=None):
    symbol = symbol_name(symbol)
    doc = offline_doc
    if doc is None:
        doc = fetch_json("/api/option-chain-equities?symbol=" + urllib.parse.quote(symbol), opener=opener)
    records = doc.get("records") or {}
    expiries = records.get("expiryDates") or []
    chosen = expiry
    if chosen is None:
        chosen = expiries[0] if expiries else None
    if chosen and chosen not in expiries:
        raise NSEError("expiry %s is not in NSE expiries: %s" % (chosen, ", ".join(expiries)))

    rows = []
    data = (doc.get("filtered") or {}).get("data")
    if not data:
        data = records.get("data") or []
    for record in data:
        if chosen and record.get("expiryDate") != chosen:
            continue
        strike = record.get("strikePrice")
        ce = record.get("CE") or {}
        pe = record.get("PE") or {}
        rows.append({
            "symbol": symbol,
            "exchange": "NSE",
            "expiry": record.get("expiryDate") or chosen,
            "strike": strike,
            "call": {
                "oi": ce.get("openInterest"), "change_oi": ce.get("changeinOpenInterest"),
                "volume": ce.get("totalTradedVolume"), "iv": ce.get("impliedVolatility"),
                "ltp": ce.get("lastPrice"), "bid": ce.get("bidprice"), "ask": ce.get("askPrice"),
            },
            "put": {
                "oi": pe.get("openInterest"), "change_oi": pe.get("changeinOpenInterest"),
                "volume": pe.get("totalTradedVolume"), "iv": pe.get("impliedVolatility"),
                "ltp": pe.get("lastPrice"), "bid": pe.get("bidprice"), "ask": pe.get("askPrice"),
            },
        })
    return {
        "symbol": symbol,
        "exchange": "NSE",
        "expiry": chosen,
        "expiries": expiries,
        "timestamp": records.get("timestamp") or doc.get("timestamp") or doc.get("records", {}).get("timestamp"),
        "underlying_value": records.get("underlyingValue"),
        "rows": rows,
        "source": "NSE public option chain",
    }


def oi_summary(symbol, expiry=None, offline_doc=None, opener=None):
    chain = option_chain(symbol, expiry=expiry, offline_doc=offline_doc, opener=opener)
    call_oi = sum((r["call"]["oi"] or 0) for r in chain["rows"])
    put_oi = sum((r["put"]["oi"] or 0) for r in chain["rows"])
    return dict(chain, call_oi=call_oi, put_oi=put_oi,
                put_call_oi=round(put_oi / call_oi, 4) if call_oi else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description="NSE public market data: equity quotes and option OI")
    sub = parser.add_subparsers(dest="cmd")
    q = sub.add_parser("quote", help="get NSE cash-market quote")
    q.add_argument("symbol")
    q.add_argument("--offline", help="saved NSE quote JSON")
    q.add_argument("--json", action="store_true")
    o = sub.add_parser("oi", help="get NSE option-chain open interest")
    o.add_argument("symbol")
    o.add_argument("--expiry", help="DD-MMM-YYYY, as shown by NSE")
    o.add_argument("--offline", help="saved NSE option-chain JSON")
    o.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 2
    try:
        if args.cmd == "quote":
            doc = json.load(open(args.offline, encoding="utf-8")) if args.offline else None
            result = quote(args.symbol, offline_doc=doc)
        else:
            doc = json.load(open(args.offline, encoding="utf-8")) if args.offline else None
            result = oi_summary(args.symbol, expiry=args.expiry, offline_doc=doc)
        if args.json:
            print(json.dumps(result, indent=2))
        elif args.cmd == "quote":
            print("{symbol} {last} INR | change {change:+} ({pchange:+.2f}%) | H {day_high} L {day_low} | prev {previous_close}".format(**result))
        else:
            print("{symbol} {expiry} | underlying {underlying_value} | call OI {call_oi:,} | put OI {put_oi:,} | P/C OI {put_call_oi}".format(**result))
        return 0
    except (NSEError, OSError, json.JSONDecodeError) as exc:
        print("nse.py: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
