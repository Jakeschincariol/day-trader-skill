#!/usr/bin/env python3
"""Time Machine for swing-timemachine: replay a swing trade before you risk a rupee. Standard library only.

    python3 timemachine.py run                 # trader/plan.json, 10,000 replays, seed 19
    python3 timemachine.py run --write         # also save trader/timemachine.json
    python3 timemachine.py run --n 20000 --seed 7 --json
    python3 timemachine.py chart               # ASCII fan of the saved run

1. Simulation. 10,000 paths of max_hold_days daily bars. Each path starts at
   the entry and is built from the stock's own last 3 years (756 sessions)
   of daily bars, as ratios to the previous close (open, high, low, close),
   drawn in blocks of 5 consecutive sessions so streaks and gaps survive.
   Seeded (19), so anyone can repeat it.
2. History. Every session in the last 5 years where the same setup fired
   on this stock: buy the next open, the same stop method and target, the
   same time stop, walked through what really happened.

Per day, in order: opened at or below the stop -> out at the open (a gap
through the stop: the GTT may not even fill); opened at or above the target
-> out at the open; low touched the stop -> out at the stop (even if the
high touched the target the same day: counted as the stop, the cautious
reading); high touched the target -> out at the target; after the last day
-> out at that close (the time stop). R = (exit - entry) / (entry - stop).
"""

import argparse
import datetime
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from india import cli, data, indicators, levels, money, symbols  # noqa: E402

LOOKBACK = 756
BLOCK = 5


class TooLittleHistory(ValueError):
    pass


def walk_day(entry, stop, target, o, h, l, c):
    if o <= stop:
        return ("stop", float(o), True)
    if o >= target:
        return ("target", float(o), False)
    if l <= stop:
        return ("stop", float(stop), False)
    if h >= target:
        return ("target", float(target), False)
    return None


def _ratios(bars, lookback):
    rows = []
    window = bars[-(lookback + 1):]
    for prev, b in zip(window, window[1:]):
        pc = prev["c"]
        if pc > 0:
            rows.append((b["o"] / pc, b["h"] / pc, b["l"] / pc, b["c"] / pc))
    return rows


def _bucket(r):
    lo = max(-3.0, min(3.5, (int((r + 10) * 2) / 2.0) - 10))
    return "%+.1f..%+.1f" % (lo, lo + 0.5)


