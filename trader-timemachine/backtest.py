#!/usr/bin/env python3
"""Cross-section backtest for trader-timemachine. Standard library only.

The Time Machine judges one plan on one stock's last 60 days: about 30 trades,
too few to tell an edge from luck. This runs the same opening-range breakout
rule, with the same fills and costs, on hundreds of liquid stocks at once, and
compares every trade with a blind entry at the same bar on the same stock's
other sessions.

    python3 backtest.py fetch                    # the S&P 500 -> 60 days of 5-min bars each, cached
    python3 backtest.py run                      # every rule variant, from the cache
    python3 backtest.py run --json --out trader/backtest.json

How it works:
  1. The universe: the S&P 500's current members (or --symbols FILE). Large,
     liquid stocks; today's list, so a stock that left the index in the last
     60 days is missing (a small survivor bias over 60 days).
  2. Bars: one Yahoo chart request per symbol, range=60d interval=5m, saved to
     --cache as <SYM>.json.gz. Full sessions only (78 bars), today left out.
  3. Each variant (target R, fills, costs): trader-timemachine's history replay
     on every symbol: the first 5-minute close above the 15-minute opening
     range is the signal, stop at the range midpoint, fill at the next bar's
     open, gaps fill at the open, costs off every R, out by --until.
  4. The control: for every trade, the average R of a blind entry at the same
     bar on every other session of the same stock, with the same stop width,
     target R, fills and costs. The difference (trade R minus its control) is
     what the breakout adds.
  5. Ranges: trades on the same day move together (one market), so the 95 %
     ranges come from a bootstrap that resamples whole DAYS, not trades.

Every stock here shares the same 60 days: one market, one stretch of time.
A result from it is a first look, not a verdict for every year.
"""

import argparse
import datetime
import gzip
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import timemachine as tm  # noqa: E402

DEFAULT_CACHE = "trader/cache/60d5m"
SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
PAUSE = 0.4
DRAWS = 2000
VARIANTS = [  # (label, target R, fill, cost bps a side)
    ("1R, next open, 2 bps", 1.0, "next_open", 2.0),
    ("2R, next open, 2 bps", 2.0, "next_open", 2.0),
    ("1R, next open, no costs", 1.0, "next_open", 0.0),
    ("1R, signal close, no costs (old)", 1.0, "close", 0.0),
]


