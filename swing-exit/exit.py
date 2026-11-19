#!/usr/bin/env python3
"""Exit Planner for swing-exit: stop, target and time stop before the entry. Standard library only.

    python3 exit.py plan                                  # trader/entry.json, swing-low stop, 2R target
    python3 exit.py plan --stop atr:2 --target 3R --write # -> trader/plan.json
    python3 exit.py plan --entry 3412.40 --stop price:3296.10
    python3 exit.py show

Stops: swing-low[:N] (lowest low of the last N sessions to the trigger,
default 10), setup-low (the trigger day's low), atr:K (entry - K x ATR14),
pct:X, price:X. Rounded DOWN to a valid NSE tick. Refused if not below the
entry, or closer than 0.5 x ATR(14).
Targets: 1R, 2R (default), 3R, price:X, rounded to the nearest tick.
Time stop: --max-hold N trading days after the entry day (default 15).
GTT: the stop becomes a GTT trigger with a limit gtt_slippage_pct (1 %)
below it, so a normal gap still fills; a gap below the limit does not.
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from india import cli, data, indicators, levels, market, money, symbols  # noqa: E402


def make_plan(ctx, ent, entry_price, stop_method, target_spec, max_hold):
    sched = ctx.cfg.get("tick_schedule")
    s = symbols.Sym(ent["symbol"], ent.get("exchange", "NSE"))
    bars = data.drop_unfinished(data.yahoo_daily(ctx.fetcher, s, "1y"), ctx.now)
    idx = len(bars) - 1
    if ent.get("trigger_date"):
        found = [k for k, b in enumerate(bars) if b["d"] == ent["trigger_date"]]
        idx = found[0] if found else idx
    stop, how = levels.compute_stop(bars, idx, entry_price, stop_method, sched)
    target = levels.compute_target(entry_price, stop, target_spec, sched)
    order = ent.get("order") or {}
    entry_date = order.get("valid_for") or market.next_trading_day(ctx.now.date()).isoformat()
    a = indicators.atr(bars[:idx + 1], 14)[idx] if idx >= 13 else None
    risk = round(entry_price - stop, 2)
    return {"symbol": s.code, "exchange": s.exchange, "setup": ent.get("setup", "level"),
            "entry": entry_price, "entry_style": order.get("style", "limit"), "entry_trigger": order.get("trigger"),
            "entry_date": entry_date, "stop": stop, "stop_how": how, "stop_method": stop_method,
            "target_spec": target_spec,
            "gtt_stop_limit": levels.gtt_stop_limit(stop, float(ctx.cfg["gtt_slippage_pct"]), sched),
            "target": target, "risk_per_share": risk, "reward_risk": round((target - entry_price) / risk, 2),
            "max_hold_days": max_hold,
            "time_stop_date": levels.time_stop(datetime.date.fromisoformat(entry_date), max_hold).isoformat(),
            "atr14": None if a is None else round(a, 2), "as_of": bars[idx]["d"],
            "trigger_date": ent.get("trigger_date"), "level": ent.get("level")}


def render(p):
    return "\n".join([
        "%s plan (%s), entry %s on %s" % (symbols.display(symbols.Sym(p["symbol"], p["exchange"])), p["setup"],
                                          money.inr(p["entry"]), p["entry_date"]),
        "  Stop    %s  (%s), %s a share at risk" % (money.inr(p["stop"]), p["stop_how"], money.inr(p["risk_per_share"])),
        "  Target  %s  (reward:risk %.1f)" % (money.inr(p["target"]), p["reward_risk"]),
        "  GTT     stop trigger %s / limit %s, target %s" % (money.inr(p["stop"]),
                                                            money.inr(p["gtt_stop_limit"]), money.inr(p["target"])),
        "  Time stop: out at the close on %s (%d trading days) if neither is hit." % (p["time_stop_date"], p["max_hold_days"]),
        "  A stop is a plan, not a guarantee: a gap below %s leaves the GTT unfilled." % money.inr(p["gtt_stop_limit"]),
        "  Next: /swing-timemachine to replay the odds. Not financial advice."])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="exit.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--entry", type=float, help="entry price (default: the order price in trader/entry.json)")
    p.add_argument("--symbol", help="plan without entry.json (needs --entry)")
    p.add_argument("--stop")
    p.add_argument("--target")
    p.add_argument("--max-hold", type=int)
    p.add_argument("--write", action="store_true")
    cli.common_args(p)
    s = sub.add_parser("show")
    cli.common_args(s)
    a = ap.parse_args(argv)
    ctx = cli.Ctx(a)
    if a.command == "show":
        plan = ctx.read("plan.json")
        if not plan:
            ctx.emit({"error": "no trader/plan.json"}, "exit: no trader/plan.json yet")
            return 2
        ctx.emit(plan, render(plan))
        return 0
    if a.symbol:
        sym = symbols.parse(a.symbol)
        ent = {"symbol": sym.code, "exchange": sym.exchange, "setup": "level"}
    else:
        ent = ctx.read("entry.json")
    if not ent:
        ctx.emit({"error": "no trader/entry.json: run /swing-entry check SYMBOL --write first (or --symbol and --entry)"},
                 "exit: no trader/entry.json: run /swing-entry check SYMBOL --write first")
        return 2
    if ent.get("state") in ("stale", "failed"):
        msg = "entry.json says %s: %s. Plan a fresh setup instead." % (ent["state"], ent.get("reason", ""))
        ctx.emit({"error": msg}, "exit: " + msg)
        return 2
    price = a.entry or (ent.get("order") or {}).get("price")
    if not price:
        ctx.emit({"error": "no entry price: entry.json is waiting; pass --entry PRICE to plan ahead"},
                 "exit: no entry price yet; pass --entry PRICE to plan ahead")
        return 2
    try:
        plan = make_plan(ctx, ent, float(price), a.stop or ctx.cfg["stop_method"], a.target or ctx.cfg["target"],
                         a.max_hold or int(ctx.cfg["max_hold_days"]))
    except (levels.PlanError, data.DataError) as e:
        ctx.emit({"error": str(e)}, "exit: refused: %s" % e)
        return 2
    if a.write:
        ctx.write("plan.json", plan)
    ctx.emit(plan, render(plan) + ("\n  Saved trader/plan.json." if a.write else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