def simulate(bars, entry, stop, target, days, n=10000, seed=19, block=BLOCK, lookback=LOOKBACK):
    need = lookback // 2
    if len(bars) < need:
        raise TooLittleHistory("only %d daily bars; the Time Machine needs at least %d" % (len(bars), need))
    rows = _ratios(bars, lookback)
    rng = random.Random(seed)
    risk = entry - stop
    counts = {"target": 0, "stop": 0, "time": 0}
    gaps, rs, held, hist = 0, [], [], {}
    fan_cols = [[] for _ in range(days)]
    sample = []
    for p in range(n):
        seq = []
        while len(seq) < days:
            k = rng.randrange(0, len(rows) - block + 1)
            seq.extend(rows[k:k + block])
        prev, out, path = entry, None, []
        for d in range(days):
            ro, rh, rl, rc = seq[d]
            o, h, l, c = prev * ro, prev * rh, prev * rl, prev * rc
            if out is None:
                got = walk_day(entry, stop, target, o, h, l, c)
                if got:
                    out = (got[0], got[1], got[2], d + 1)
            path.append(out[1] if out else c)
            prev = c
        if out is None:
            out = ("time", path[-1], False, days)
        counts[out[0]] += 1
        gaps += out[2]
        r = (out[1] - entry) / risk
        rs.append(r)
        held.append(out[3])
        b = _bucket(r)
        hist[b] = hist.get(b, 0) + 1
        for d in range(days):
            fan_cols[d].append(path[d])
        if p < 20:
            sample.append([round(x, 2) for x in path])
    held.sort()

    def pct(col, q):
        s = sorted(col)
        return round(s[min(len(s) - 1, int(q * len(s)))], 2)
    return {"n": n, "seed": seed, "days": days, "block": block, "lookback": len(rows),
            "target_pct": 100.0 * counts["target"] / n, "stop_pct": 100.0 * counts["stop"] / n,
            "time_pct": 100.0 * counts["time"] / n, "gap_through_pct": 100.0 * gaps / n,
            "avg_r": round(sum(rs) / n, 4), "worst_r": round(min(rs), 4), "median_days": held[n // 2],
            "r_hist": dict(sorted(hist.items(), key=lambda kv: float(kv[0].split("..")[0]))),
            "fan": [{"day": d + 1, "p10": pct(col, 0.1), "p50": pct(col, 0.5), "p90": pct(col, 0.9)}
                    for d, col in enumerate(fan_cols)],
            "paths_sample": sample}


def history(bars, setup, stop_method, target_spec, days, years=5, schedule=None):
    rsi = indicators.rsi_wilder([b["c"] for b in bars])
    start = max(0, len(bars) - years * 250)
    trades = []
    for i in range(start, len(bars) - 1 - days):
        if setup not in indicators.setups_at(bars, i, rsi):
            continue
        entry = bars[i + 1]["o"]
        try:
            stop, _ = levels.compute_stop(bars, i, entry, stop_method, schedule)
            target = levels.compute_target(entry, stop, target_spec, schedule)
        except levels.PlanError:
            continue
        out = None
        for d in range(days):
            b = bars[i + 1 + d]
            got = walk_day(entry, stop, target, entry if d == 0 else b["o"], b["h"], b["l"], b["c"])
            if got:
                out = (got[0], got[1], d + 1)
                break
        if out is None:
            out = ("time", bars[i + days]["c"], days)
        trades.append({"date": bars[i]["d"], "entry": entry, "stop": stop, "target": target, "exit": round(out[1], 2),
                       "r": round((out[1] - entry) / (entry - stop), 3), "days": out[2], "outcome": out[0]})
    n = len(trades)
    return {"setup": setup, "years": years, "fired": n,
            "target": sum(t["outcome"] == "target" for t in trades),
            "stop": sum(t["outcome"] == "stop" for t in trades),
            "time": sum(t["outcome"] == "time" for t in trades),
            "avg_r": round(sum(t["r"] for t in trades) / n, 4) if n else None, "trades": trades}


def verdict(sim_r, hist_r):
    rs = [x for x in (sim_r, hist_r) if x is not None]
    if rs and all(x > 0.2 for x in rs):
        return "edge in its own history"
    if rs and all(-0.2 <= x <= 0.2 for x in rs):
        return "close to a coin flip"
    if rs and any(x < -0.2 for x in rs):
        return "history is against it"
    return "mixed: the replay and the record disagree"


def render(r):
    p, s, h = r["plan"], r["sim"], r["history"]
    lines = ["Time Machine: %s, entry %s, stop %s, target %s, %d trading days (to %s)" % (
        symbols.display(symbols.Sym(p["symbol"], p.get("exchange", "NSE"))), money.inr(p["entry"]), money.inr(p["stop"]),
        money.inr(p["target"]), s["days"], p.get("time_stop_date", "?")),
        "  %d replays from the last %d sessions (seed %d, blocks of %d):" % (s["n"], s["lookback"], s["seed"], s["block"]),
        "    target first %.1f %%   stop first %.1f %%   time stop %.1f %%" % (s["target_pct"], s["stop_pct"], s["time_pct"]),
        "    gapped through the stop %.1f %%, worst %.2f R; average %+.2f R; median %d days held" % (
            s["gap_through_pct"], s["worst_r"], s["avg_r"], s["median_days"])]
    if h:
        lines.append("  History, %s on this stock over %d years: fired %d times: %d target, %d stop, %d time stop%s" % (
            h["setup"], h["years"], h["fired"], h["target"], h["stop"], h["time"],
            "" if h["avg_r"] is None else ", average %+.2f R" % h["avg_r"]))
    else:
        lines.append("  History: no setup rule for a hand-picked level, so no record to replay.")
    if r.get("results_inside"):
        lines.append("  Results due %s, inside this hold: these odds do not include a results move." % r["results_inside"])
    lines.append("  Verdict: %s. A simulation from the stock's own past, not a prediction. Not financial advice." % r["verdict"])
    lines.append("  Next: /swing-budget to size it.")
    return "\n".join(lines)


def chart(saved):
    fan = saved["sim"]["fan"]
    p = saved["plan"]
    lo = min(min(x["p10"] for x in fan), p["stop"])
    hi = max(max(x["p90"] for x in fan), p["target"])
    width = 50

    def col(v):
        return int((v - lo) / (hi - lo) * (width - 1)) if hi > lo else 0
    out = ["%-7s %s" % ("", "stop %s ... target %s (10th / median / 90th percentile close)" % (
        money.inr(p["stop"]), money.inr(p["target"])))]
    for x in fan:
        row = [" "] * width
        for k in range(col(x["p10"]), col(x["p90"]) + 1):
            row[k] = "-"
        row[col(x["p50"])] = "o"
        row[col(p["stop"])] = "S"
        row[col(p["target"])] = "T"
        out.append("day %-3d |%s| %s" % (x["day"], "".join(row), money.inr(x["p50"])))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="timemachine.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--n", type=int, default=10000)
    r.add_argument("--seed", type=int, default=19)
    r.add_argument("--write", action="store_true")
    cli.common_args(r)
    c = sub.add_parser("chart")
    cli.common_args(c)
    a = ap.parse_args(argv)
    ctx = cli.Ctx(a)
    if a.command == "chart":
        saved = ctx.read("timemachine.json")
        if not saved:
            print("timemachine: no trader/timemachine.json; run: timemachine.py run --write")
            return 2
        print(chart(saved))
        return 0
    plan = ctx.read("plan.json")
    if not plan:
        ctx.emit({"error": "no trader/plan.json"}, "timemachine: no trader/plan.json; run /swing-exit plan --write first")
        return 2
    s = symbols.Sym(plan["symbol"], plan.get("exchange", "NSE"))
    try:
        bars = data.drop_unfinished(data.yahoo_daily(ctx.fetcher, s, "5y"), ctx.now)
        sim = simulate(bars, plan["entry"], plan["stop"], plan["target"], int(plan["max_hold_days"]), a.n, a.seed)
    except (TooLittleHistory, data.DataError) as e:
        ctx.emit({"error": str(e)}, "timemachine: %s" % e)
        return 2
    hist = None
    if plan.get("setup") in indicators.SETUPS and plan.get("setup") != "oversold":
        hist = history(bars, plan["setup"], plan.get("stop_method", ctx.cfg["stop_method"]),
                       plan.get("target_spec", "%gR" % plan.get("reward_risk", 2)), int(plan["max_hold_days"]),
                       schedule=ctx.cfg.get("tick_schedule"))
    results_inside = None
    if plan.get("entry_date") and plan.get("time_stop_date"):
        got = ctx.nse.results_dates([s.code], datetime.date.fromisoformat(plan["entry_date"]),
                                    datetime.date.fromisoformat(plan["time_stop_date"]))
        results_inside = ((got or {}).get(s.code) or [None])[0]
        ctx.nse_notice()
    doc = {"plan": plan, "sim": sim, "history": hist, "results_inside": results_inside,
           "verdict": verdict(sim["avg_r"], hist["avg_r"] if hist else None), "as_of": bars[-1]["d"]}
    if a.write:
        ctx.write("timemachine.json", doc)
    ctx.emit(doc, render(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
