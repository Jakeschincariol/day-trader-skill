#!/usr/bin/env python3
"""Price Alerts for swing-alerts: after-close checks on open swing positions. Standard library only.

    python3 alerts.py check              # after 15:50 IST; exit 0 = something rang, 1 = nothing new
    python3 alerts.py clock              # NSE open or closed, next session, today's holiday
    python3 alerts.py quote TCS 'M&M' --write
    python3 alerts.py quote --holdings --write     # -> trader/prices.json

For each position in trader/positions.json, on the last final daily bar:
  gap_through      opened below the stop
  stop_touched     the low reached the stop (the GTT should have fired)
  below_gtt_limit  the low went under the GTT's limit: it may not have filled
  target_touched   the high reached the target
  time_stop_tomorrow  the time stop is next session: sell by its close
  time_stop        the time stop date has passed: out next session
  results_tomorrow results are due next session      (optional nse package)
  ex_date_tomorrow a dividend, split or bonus goes ex next session (nse)
  band_changed     NSE moved the stock to another price band
Each alert rings once (trader/state/alerts.json). An alert is information,
never an order.
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from india import cli, data, market, money, symbols  # noqa: E402


def daily_alerts(position, bar, prev_close, today, results, actions, band_now, band_before):
    sym, d = position["symbol"], bar["d"]
    tomorrow = market.next_trading_day(today).isoformat()
    out = []

    def ring(kind, msg):
        out.append({"id": "%s:%s:%s" % (sym, kind, d), "symbol": sym, "kind": kind, "message": msg})
    stop, lim, target = float(position["stop"]), float(position["gtt_stop_limit"]), float(position["target"])
    if bar["o"] < stop:
        ring("gap_through", "%s opened at %s, below your stop %s (previous close %s): a gap through the stop." % (
            sym, money.inr(bar["o"]), money.inr(stop), money.inr(prev_close)))
    if bar["l"] <= stop:
        ring("stop_touched", "%s traded down to %s on %s: your stop %s was hit. Check that the GTT sold." % (
            sym, money.inr(bar["l"]), d, money.inr(stop)))
    if bar["l"] < lim:
        ring("below_gtt_limit", "%s went under the GTT limit %s (low %s): the stop order may not have filled. "
             "Check your holdings now." % (sym, money.inr(lim), money.inr(bar["l"])))
    if bar["h"] >= target:
        ring("target_touched", "%s reached %s on %s: your target %s. Check that the GTT sold." % (
            sym, money.inr(bar["h"]), d, money.inr(target)))
    ts = position.get("time_stop_date")
    if ts and tomorrow == ts:
        ring("time_stop_tomorrow", "%s: time stop is tomorrow, %s. The plan says sell by that session's close "
             "if neither the stop nor the target is hit; cancel the GTT when you do." % (sym, ts))
    if ts and today.isoformat() >= ts:
        ring("time_stop", "%s: the time stop (%s) has passed; the plan said out by that close (last close %s). "
             "Sell next session and cancel the GTT." % (sym, ts, money.inr(bar["c"])))
    if tomorrow in (results or []):
        ring("results_tomorrow", "%s reports results on %s, next session: expect a gap either way." % (sym, tomorrow))
    for act in actions or []:
        if act.get("ex_date") == tomorrow:
            ring("ex_date_tomorrow", "%s goes ex on %s (%s): the price will drop by it; do not read that as the stop." % (
                sym, tomorrow, act.get("purpose", "")))
    if band_now and band_before and band_now != band_before:
        ring("band_changed", "%s price band changed from %s to %s." % (sym, band_before, band_now))
    return out


def cmd_check(ctx, a):
    positions = (ctx.read("positions.json") or {}).get("positions", [])
    as_of = market.last_final_bar_date(ctx.now)
    state = ctx.read("state/alerts.json") or {"fired": [], "bands": {}}
    try:
        bands = data.nse_price_bands(ctx.fetcher)
    except data.DataError:
        bands = {}
    syms = sorted({p["symbol"] for p in positions})
    nxt = market.next_trading_day(as_of)
    results = (ctx.nse.results_dates(syms, nxt, nxt) if syms else {}) or {}
    actions = (ctx.nse.corporate_actions(syms, nxt, nxt) if syms else {}) or {}
    ctx.nse_notice()
    rang, notes = [], []
    for p in positions:
        try:
            bars = [b for b in data.yahoo_daily(ctx.fetcher, symbols.Sym(p["symbol"], p.get("exchange", "NSE")), "1y")
                    if b["d"] <= as_of.isoformat()]
        except data.DataError as e:
            notes.append("%s: %s" % (p["symbol"], e))
            continue
        if len(bars) < 2 or bars[-1]["d"] != as_of.isoformat():
            notes.append("%s: no bar for %s" % (p["symbol"], as_of))
            continue
        got = daily_alerts(p, bars[-1], bars[-2]["c"], as_of, results.get(p["symbol"], []),
                           actions.get(p["symbol"], []), bands.get(p["symbol"]), state["bands"].get(p["symbol"]))
        for al in got:
            if al["id"] not in state["fired"]:
                state["fired"].append(al["id"])
                rang.append(al)
        if bands.get(p["symbol"]):
            state["bands"][p["symbol"]] = bands[p["symbol"]]
    state["fired"] = state["fired"][-500:]
    ctx.write("state/alerts.json", state)
    head = "Alerts as of the %s close (%d open position%s)." % (as_of, len(positions), "" if len(positions) == 1 else "s")
    lines = [head] + ["  RING " + al["message"] for al in rang] + ["  note: " + n for n in notes]
    if not rang:
        lines.append("  Nothing new.")
    lines.append("An alert is information, never an order. Not financial advice.")
    ctx.emit({"as_of": as_of.isoformat(), "rang": rang, "notes": notes}, "\n".join(lines))
    return 0 if rang else 1


def cmd_clock(ctx, a):
    s = market.market_status(ctx.now)
    text = "NSE %s at %s IST (%s)" % ("OPEN" if s["open"] else "CLOSED", ctx.now.strftime("%Y-%m-%d %H:%M"), s["reason"])
    if not s["open"]:
        text += "; next session %s IST" % s["next_open"].replace("T", " ")
    ctx.emit(s, text)
    return 0


def cmd_quote(ctx, a):
    names = list(a.symbols or [])
    if a.holdings:
        names += [p["symbol"] for p in (ctx.read("positions.json") or {}).get("positions", [])]
        plan = ctx.read("plan.json")
        if plan:
            names.append(plan["symbol"])
    prices, notes = {}, []
    for n in dict.fromkeys(names):
        try:
            s = symbols.parse(n)
            bars = [b for b in data.yahoo_daily(ctx.fetcher, s, "1y") if b["d"] <= ctx.now.date().isoformat()]
        except (ValueError, data.DataError) as e:
            notes.append(str(e))
            continue
        if len(bars) >= 2:
            prices[s.code] = {"last": bars[-1]["c"], "date": bars[-1]["d"], "prev_close": bars[-2]["c"], "currency": "INR"}
    doc = {"as_of": ctx.now.strftime("%Y-%m-%d %H:%M"), "prices": prices, "notes": notes}
    if a.write:
        ctx.write("prices.json", doc)
    ctx.emit(doc, "\n".join("%-12s %s (%s), previous close %s" % (k, money.inr(v["last"]), v["date"], money.inr(v["prev_close"]))
                            for k, v in prices.items()) + "".join("\n  note: " + n for n in notes)
             + "\nFree delayed data; check your broker before acting.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="alerts.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check")
    cli.common_args(c)
    k = sub.add_parser("clock")
    cli.common_args(k)
    q = sub.add_parser("quote")
    q.add_argument("symbols", nargs="*")
    q.add_argument("--holdings", action="store_true")
    q.add_argument("--write", action="store_true")
    cli.common_args(q)
    a = ap.parse_args(argv)
    ctx = cli.Ctx(a)
    return {"check": cmd_check, "clock": cmd_clock, "quote": cmd_quote}[a.command](ctx, a)


if __name__ == "__main__":
    sys.exit(main())
