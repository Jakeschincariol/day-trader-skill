#!/usr/bin/env python3
"""Budget Manager for swing-budget: size the position in rupees. Standard library only.

    python3 size.py                 # trader/plan.json + trader/config.json + trader/positions.json
    python3 size.py --write         # -> trader/orders.json (one proposal: CNC buy + GTT OCO)
    python3 size.py --capital 300000 --risk-pct 0.5

Quantity = the smallest of four limits, in whole shares:
  risk          capital x risk_per_trade_pct (1 %) / (entry - stop)
  position cap  capital x max_position_pct (20 %) / entry
  cash          (cash - capital x cash_buffer_pct (10 %)) / entry, where cash is
                config "cash" or else capital minus the cost of open positions
  and it says which one decided. Refused if that is zero shares, or the cost
  is under min_order (Rs 1,000). Charges are an estimate (india/charges.py).
Nothing is placed: this writes a proposal for swing-risk to check.
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from india import charges, cli, money, symbols  # noqa: E402


class SizeError(ValueError):
    pass


def open_cost(positions):
    return sum(float(p["qty"]) * float(p["entry"]) for p in positions)


def size(plan, cfg, positions):
    entry, stop = float(plan["entry"]), float(plan["stop"])
    risk_ps = round(entry - stop, 2)
    if risk_ps <= 0:
        raise SizeError("the stop is not below the entry")
    capital = float(cfg["capital"])
    risk_rs = capital * float(cfg["risk_per_trade_pct"]) / 100
    cash = float(cfg["cash"]) if cfg.get("cash") is not None else capital - open_cost(positions)
    spendable = cash - capital * float(cfg["cash_buffer_pct"]) / 100
    limits = [("risk", math.floor(round(risk_rs / risk_ps, 6))),
              ("position cap", math.floor(round(capital * float(cfg["max_position_pct"]) / 100 / entry, 6))),
              ("cash", max(0, math.floor(round(spendable / entry, 6))))]
    decided_by, qty = min(limits, key=lambda kv: kv[1])
    if qty < 1:
        if decided_by == "risk":
            raise SizeError("one share risks %s, more than your %s per trade (%s%% of %s). Use a closer stop or skip it." % (
                money.inr(risk_ps), money.inr(risk_rs), cfg["risk_per_trade_pct"], money.inr(capital)))
        raise SizeError("no room: the %s limit allows 0 shares at %s" % (decided_by, money.inr(entry)))
    cost = round(qty * entry, 2)
    if cost < float(cfg["min_order"]):
        raise SizeError("%d share(s) cost %s, under your minimum order %s" % (qty, money.inr(cost), money.inr(cfg["min_order"])))
    ch = charges.delivery_round_trip(cost, qty * stop, cfg.get("charges"))
    risk_at_stop = round(qty * risk_ps, 2)
    return {"qty": qty, "decided_by": decided_by, "limits": dict(limits), "cost": cost,
            "risk_at_stop": risk_at_stop,
            "risk_at_gtt_limit": round(qty * (entry - float(plan["gtt_stop_limit"])), 2),
            "charges": ch, "max_loss_incl_charges": round(risk_at_stop + ch["total"], 2),
            "reward_risk": plan.get("reward_risk"), "risk_budget": round(risk_rs, 2)}


def proposal(plan, s):
    return {"id": "%s-%s" % (plan["symbol"], plan["entry_date"]), "symbol": plan["symbol"],
            "exchange": plan.get("exchange", "NSE"), "product": "CNC", "side": "BUY", "qty": s["qty"],
            "entry_style": plan.get("entry_style", "limit"), "entry_price": plan["entry"],
            "entry_trigger": plan.get("entry_trigger"), "valid_for": plan["entry_date"],
            "gtt": {"type": "OCO", "stop_trigger": plan["stop"], "stop_limit": plan["gtt_stop_limit"],
                    "target_trigger": plan["target"], "target_limit": plan["target"]},
            "cost": s["cost"], "risk_at_stop": s["risk_at_stop"], "risk_at_gtt_limit": s["risk_at_gtt_limit"],
            "charges_est": s["charges"]["total"], "reward_risk": plan.get("reward_risk"),
            "time_stop_date": plan.get("time_stop_date"), "setup": plan.get("setup")}


def render(plan, s):
    name = symbols.display(symbols.Sym(plan["symbol"], plan.get("exchange", "NSE")))
    lim = s["limits"]
    return "\n".join([
        "%s: %d shares at %s = %s (decided by %s)" % (name, s["qty"], money.inr(plan["entry"]), money.inr(s["cost"]),
                                                     s["decided_by"]),
        "  limits: risk %d, position cap %d, cash %d shares" % (lim["risk"], lim["position cap"], lim["cash"]),
        "  loss at the stop %s (budget %s) + charges ~%s = %s" % (
            money.inr(s["risk_at_stop"]), money.inr(s["risk_budget"]), money.inr(s["charges"]["total"]),
            money.inr(s["max_loss_incl_charges"])),
        "  if a gap fills only at the GTT limit %s: %s" % (money.inr(plan["gtt_stop_limit"]), money.inr(s["risk_at_gtt_limit"])),
        "  Sizing keeps a loss small; it does not make a trade win. Not financial advice.",
        "  Next: /swing-risk to check it."])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="size.py", description=__doc__.split("\n")[0])
    ap.add_argument("--capital", type=float)
    ap.add_argument("--risk-pct", type=float)
    ap.add_argument("--write", action="store_true")
    cli.common_args(ap)
    a = ap.parse_args(argv)
    ctx = cli.Ctx(a)
    if a.capital:
        ctx.cfg["capital"] = a.capital
    if a.risk_pct:
        ctx.cfg["risk_per_trade_pct"] = a.risk_pct
    plan = ctx.read("plan.json")
    if not plan:
        ctx.emit({"error": "no trader/plan.json"}, "size: no trader/plan.json; run /swing-exit plan --write first")
        return 2
    positions = (ctx.read("positions.json") or {}).get("positions", [])
    try:
        s = size(plan, ctx.cfg, positions)
    except SizeError as e:
        ctx.emit({"error": str(e)}, "size: refused: %s" % e)
        return 2
    doc = {"as_of": ctx.now.strftime("%Y-%m-%d %H:%M"), "proposals": [proposal(plan, s)], "sizing": s}
    if a.write:
        ctx.write("orders.json", doc)
    ctx.emit(doc, render(plan, s) + ("\n  Saved trader/orders.json." if a.write else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