def progress(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- fetch

def universe(path=None):
    """The S&P 500 (datasets/s-and-p-500-companies on GitHub), or a CSV or text file
    you give: the first column of each row is the symbol."""
    if path:
        with open(path, encoding="utf-8") as fh:
            text, src = fh.read(), path
    else:
        text, src = tm._get(SP500_URL), SP500_URL
    syms = []
    for i, line in enumerate(text.splitlines()):
        sym = line.split(",")[0].strip().strip('"').upper()
        if i == 0 and sym in ("SYMBOL", "TICKER"):
            continue
        if sym and sym not in syms:
            syms.append(sym)
    return syms, src


def cmd_fetch(a):
    syms, src = universe(a.symbols)
    progress("Universe: %d symbols from %s." % (len(syms), src))
    os.makedirs(a.cache, exist_ok=True)
    with open(os.path.join(a.cache, "symbols.json"), "w") as fh:
        json.dump({"symbols": syms, "source": src,
                   "fetched_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, fh)
    bad = 0
    for i, s in enumerate(syms):
        path = os.path.join(a.cache, "%s.json.gz" % s)
        if os.path.exists(path) and not a.refresh:
            continue
        try:
            text = tm.fetch_chart(s)
        except tm.TMError as e:
            bad += 1
            progress("  %s: %s" % (s, e))
            continue
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(text)
        if (i + 1) % 50 == 0:
            progress("  charts: %d of %d" % (i + 1, len(syms)))
        time.sleep(PAUSE)
    progress("Charts saved to %s (%d failed)." % (a.cache, bad))
    return 0


# ---------------------------------------------------------------- run

def load_sessions(cache, now_utc):
    with open(os.path.join(cache, "symbols.json")) as fh:
        meta = json.load(fh)
    today = tm.to_eastern(now_utc).date().isoformat()
    out = {}
    for s in meta["symbols"]:
        path = os.path.join(cache, "%s.json.gz" % s)
        if not os.path.exists(path):
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                res = tm.chart_result(fh.read(), s)
            _, bars, _ = tm.parse_bars(res, now_utc)
        except (tm.TMError, OSError, ValueError):
            continue
        sessions, _ = tm.full_sessions(tm.split_sessions(bars), today)
        if len(sessions) >= tm.MIN_SESSIONS:
            out[s] = sessions
    return meta, out


def control_r(sessions, tr, last, rule, fill, cost_bps):
    """Average R of a blind entry at the trade's bar on the stock's other sessions."""
    kk, frac = tr["bar"], tr["risk"] / tr["signal"]
    rs = []
    for d, D in sessions:
        if d == tr["date"]:
            continue
        p = round(D[kk]["c"], 2)
        s = tm.cents_away(p * (1 - frac), True)
        risk = p - s
        if risk <= 0:
            continue
        t = round(p + rule["target_r"] * risk, 2)
        ct = tm.one_trade(D, kk, p, s, t, last, True, fill, cost_bps)
        if not isinstance(ct, str):
            rs.append(ct["R"])
    return sum(rs) / len(rs) if rs else None


def day_bootstrap(rows, key, rng, draws):
    """95 % range of the mean of row[key], resampling whole days."""
    by_day = {}
    for r in rows:
        by_day.setdefault(r["date"], []).append(r[key])
    days = sorted(by_day)
    sums = [(sum(by_day[d]), len(by_day[d])) for d in days]
    means = []
    for _ in range(draws):
        tot = n = 0
        for _ in days:
            s, c = sums[rng.randrange(len(days))]
            tot += s
            n += c
        means.append(tot / n)
    means.sort()
    return tm.pct(means, 0.025), tm.pct(means, 0.975)


def run_variant(data, target_r, fill, cost_bps, last, seed, draws):
    rule = {"setup": "orb", "or_minutes": 15, "stop_rule": "or_mid", "target_r": target_r}
    rows = []
    skipped = {"no_bar": 0, "rejected": 0}
    for sym, sessions in data.items():
        h = tm.history_replay(sessions, rule, last, "buy", fill, cost_bps)
        for k in skipped:
            skipped[k] += h["skipped"][k]
        for tr in h["trades"]:
            c = control_r(sessions, tr, last, rule, fill, cost_bps)
            if c is None:
                continue
            rows.append({"symbol": sym, "date": tr["date"], "R": tr["R"], "control": c, "diff": tr["R"] - c,
                         "outcome": tr["outcome"]})
    n = len(rows)
    if not n:
        return {"trades": 0}
    rng = random.Random(seed)
    mean = lambda k: sum(r[k] for r in rows) / n  # noqa: E731
    out = {"trades": n, "symbols": len({r["symbol"] for r in rows}), "days": len({r["date"] for r in rows}),
           "skipped": skipped,
           "target": sum(r["outcome"] == "target" for r in rows) / n,
           "stop": sum(r["outcome"] == "stop" for r in rows) / n,
           "neither": sum(r["outcome"] == "close" for r in rows) / n,
           "avg_R": mean("R"), "control_R": mean("control"), "edge_R": mean("diff")}
    out["R_ci"] = day_bootstrap(rows, "R", rng, draws)
    out["edge_ci"] = day_bootstrap(rows, "diff", rng, draws)
    dates = sorted({r["date"] for r in rows})
    half = dates[len(dates) // 2]
    for name, part in (("first_half", [r for r in rows if r["date"] < half]),
                       ("second_half", [r for r in rows if r["date"] >= half])):
        if part:
            out[name] = {"trades": len(part), "avg_R": sum(r["R"] for r in part) / len(part),
                         "edge_R": sum(r["diff"] for r in part) / len(part),
                         "from": min(r["date"] for r in part),
                         "to": max(r["date"] for r in part)}
    return out


def fmt(v):
    lo, hi = v
    return "%+.3f to %+.3f" % (lo, hi)


def cmd_run(a):
    now = tm.parse_now(a.now)
    meta, data = load_sessions(a.cache, now)
    if not data:
        raise tm.TMError("no usable charts in %s: run backtest.py fetch first" % a.cache)
    until = tm.parse_clock(a.until, "--until")
    last = (until - tm.OPEN_MIN) // 5 - 1
    days = sorted({d for ss in data.values() for d, _ in ss})
    progress("%d stocks with %d+ full sessions, %s to %s; out by %s." % (
        len(data), tm.MIN_SESSIONS, days[0], days[-1], tm.clock12(until)))
    results = []
    for label, r, fill, cost in VARIANTS:
        t0 = time.time()
        res = run_variant(data, r, fill, cost, last, a.seed, a.draws)
        res["label"] = label
        results.append(res)
        progress("  %s: %d trades (%.0f s)" % (label, res["trades"], time.time() - t0))
    doc = {"created_by": "trader-timemachine/backtest.py", "stocks": len(data), "from": days[0], "to": days[-1],
           "until": tm.clock24(until), "seed": a.seed, "draws": a.draws, "source": meta.get("source"),
           "fetched_at": meta.get("fetched_at"), "variants": results}
    if a.out:
        tm._write(a.out, doc)
    if a.json:
        print(json.dumps(doc, indent=2))
        return 0
    print("Opening-range breakout (15-min range, stop at the midpoint, long only) on %d S&P 500 stocks, "
          "%s to %s, out by %s. Ranges: 95 %%, resampling whole days (%d draws, seed %d)."
          % (len(data), days[0], days[-1], tm.clock12(until), a.draws, a.seed))
    for v in results:
        if not v["trades"]:
            print("\n%s: no trades." % v["label"])
            continue
        print("\n%s: %s trades on %d stocks and %d days (left out: %d rejected brackets, %d with no bar)."
              % (v["label"], "{:,}".format(v["trades"]), v["symbols"], v["days"], v["skipped"]["rejected"],
                 v["skipped"]["no_bar"]))
        print("  target first %.1f %%, stop first %.1f %%, neither %.1f %%"
              % (100 * v["target"], 100 * v["stop"], 100 * v["neither"]))
        print("  average R        %+.3f   (%s)" % (v["avg_R"], fmt(v["R_ci"])))
        print("  blind entry R    %+.3f" % v["control_R"])
        print("  breakout adds    %+.3f R a trade   (%s)" % (v["edge_R"], fmt(v["edge_ci"])))
        for name in ("first_half", "second_half"):
            h = v.get(name)
            if h:
                print("  %s to %s: %s trades, average R %+.3f, breakout adds %+.3f"
                      % (h["from"], h["to"], "{:,}".format(h["trades"]), h["avg_R"], h["edge_R"]))
    print("\nEvery stock shares the same %d days: one market, one stretch of time. A first look, not a verdict."
          % len(days))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cross-section backtest of the opening-range breakout.")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("fetch")
    p.add_argument("--symbols", help="a CSV or text file of symbols (first column) instead of the S&P 500")
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--refresh", action="store_true")
    p = sub.add_parser("run")
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--until", default="15:55")
    p.add_argument("--seed", type=int, default=19)
    p.add_argument("--draws", type=int, default=DRAWS)
    p.add_argument("--now", help='pin the clock ("2026-11-03 16:30" New York)')
    p.add_argument("--json", action="store_true")
    p.add_argument("--out")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"fetch": cmd_fetch, "run": cmd_run}[a.cmd](a)
    except tm.TMError as e:
        print("backtest.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
