#!/usr/bin/env python3
"""Chart Scanner for swing-scanner: NSE daily setups. Standard library only.

    python3 scan.py universe                       # NSE equity list -> trader/universe.txt
    python3 scan.py daily                          # after 15:50 IST -> trader/watchlist.json
    python3 scan.py daily --symbols 'TCS,M&M,INFY' # or --limit 300
    python3 scan.py daily --now "2026-11-18 16:00" --offline tests/fixtures/india

universe  NSE's EQUITY_L.csv, series EQ (add --include-be for the trade-for-
          trade BE series), one symbol per line.

daily     Stage 1: one year of daily closes for every symbol (Yahoo spark, 20
          a request); a chart moves on if any setup fires on the closes of
          the last final day and the close is >= --min-price (Rs 50).
          Stage 2: the full daily bars (Yahoo chart) for up to --max-confirm
          (200) candidates: the setups again with real highs and lows, the
          20-day average traded value (close x volume) >= --min-traded-value
          (Rs 5 crore), and the NSE price band (2 % and 5 % bands are out by
          default: they can lock at the limit and you cannot get out).
          Delivery % from NSE's bhavcopy is shown when it is published.

A day's bar counts only after 15:50 IST (the close plus the data delay);
before that the scan is as of the previous trading day.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from india import cli, data, indicators, market, money, symbols  # noqa: E402

NOTE = "A scan is a list of charts that match a rule, not a list of stocks to buy. Not financial advice."


def cmd_universe(ctx, a):
    rows = data.nse_equity_list(ctx.fetcher)
    series = {"EQ", "BE"} if (a.include_be or ctx.cfg.get("include_be")) else {"EQ"}
    syms = sorted({r["symbol"] for r in rows if r["series"] in series})
    with open(ctx.path("universe.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(s + "\n" for s in syms))
    ctx.emit({"count": len(syms), "series": sorted(series), "symbols": syms},
             "%d NSE symbols (series %s) -> %s" % (len(syms), "+".join(sorted(series)),
                                                  os.path.join(ctx.dir, "universe.txt")))
    return 0


def load_symbols(ctx, a):
    if a.symbols:
        raw = [s for s in a.symbols.split(",") if s.strip()]
    else:
        path = os.path.join(ctx.dir, "universe.txt")
        if not os.path.exists(path):
            cmd_universe(ctx, argparse.Namespace(include_be=False)) if not ctx.json else None
        if not os.path.exists(path):
            rows = data.nse_equity_list(ctx.fetcher)
            raw = sorted({r["symbol"] for r in rows if r["series"] == "EQ"})
        else:
            with open(path, encoding="utf-8") as fh:
                raw = [l.strip() for l in fh if l.strip()]
    if a.limit:
        raw = raw[:a.limit]
    out, notes = [], []
    for r in raw:
        try:
            out.append(symbols.parse(r))
        except ValueError as e:
            notes.append(str(e))
    return out, notes


def upto(bars, as_of):
    bars = [b for b in bars if b["d"] <= as_of]
    return bars if bars and bars[-1]["d"] == as_of else None


def cmd_daily(ctx, a):
    as_of = market.last_final_bar_date(ctx.now).isoformat()
    min_price = ctx.cfg["min_price"] if a.min_price is None else a.min_price
    min_tv = ctx.cfg["min_traded_value"] if a.min_traded_value is None else a.min_traded_value
    block = set(ctx.cfg["block_bands"]) if a.bands is None else {b for b in ["2", "5", "10", "20", "-"]
                                                                     if b not in a.bands.split(",")}
    syms, notes = load_symbols(ctx, a)
    closes = data.yahoo_spark(ctx.fetcher, syms, "1y")
    cands = []
    for s in syms:
        bars = upto(closes.get(s.code) or [], as_of)
        if not bars:
            notes.append("%s: no daily close for %s" % (symbols.display(s), as_of))
            continue
        if bars[-1]["c"] < min_price:
            continue
        if indicators.setups_at(bars, len(bars) - 1):
            cands.append(s)
    if len(cands) > a.max_confirm:
        notes.append("stage 2 stopped at %d of %d candidates (--max-confirm)" % (a.max_confirm, len(cands)))
        cands = cands[:a.max_confirm]
    try:
        bands = data.nse_price_bands(ctx.fetcher)
    except data.DataError as e:
        bands = {}
        notes.append("price bands unavailable: %s" % e)
    delivery = data.nse_delivery(ctx.fetcher, market.last_final_bar_date(ctx.now))
    hits = []
    for s in cands:
        try:
            bars = upto(data.yahoo_daily(ctx.fetcher, s, "1y"), as_of)
        except data.DataError as e:
            notes.append("%s: %s" % (symbols.display(s), e))
            continue
        if not bars:
            continue
        tv = indicators.avg_traded_value(bars, 20) or 0.0
        band = bands.get(s.code, "?") if s.exchange == "NSE" else "?"
        if tv < min_tv or band in block or bars[-1]["c"] < min_price:
            continue
        for setup, level in sorted(indicators.setups_at(bars, len(bars) - 1).items()):
            hits.append({"symbol": s.code, "exchange": s.exchange, "setup": setup,
                         "level": None if level is None else round(level, 2), "close": bars[-1]["c"],
                         "traded_value": round(tv), "band": band, "delivery_pct": delivery.get(s.code)})
    doc = {"generated": ctx.now.strftime("%Y-%m-%d %H:%M"), "as_of": as_of, "scanned": len(syms),
           "candidates": len(cands), "hits": hits, "notes": notes}
    ctx.write("watchlist.json", doc)
    lines = ["Daily scan as of %s (IST close): %d charts, %d candidates, %d hits." % (
        as_of, len(syms), len(cands), len(hits))]
    for h in hits:
        lines.append("  %-12s %-16s close %s  level %s  avg traded %s/day  band %s%s" % (
            h["symbol"], h["setup"], money.inr(h["close"]),
            "-" if h["level"] is None else money.inr(h["level"]), money.crore(h["traded_value"]),
            h["band"], "" if h["delivery_pct"] is None else "  delivery %.0f%%" % h["delivery_pct"]))
    lines += ["  note: " + n for n in notes[:10]]
    lines.append(NOTE + " Next: /swing-news on the hits, then /swing-entry.")
    ctx.emit(doc, "\n".join(lines))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scan.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    u = sub.add_parser("universe")
    u.add_argument("--include-be", action="store_true")
    cli.common_args(u)
    d = sub.add_parser("daily")
    d.add_argument("--symbols", help="comma-separated, e.g. TCS,M&M,INFY")
    d.add_argument("--limit", type=int)
    d.add_argument("--min-price", type=float)
    d.add_argument("--min-traded-value", type=float)
    d.add_argument("--bands", help="price bands to allow, e.g. 10,20,- (default: config block_bands out)")
    d.add_argument("--max-confirm", type=int, default=200)
    cli.common_args(d)
    a = ap.parse_args(argv)
    ctx = cli.Ctx(a)
    return cmd_universe(ctx, a) if a.command == "universe" else cmd_daily(ctx, a)


if __name__ == "__main__":
    sys.exit(main())
