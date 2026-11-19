#!/usr/bin/env python3
"""Entry Timer for swing-entry: the daily CLOSE that confirms a setup. Standard library only.

    python3 entry.py check TCS --setup breakout_20d        # level from the setup's last firing
    python3 entry.py check TCS --level 3400 --write        # your own level -> trader/entry.json
    python3 entry.py check TCS --level 3400 --pre-close    # 15:00-15:30 IST: today's forming bar, provisional
    python3 entry.py watchlist                             # every hit in trader/watchlist.json

The trigger is the first completed daily bar after the setup that CLOSES
above the level (with --min-volume-x, on at least that multiple of the
20-day average volume). An intraday poke above the level is not an entry.

States
  waiting    no close above the level yet (how far it is)
  triggered  closed above: the date, the close, and the order for the next session
  stale      triggered more than 2 trading days ago AND now more than 3 % above the level
  failed     closed above, then closed back under the level

The suggested order is for the next session (valid_for): a LIMIT buy at the
trigger close + 0.5 % (config entry_limit_buffer_pct), or with
--entry-style sl-buy a stop-limit buy that triggers one tick above the
trigger bar's high. Prices are on NSE ticks. Nothing is ever placed.
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from india import cli, data, indicators, market, money, symbols, ticks  # noqa: E402

STALE_DAYS = 2
STALE_PCT = 3.0
TRIGGERS_ON_SETUP_BAR = {"breakout_20d", "breakout_52w"}
PRE_CLOSE_FROM = datetime.time(15, 0)


def _pre_close_window(now):
    return market.is_trading_day(now.date()) and PRE_CLOSE_FROM <= now.time() < market.CLOSE


def suggest_order(ref_close, ref_high, valid, cfg):
    """The buy for session `valid`, priced off the latest completed bar."""
    sched = cfg.get("tick_schedule")
    buf = 1 + float(cfg.get("entry_limit_buffer_pct", 0.5)) / 100
    if cfg.get("entry_style") == "sl-buy":
        hi = ticks.round_up(ref_high, sched)
        trig = round(hi + ticks.tick_paise(hi, sched) / 100.0, 2)
        return {"style": "sl-buy", "trigger": trig, "price": ticks.round_up(trig * buf, sched), "valid_for": valid}
    return {"style": "limit", "price": ticks.round_up(ref_close * buf, sched), "valid_for": valid}


def evaluate(bars, level, since, now, cfg, pre_close=False, min_volume_x=None):
    provisional_ok = pre_close and _pre_close_window(now)
    last_final = market.last_final_bar_date(now).isoformat()
    today = now.date().isoformat()
    usable = [b for b in bars if b["d"] <= last_final or (provisional_ok and b["d"] == today)]
    res = {"level": level, "state": "waiting", "late_sessions": None, "trigger_date": None, "trigger_close": None,
           "trigger_high": None, "distance_pct": None, "provisional": False, "reason": "",
           "as_of": usable[-1]["d"] if usable else None}
    if not usable:
        res["reason"] = "no completed daily bars"
        return res
    trig_i, vol_note = None, ""
    for i, b in enumerate(usable):
        if b["d"] <= since or b["c"] <= level:
            continue
        if min_volume_x:
            prior = usable[max(0, i - 20):i]
            avg = sum(x["v"] for x in prior) / len(prior) if prior else 0
            if avg and b["v"] < min_volume_x * avg:
                vol_note = "the %s close %s was above the level but on %.2fx the 20-day volume, under %.2fx" % (
                    b["d"], money.inr(b["c"]), b["v"] / avg, min_volume_x)
                continue
        trig_i = i
        break
    last = usable[-1]
    if trig_i is None:
        res["distance_pct"] = round((level - last["c"]) / last["c"] * 100, 4)
        res["reason"] = vol_note or "last close %s (%s), %.2f%% under the level %s" % (
            money.inr(last["c"]), last["d"], res["distance_pct"], money.inr(level))
        return res
    t = usable[trig_i]
    res.update(trigger_date=t["d"], trigger_close=t["c"], trigger_high=t["h"],
               provisional=bool(provisional_ok and t["d"] == today))
    after = usable[trig_i + 1:]
    above_pct = (last["c"] / level - 1) * 100
    days = market.trading_days_between(datetime.date.fromisoformat(t["d"]), datetime.date.fromisoformat(last["d"]))
    if any(b["c"] < level for b in after):
        res["state"] = "failed"
        res["reason"] = "closed above %s on %s, then back under it" % (money.inr(level), t["d"])
        return res
    if days > STALE_DAYS and above_pct > STALE_PCT:
        res["state"] = "stale"
        res["reason"] = ("triggered %s, %d sessions ago, and now %.1f%% above the level: a late entry is a "
                         "different trade with a wider stop" % (t["d"], days, above_pct))
        return res
    res["state"] = "triggered"
    res["late_sessions"] = days
    if last["d"] == today and provisional_ok:
        valid = today                                    # pre-close: buy in today's closing minutes
    else:
        valid = market.next_trading_day(datetime.date.fromisoformat(last["d"])).isoformat()
    res["order"] = suggest_order(last["c"], last["h"], valid, cfg)
    res["reason"] = "the %s bar closed at %s, above %s%s" % (
        t["d"], money.inr(t["c"]), money.inr(level),
        " (%.1f%% above the level: extended)" % above_pct if above_pct > STALE_PCT else "")
    if days:
        res["reason"] += ("; that was %d session%s ago, so the order is priced off the latest close %s (%s)"
                          % (days, "" if days == 1 else "s", money.inr(last["c"]), last["d"]))
    if res["provisional"]:
        res["reason"] += "; PROVISIONAL: today's bar has not closed"
    return res


def find_setup(bars, setup, lookback=10):
    rsi = indicators.rsi_wilder([b["c"] for b in bars])
    for i in range(len(bars) - 1, max(-1, len(bars) - 1 - lookback), -1):
        got = indicators.setups_at(bars, i, rsi)
        if setup in got and got[setup] is not None:
            since = bars[i - 1]["d"] if setup in TRIGGERS_ON_SETUP_BAR and i else bars[i]["d"]
            return got[setup], since, bars[i]["d"]
    return None


def check_one(ctx, sym, setup=None, level=None, since=None, pre_close=False, min_volume_x=None):
    s = symbols.parse(sym)
    bars = data.yahoo_daily(ctx.fetcher, s, "1y")
    final = data.drop_unfinished(bars, ctx.now)
    setup_date = None
    if level is None:
        found = find_setup(final, setup)
        if not found:
            raise ValueError("%s did not fire on %s in the last 10 sessions" % (setup, symbols.display(s)))
        level, auto_since, setup_date = found
        since = since or auto_since
    if since is None:
        since = final[-6]["d"] if len(final) > 6 else final[0]["d"]
    r = evaluate(bars, round(level, 2), since, ctx.now, ctx.cfg, pre_close, min_volume_x)
    r.update(symbol=s.code, exchange=s.exchange, setup=setup or "level", setup_date=setup_date)
    return r


def render(r):
    head = "%s %s: %s" % (symbols.display(symbols.Sym(r["symbol"], r["exchange"])), r["setup"], r["state"].upper())
    lines = [head, "  " + r["reason"]]
    o = r.get("order")
    if o:
        if o["style"] == "limit":
            lines.append("  Next session (%s): LIMIT buy at %s." % (o["valid_for"], money.inr(o["price"])))
        else:
            lines.append("  Next session (%s): SL-BUY trigger %s, limit %s." % (
                o["valid_for"], money.inr(o["trigger"]), money.inr(o["price"])))
        lines.append("  Next: /swing-exit to set the stop and target before anything else.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="entry.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check")
    c.add_argument("symbol")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--setup")
    g.add_argument("--level", type=float)
    c.add_argument("--since", help="only closes after this date count (YYYY-MM-DD)")
    c.add_argument("--min-volume-x", type=float)
    c.add_argument("--pre-close", action="store_true")
    c.add_argument("--entry-style", choices=["limit", "sl-buy"])
    c.add_argument("--write", action="store_true")
    cli.common_args(c)
    w = sub.add_parser("watchlist")
    w.add_argument("--min-volume-x", type=float)
    cli.common_args(w)
    a = ap.parse_args(argv)
    ctx = cli.Ctx(a)
    if getattr(a, "entry_style", None):
        ctx.cfg["entry_style"] = a.entry_style
    if a.command == "check":
        try:
            r = check_one(ctx, a.symbol, a.setup, a.level, a.since, a.pre_close, a.min_volume_x)
        except (ValueError, data.DataError) as e:
            ctx.emit({"error": str(e)}, "entry: %s" % e)
            return 2
        if a.write:
            ctx.write("entry.json", r)
        ctx.emit(r, render(r) + ("\n  Saved trader/entry.json." if a.write else ""))
        return 0
    wl = ctx.read("watchlist.json")
    if not wl:
        ctx.emit({"error": "no trader/watchlist.json"}, "entry: no trader/watchlist.json; run /swing-scanner first")
        return 2
    out = []
    for h in wl.get("hits", []):
        if h.get("level") is None:
            continue
        since = h["as_of"] if "as_of" in h else wl["as_of"]
        if h["setup"] in TRIGGERS_ON_SETUP_BAR:
            since = market.prev_trading_day(datetime.date.fromisoformat(wl["as_of"])).isoformat()
        try:
            r = check_one(ctx, h["symbol"] if h.get("exchange", "NSE") == "NSE" else "BSE:" + h["symbol"],
                          h["setup"], h["level"], since, False, a.min_volume_x)
        except (ValueError, data.DataError) as e:
            out.append({"symbol": h["symbol"], "setup": h["setup"], "state": "error", "reason": str(e)})
            continue
        out.append(r)
    ctx.emit({"results": out}, "\n".join(render(r) if r["state"] != "error" else
                                         "%s %s: ERROR %s" % (r["symbol"], r["setup"], r["reason"]) for r in out)
             + "\nPick one and run check SYMBOL --setup NAME --write. Not financial advice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
