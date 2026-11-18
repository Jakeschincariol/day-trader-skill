#!/usr/bin/env python3
"""Risk Manager for swing-risk: PASS, WARN or BLOCK every proposal. Standard library only.

    python3 check.py                 # trader/orders.json -> trader/state/risk.json
    python3 check.py --json
    python3 check.py --no-write      # look without recording

BLOCK (final: the card is not shown):
  no GTT stop; not a CNC BUY; not an NSE/BSE equity symbol; a price off the
  NSE tick; loss at the stop over risk_per_trade_pct of capital (5 %
  tolerance); reward:risk under min_reward_risk; open positions already at
  max_open_positions; portfolio heat (open risk to stops + this trade) over
  max_heat_pct of capital; cost over the position cap; buying would dip
  into the cash buffer; on your blocked list; NSE price band in
  block_bands (2 %, 5 %); results due inside the hold when
  block_on_results is true.
WARN (shown, with the reasons above the card):
  price band in warn_bands (10 %); results due inside the hold; quantity
  over 1 % of the 20-day average volume; band or results data unavailable.
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from india import cli, config, data, money, symbols, ticks  # noqa: E402

TOL = 1.05


def heat(positions):
    return sum(float(p["qty"]) * (float(p["entry"]) - float(p["stop"]))
               for p in positions if float(p["stop"]) < float(p["entry"]))


def check(p, cfg, positions, bands, results, avg_volume):
    block, warn = [], []
    capital = float(cfg["capital"])
    sched = cfg.get("tick_schedule")
    g = p.get("gtt") or {}
    if not g.get("stop_trigger"):
        block.append("no GTT stop: every swing trade needs a stop at the broker")
    if p.get("product") != "CNC" or p.get("side") != "BUY":
        block.append("only CNC (delivery) BUY proposals: got %s %s" % (p.get("product"), p.get("side")))
    try:
        sym = symbols.parse("%s:%s" % (p.get("exchange", "NSE"), p.get("symbol", "")))
    except ValueError as e:
        block.append(str(e))
        sym = None
    prices = [("entry", p.get("entry_price")), ("entry trigger", p.get("entry_trigger"))] + [
        ("GTT " + k.replace("_", " "), g.get(k)) for k in ("stop_trigger", "stop_limit", "target_trigger", "target_limit")]
    for name, v in prices:
        if v is not None and not ticks.is_valid(v, sched):
            block.append("%s %s is not on a valid NSE tick" % (name, v))
    budget = capital * float(cfg["risk_per_trade_pct"]) / 100
    if float(p.get("risk_at_stop", 0)) > budget * TOL:
        block.append("loss at the stop %s is over your %s per trade" % (money.inr(p["risk_at_stop"]), money.inr(budget)))
    if p.get("reward_risk") is None or float(p["reward_risk"]) < float(cfg["min_reward_risk"]):
        block.append("reward:risk %s is under your minimum %s" % (p.get("reward_risk"), cfg["min_reward_risk"]))
    if len(positions) >= int(cfg["max_open_positions"]):
        block.append("%d open positions already (max %d)" % (len(positions), cfg["max_open_positions"]))
    total = heat(positions) + float(p.get("risk_at_stop", 0))
    max_heat = capital * float(cfg["max_heat_pct"]) / 100
    if total > max_heat:
        block.append("portfolio heat %s (open risk to stops + this trade) is over %s (%s%% of capital)" % (
            money.inr(total), money.inr(max_heat), cfg["max_heat_pct"]))
    cap = capital * float(cfg["max_position_pct"]) / 100
    if float(p.get("cost", 0)) > cap + 0.01:
        block.append("cost %s is over the position cap %s" % (money.inr(p["cost"]), money.inr(cap)))
    cash = float(cfg["cash"]) if cfg.get("cash") is not None else capital - sum(
        float(x["qty"]) * float(x["entry"]) for x in positions)
    buffer = capital * float(cfg["cash_buffer_pct"]) / 100
    if cash - float(p.get("cost", 0)) < buffer - 0.01:
        block.append("buying leaves %s cash, under your %s buffer" % (money.inr(cash - float(p.get("cost", 0))), money.inr(buffer)))
    if sym and sym.code in [str(x).upper() for x in cfg.get("blocked", [])]:
        block.append("%s is on your blocked list" % sym.code)
    band = bands.get(sym.code) if sym and sym.exchange == "NSE" else None
    if band in cfg.get("block_bands", []):
        block.append("%s%% price band: it can lock at the limit and you may not be able to sell" % band)
    elif band in cfg.get("warn_bands", []):
        warn.append("%s%% price band: a big move can lock it at the limit" % band)
    elif band is None:
        warn.append("price band unknown (check it on NSE before buying)")
    if results is None:
        warn.append("results data unavailable: check the results date yourself, or add it to trader/results.json")
    elif sym:
        inside = [d for d in results.get(sym.code, []) if p.get("valid_for", "") <= d <= p.get("time_stop_date", "")]
        if inside:
            msg = "results due %s, inside the hold (to %s)" % (inside[0], p.get("time_stop_date"))
            (block if cfg.get("block_on_results") else warn).append(msg)
    if avg_volume and float(p.get("qty", 0)) > 0.01 * avg_volume:
        warn.append("%s shares is over 1%% of the 20-day average volume (%d): hard to get out quickly" % (
            p["qty"], avg_volume))
    verdict = "BLOCK" if block else ("WARN" if warn else "PASS")
    return {"id": p.get("id"), "verdict": verdict, "reasons": block + warn, "fingerprint": config.fingerprint(p)}


def gather(ctx, proposals):
    try:
        bands = data.nse_price_bands(ctx.fetcher)
    except data.DataError:
        bands = {}
    syms = sorted({p["symbol"] for p in proposals})
    manual = ctx.read("results.json") or {}
    results = None
    if ctx.nse.available:
        start = ctx.now.date()
        ends = [p.get("time_stop_date") for p in proposals if p.get("time_stop_date")]
        end = max(datetime.date.fromisoformat(max(ends)), start) if ends else start + datetime.timedelta(days=60)
        results = ctx.nse.results_dates(syms, start, end)
    if manual:
        results = dict(results or {})
        for k, v in manual.items():
            results[k] = sorted(set(results.get(k, [])) | set(v))
    vols = {}
    for p in proposals:
        try:
            bars = data.drop_unfinished(data.yahoo_daily(ctx.fetcher, symbols.Sym(p["symbol"], p.get("exchange", "NSE")),
                                                         "1y"), ctx.now)[-20:]
            vols[p["id"]] = sum(b["v"] for b in bars) / len(bars) if bars else None
        except (data.DataError, ValueError):
            vols[p["id"]] = None
    return bands, results, vols


def main(argv=None):
    ap = argparse.ArgumentParser(prog="check.py", description=__doc__.split("\n")[0])
    ap.add_argument("--no-write", action="store_true")
    cli.common_args(ap)
    a = ap.parse_args(argv)
    ctx = cli.Ctx(a)
    orders = ctx.read("orders.json")
    if not orders or not orders.get("proposals"):
        ctx.emit({"error": "no trader/orders.json"}, "risk: no trader/orders.json; run /swing-budget --write first")
        return 2
    positions = (ctx.read("positions.json") or {}).get("positions", [])
    bands, results, vols = gather(ctx, orders["proposals"])
    ctx.nse_notice()
    verdicts = [check(p, ctx.cfg, positions, bands, results, vols.get(p["id"])) for p in orders["proposals"]]
    doc = {"date": ctx.now.date().isoformat(), "verdicts": verdicts}
    if not a.no_write:
        ctx.write("state/risk.json", doc)
    lines = []
    for p, v in zip(orders["proposals"], verdicts):
        lines.append("%-5s %s: BUY %s %s, CNC, %s" % (v["verdict"], p["id"], p["qty"], p["symbol"], money.inr(p.get("cost", 0))))
        lines += ["      - " + r for r in v["reasons"]]
    lines.append("A BLOCK is final for that proposal. These limits keep losses small; they do not make a trade win. "
                 "Not financial advice. Next: /swing-card for anything that passed.")
    ctx.emit(doc, "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
