#!/usr/bin/env python3
"""Trade card for swing-card: what you type into your own broker, plus your journal.

    python3 card.py show                                   # a card for every proposal that passed today
    python3 card.py record --id TCS-2026-11-19 --qty 29 --price 3412.40
    python3 card.py close --symbol TCS --price 3645 --reason target
    python3 card.py log

This file never talks to a broker or the network: it reads and writes the
JSON files in trader/ only. The user places every order.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from india import charges, cli, config, money, symbols  # noqa: E402

GTT_NOTE = "Place the GTT after the buy fills: most brokers need the shares in your holdings first."


def render(p, verdict):
    name = symbols.display(symbols.Sym(p["symbol"], p.get("exchange", "NSE")))
    if p.get("exchange", "NSE") == "NSE":
        name += " (NSE)"
    if p.get("entry_style") == "sl-buy":
        how = "SL-BUY trigger %s / limit %s" % (money.inr(p["entry_trigger"]), money.inr(p["entry_price"]))
    else:
        how = "LIMIT %s" % money.inr(p["entry_price"])
    g = p["gtt"]
    lines = ["WARNING: " + r for r in verdict.get("reasons", [])] if verdict.get("verdict") == "WARN" else []
    lines += [
        "%s %s · %s · %d shares · %s · valid %s" % (p["side"], name, p["product"], p["qty"], how, p["valid_for"]),
        "GTT %s  stop trigger %s / limit %s" % (g["type"], money.inr(g["stop_trigger"]), money.inr(g["stop_limit"])),
        "         target trigger %s / limit %s" % (money.inr(g["target_trigger"]), money.inr(g["target_limit"])),
        "Risk at stop %s + charges ~%s · R:R %.1f · time stop %s" % (
            money.inr(p["risk_at_stop"]), money.inr(p.get("charges_est", 0), 0), float(p["reward_risk"]),
            p.get("time_stop_date")),
        GTT_NOTE]
    return "\n".join(lines)


def shown(ctx):
    orders = (ctx.read("orders.json") or {}).get("proposals", [])
    state = ctx.read("state/risk.json") or {}
    today = ctx.now.date().isoformat()
    by_id = {v["id"]: v for v in state.get("verdicts", [])} if state.get("date") == today else {}
    out, hidden = [], []
    for p in orders:
        v = by_id.get(p["id"])
        if v and v["verdict"] in ("PASS", "WARN") and v["fingerprint"] == config.fingerprint(p):
            out.append((p, v))
        else:
            hidden.append((p["id"], "BLOCKED" if v and v["verdict"] == "BLOCK" else
                           "changed since the risk check" if v else "not risk-checked today"))
    return out, hidden


def cmd_show(ctx, a):
    cards, hidden = shown(ctx)
    lines = []
    for p, v in cards:
        lines += [render(p, v), ""]
    for pid, why in hidden:
        lines.append("No card for %s: %s. Run /swing-risk again after any change." % (pid, why))
    if cards:
        lines.append("You place this in your own broker app, if you decide yes. Then record the fill: "
                     "card.py record --id ID --qty Q --price P. Not financial advice.")
    ctx.emit({"cards": [dict(p, verdict=v["verdict"], reasons=v["reasons"]) for p, v in cards],
              "hidden": hidden}, "\n".join(lines) if lines else "No proposals: run /swing-budget --write.")
    return 0


def _positions(ctx):
    return (ctx.read("positions.json") or {}).get("positions", [])


def cmd_record(ctx, a):
    orders = {p["id"]: p for p in (ctx.read("orders.json") or {}).get("proposals", [])}
    p = orders.get(a.id)
    if not p:
        ctx.emit({"error": "no proposal %s" % a.id}, "card: no proposal %s in trader/orders.json" % a.id)
        return 2
    pos = _positions(ctx)
    entry = {"id": p["id"], "symbol": p["symbol"], "exchange": p.get("exchange", "NSE"), "qty": int(a.qty),
             "entry": float(a.price), "entry_date": a.date or ctx.now.date().isoformat(),
             "stop": p["gtt"]["stop_trigger"], "gtt_stop_limit": p["gtt"]["stop_limit"],
             "target": p["gtt"]["target_trigger"], "time_stop_date": p.get("time_stop_date"), "setup": p.get("setup")}
    pos.append(entry)
    ctx.write("positions.json", {"positions": pos})
    ctx.emit(entry, "Recorded: bought %d %s at %s on %s. Now place the GTT OCO: stop %s / limit %s, target %s." % (
        entry["qty"], entry["symbol"], money.inr(entry["entry"]), entry["entry_date"], money.inr(entry["stop"]),
        money.inr(entry["gtt_stop_limit"]), money.inr(entry["target"])))
    return 0


def cmd_close(ctx, a):
    pos = _positions(ctx)
    sym = symbols.parse(a.symbol).code
    match = [p for p in pos if p["symbol"] == sym]
    if not match:
        ctx.emit({"error": "no open position in %s" % sym}, "card: no open position in %s" % sym)
        return 2
    p = match[0]
    qty = int(a.qty or p["qty"])
    exit_px = float(a.price)
    ch = charges.delivery_round_trip(qty * p["entry"], qty * exit_px, ctx.cfg.get("charges"))["total"]
    r = round((exit_px - p["entry"]) / (p["entry"] - p["stop"]), 2)
    trade = dict(p, qty=qty, exit=exit_px, exit_date=a.date or ctx.now.date().isoformat(), exit_reason=a.reason,
                 r=r, charges=ch, pnl=round(qty * (exit_px - p["entry"]) - ch, 2))
    journal = ctx.read("journal.json") or {"trades": []}
    journal["trades"].append(trade)
    ctx.write("journal.json", journal)
    rest = qty < p["qty"]
    if rest:
        p["qty"] -= qty
    else:
        pos.remove(p)
    ctx.write("positions.json", {"positions": pos})
    ctx.emit(trade, "Closed %d %s at %s (%s): %+.2f R, P&L %s after ~%s charges.%s" % (
        qty, sym, money.inr(exit_px), a.reason, r, money.inr(trade["pnl"]), money.inr(ch, 0),
        " Cancel or resize the GTT for the shares you sold." if rest else " Cancel the leftover GTT if your broker did not."))
    return 0


def cmd_log(ctx, a):
    trades = (ctx.read("journal.json") or {}).get("trades", [])
    if not trades:
        ctx.emit({"trades": []}, "No closed trades yet.")
        return 0
    wins = sum(t["pnl"] > 0 for t in trades)
    avg_r = sum(t["r"] for t in trades) / len(trades)
    pnl = sum(t["pnl"] for t in trades)
    lines = ["%s %-10s %4d  %s -> %s  %+.2f R  %s  (%s)" % (t["exit_date"], t["symbol"], t["qty"], money.inr(t["entry"]),
                                                          money.inr(t["exit"]), t["r"], money.inr(t["pnl"]), t["exit_reason"])
             for t in trades]
    lines.append("%d trade%s, %d winners (%.0f%%), average %+.2f R, total P&L %s after estimated charges." % (
        len(trades), "" if len(trades) == 1 else "s", wins, 100.0 * wins / len(trades), avg_r, money.inr(pnl)))
    open_pos = _positions(ctx)
    if open_pos:
        lines.append("Open: " + ", ".join("%s %d @ %s" % (p["symbol"], p["qty"], money.inr(p["entry"])) for p in open_pos))
    ctx.emit({"trades": trades, "win_rate": wins / len(trades), "avg_r": avg_r, "pnl": pnl}, "\n".join(lines))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="card.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("show")
    cli.common_args(s)
    r = sub.add_parser("record")
    r.add_argument("--id", required=True)
    r.add_argument("--qty", type=int, required=True)
    r.add_argument("--price", type=float, required=True)
    r.add_argument("--date")
    cli.common_args(r)
    c = sub.add_parser("close")
    c.add_argument("--symbol", required=True)
    c.add_argument("--price", type=float, required=True)
    c.add_argument("--qty", type=int)
    c.add_argument("--date")
    c.add_argument("--reason", choices=["stop", "target", "time", "manual"], default="manual")
    cli.common_args(c)
    lg = sub.add_parser("log")
    cli.common_args(lg)
    a = ap.parse_args(argv)
    ctx = cli.Ctx(a)
    return {"show": cmd_show, "record": cmd_record, "close": cmd_close, "log": cmd_log}[a.command](ctx, a)


if __name__ == "__main__":
    sys.exit(main())
