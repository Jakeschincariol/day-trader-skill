#!/usr/bin/env python3
"""Multi-ticker backtest for trader-timemachine. Standard library only.

The Time Machine's history replay runs one rule on one stock: about 30 trades
in 60 days, far too few to tell a real edge from luck. This runs the same
opening-range breakout (long only) on every ticker you give it, keeps what
each trade looked like when it fired (relative volume, gap, range width,
VWAP, the market), and tests filters the honest way:

  1. Split the days in time order: the first half is IN SAMPLE (where you
     look for ideas), the second half OUT OF SAMPLE (where you check them).
  2. Score the baseline (no filter), each filter alone, and all of them
     together, in both halves: trades, win rate with its 95 % range, average
     R with its 95 % range, all after slippage.
  3. A filter "held up" only when it beat the baseline's average R in BOTH
     halves with at least 30 trades in each AND its average R is above zero
     after costs in both. Beating a losing baseline while still losing is
     called "less bad, but still loses". Better in sample only is called
     what it usually is: noise. The baseline itself is called positive,
     losing or mixed after costs.

    python3 backtest.py run --symbols TSLA,NVDA,AMD,AAPL,META
    python3 backtest.py run --watchlist trader/watchlist.json --slippage 5bps
    python3 backtest.py run --symbols TSLA,NVDA --filter "rvol>=2" --filter vwap --filter market
    python3 backtest.py run --symbols TSLA,NVDA --filter "time<=10:30" --by time --by rvol
    python3 backtest.py run --symbols TSLA --stop-rule or_low --target-r 2 --until 15:55 --write

The rule, per ticker and per full session (78 five-minute bars) in the data:
the opening range is the first --or-minutes; the entry is the first bar after
it, no later than --last-entry, to CLOSE above the range high, at that close.
The stop is the range midpoint (or_mid), the range low (or_low) or --stop-pct
below the entry, rounded down to the cent; the target is --target-r times the
risk. Bar by bar: the stop first (a bar that opens below the stop fills at its
open: a gap), then the target, else out at the --until bar's close.
--slippage (0.03, 5bps or auto, see timemachine.py) makes every R net of costs.

What each trade records, for --filter and --by:
  rvol     volume from the open through the entry bar / the same for the
           previous up to 20 sessions (needs 5)
  gap      today's open vs the previous session's close, in %
  or_pct   the opening range's width, % of its low
  price    the entry price
  time     the entry bar's close, New York time (time<=10:30)
  vwap     the entry closed above the session's VWAP so far (yes/no)
  market   the market (--market, SPY) was above its own VWAP at that bar (yes/no)
A trade whose value is unknown (too little history, no market data) is left
out when that filter is on, and the report says how many.

Filters: rvol>=2, gap>=0.5, gap<=3, or_pct<=2, price>=10, time<=10:30, vwap,
market. --by buckets the all-filters set by time, rvol, gap, or_pct, symbol,
weekday, vwap or market.

Data: Yahoo v8 chart, 60 days of 5-minute bars per ticker (one request each,
half a second apart), or --offline DIR holding <SYM>-60d5m.json(.gz). Same
data, same result: there is no randomness here. Past results are not a
prediction, and 60 days is one market mood.
"""

import argparse
import datetime
import json
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timemachine as tm  # noqa: E402

MIN_PRIOR = 5          # rvol needs this many earlier sessions
RVOL_LOOKBACK = 20
FEW = 30               # trades per half before a verdict means anything
MAX_SYMBOLS = 40
FILTER_RE = re.compile(r"^(rvol|gap|or_pct|price|time)(>=|<=|>|<)(-?[0-9.:]+)$")
BOOL_FILTERS = ("vwap", "market")
BY = ("time", "rvol", "gap", "or_pct", "symbol", "weekday", "vwap", "market")
BUCKETS = {
    "rvol": [(None, 1, "<1"), (1, 2, "1-2"), (2, 3, "2-3"), (3, None, "3+")],
    "gap": [(None, -2, "< -2 %"), (-2, 0, "-2 to 0 %"), (0, 2, "0 to 2 %"), (2, None, "2 % +")],
    "or_pct": [(None, 1, "< 1 %"), (1, 2, "1-2 %"), (2, 4, "2-4 %"), (4, None, "4 % +")],
}


class BTError(Exception):
    pass


# ---------------------------------------------------------------- filters

def parse_filter(text):
    t = re.sub(r"\s+", "", str(text or "")).lower()
    if t in BOOL_FILTERS:
        return {"name": t, "op": "is", "value": True, "text": t}
    m = FILTER_RE.match(t)
    if not m:
        raise BTError("--filter %r: use rvol>=2, gap>=0.5, or_pct<=2, price>=10, time<=10:30, vwap or market"
                      % text)
    name, op, v = m.groups()
    if name == "time":
        try:
            value = tm.parse_clock(v, "the time filter")
        except tm.TMError as e:
            raise BTError(str(e))
    else:
        try:
            value = float(v)
        except ValueError:
            raise BTError("--filter %r wants a number" % text)
    return {"name": name, "op": op, "value": value, "text": "%s%s%s" % (name, op, v)}


def passes(trade, f):
    """True, False, or None when the trade's value is unknown."""
    x = trade["features"].get(f["name"])
    if x is None:
        return None
    if f["op"] == "is":
        return bool(x) is f["value"]
    v = f["value"]
    return {">=": x >= v, "<=": x <= v, ">": x > v, "<": x < v}[f["op"]]


def apply_filters(trades, filters):
    """(kept, unknown): trades that pass every filter, and how many were left out as unknown."""
    kept, unknown = [], 0
    for t in trades:
        res = [passes(t, f) for f in filters]
        if any(r is None for r in res):
            unknown += 1
        elif all(res):
            kept.append(t)
    return kept, unknown


# ---------------------------------------------------------------- features

def vwap_at(D, k):
    pv = sum((b["h"] + b["l"] + b["c"]) / 3.0 * (b["v"] or 0) for b in D[:k + 1])
    v = sum((b["v"] or 0) for b in D[:k + 1])
    return pv / v if v > 0 else None


def market_above_vwap(mdays, d, k):
    s = (mdays or {}).get(d)
    if not s or not all(i in s for i in range(k + 1)):
        return None
    D = [s[i] for i in range(k + 1)]
    vw = vwap_at(D, k)
    return None if vw is None else D[k]["c"] > vw


# ---------------------------------------------------------------- the rule on one ticker

def symbol_trades(sym, days, rule, until_min, last_entry_min, slip_frac=None, mdays=None):
    """Every trade the rule takes on one ticker's full sessions, oldest first."""
    dates = sorted(days)
    n = rule["or_minutes"] // 5
    last = (until_min - tm.OPEN_MIN) // 5 - 1
    last_k = min(last, (last_entry_min - tm.OPEN_MIN) // 5 - 1)
    cum_hist, trades = [], []
    for idx, d in enumerate(dates):
        s = days[d]
        if len(s) != tm.SESSION_BARS:
            continue
        D = [s[i] for i in range(tm.SESSION_BARS)]
        cum, run = [], 0.0
        for b in D:
            run += b["v"] or 0
            cum.append(run)
        oh, ol = tm.opening_range(D, n)
        kk = next((i for i in range(n, last_k + 1) if D[i]["c"] > oh), None)
        if kk is not None:
            e = round(D[kk]["c"], 2)
            st = tm.rule_stop(rule, oh, ol, e, True)
            risk = e - st
            if risk > 0:
                t = round(e + rule["target_r"] * risk, 2)
                oc, fill = None, st
                for b in D[kk + 1:last + 1]:
                    if b["l"] <= st:
                        oc, fill = "stop", min(st, b["o"])
                        break
                    if b["h"] >= t:
                        oc = "target"
                        break
                cl = D[last]["c"]
                oc = oc or "close"
                gross = tm.net_exit_r(True, oc, e, t, fill, cl, risk, 0.0)
                net = tm.net_exit_r(True, oc, e, t, fill, cl, risk, slip_frac * e) if slip_frac else gross
                prior = cum_hist[-RVOL_LOOKBACK:]
                rvol = None
                if len(prior) >= MIN_PRIOR:
                    avg = statistics.mean(p[kk] for p in prior)
                    rvol = round(cum[kk] / avg, 2) if avg > 0 else None
                gap = None
                if idx > 0:
                    prev = days[dates[idx - 1]]
                    pc = prev[max(prev)]["c"]
                    gap = round(100.0 * (D[0]["o"] / pc - 1), 2) if pc else None
                vw = vwap_at(D, kk)
                tmin = tm.OPEN_MIN + 5 * (kk + 1)
                trades.append({
                    "symbol": sym, "date": d, "time": tm.clock24(tmin), "entry": e, "stop": st, "target": t,
                    "outcome": oc, "R": round(net, 3), "R_gross": round(gross, 3),
                    "gapped": oc == "stop" and fill < st,
                    "features": {"rvol": rvol, "gap": gap, "or_pct": round(100.0 * (oh - ol) / ol, 2),
                                 "price": e, "time": tmin,
                                 "vwap": (e > vw) if vw is not None else None,
                                 "market": market_above_vwap(mdays, d, kk)},
                })
        cum_hist.append(cum)
    return trades


# ---------------------------------------------------------------- stats

def wilson(k, n, z=1.96):
    if not n:
        return None
    p = float(k) / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4.0 * n * n)) / den
    return [round(max(0.0, mid - half), 4), round(min(1.0, mid + half), 4)]


def summarize(trades):
    n = len(trades)
    if not n:
        return {"n": 0}
    Rs = [t["R"] for t in trades]
    wins = sum(1 for r in Rs if r > 0)
    avg = statistics.mean(Rs)
    half = 1.96 * statistics.stdev(Rs) / math.sqrt(n) if n > 1 else None
    return {"n": n, "wins": wins, "win_rate": round(float(wins) / n, 4), "win_range": wilson(wins, n),
            "avg_R": round(avg, 3), "avg_R_range": [round(avg - half, 3), round(avg + half, 3)] if half else None,
            "avg_R_gross": round(statistics.mean(t["R_gross"] for t in trades), 3),
            "total_R": round(sum(Rs), 2),
            "target": sum(1 for t in trades if t["outcome"] == "target"),
            "stop": sum(1 for t in trades if t["outcome"] == "stop"),
            "close": sum(1 for t in trades if t["outcome"] == "close"),
            "symbols": len({t["symbol"] for t in trades})}


def sign_words(v):
    """Does a variant make money after costs? Looks at both halves."""
    vi, vo = v["in"], v["out"]
    if not vi.get("n") or not vo.get("n"):
        return "no trades in one half"
    if vi["avg_R"] > 0 and vo["avg_R"] > 0:
        sure = vo.get("avg_R_range") and vo["avg_R_range"][0] > 0
        return "positive after costs in both halves" + (
            " (out of sample, the 95 % range is above zero)" if sure else
            " (but out of sample the 95 % range still reaches below zero)")
    if vi["avg_R"] <= 0 and vo["avg_R"] <= 0:
        return "loses after costs in both halves"
    return "mixed: one half above zero, one below"


def judge(base, var):
    """A filter held up only when it beat the baseline's average R in both halves, with
    enough trades, AND made money after costs in both. Beating a losing baseline while
    still losing is called that: less bad, still losing."""
    bi, bo, vi, vo = base["in"], base["out"], var["in"], var["out"]
    if vi["n"] < FEW or vo["n"] < FEW:
        return "too few trades to tell (needs %d in each half)" % FEW
    better_in = vi["avg_R"] > bi.get("avg_R", -99)
    better_out = vo["avg_R"] > bo.get("avg_R", -99)
    positive = vi["avg_R"] > 0 and vo["avg_R"] > 0
    if better_in and better_out:
        if positive:
            return "held up: better than the baseline and " + sign_words(var)
        return "less bad than the baseline in both halves, but still loses after costs"
    if better_in:
        return "better in sample only: likely noise"
    if better_out:
        return "better out of sample only: not proven"
    return "did not help"


def bucket_of(t, by):
    f = t["features"]
    if by == "symbol":
        return t["symbol"]
    if by == "weekday":
        return ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[datetime.date.fromisoformat(t["date"]).weekday()]
    if by == "time":
        m = f["time"]
        start = m - (m - tm.OPEN_MIN) % 30
        return "%s-%s" % (tm.clock24(start), tm.clock24(start + 30))
    if by in ("vwap", "market"):
        return "unknown" if f[by] is None else ("above" if f[by] else "below")
    x = f[by]
    if x is None:
        return "unknown"
    for lo, hi, label in BUCKETS[by]:
        if (lo is None or x >= lo) and (hi is None or x < hi):
            return label
    return "?"


# ---------------------------------------------------------------- the run

def load_days(sym, offline, now_utc):
    text = tm.read_offline(offline, sym) if offline else tm.fetch_chart(sym)
    result = tm.chart_result(text, sym)
    meta, bars, _ = tm.parse_bars(result, now_utc)
    msym = str(meta.get("symbol") or "").upper()
    if msym and msym != sym.replace(".", "-"):
        raise tm.TMError("the data is for %s, not %s" % (msym, sym))
    if meta.get("dataGranularity") and meta["dataGranularity"] != "5m":
        raise tm.TMError("the data has %s bars, not 5-minute bars" % meta["dataGranularity"])
    return tm.split_sessions(bars)


def symbols_from(a):
    syms = []
    if a.symbols:
        syms += [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    if a.watchlist:
        if not os.path.exists(a.watchlist):
            raise BTError("no watchlist at %s: run /trader-scanner, or pass --symbols" % a.watchlist)
        try:
            with open(a.watchlist, encoding="utf-8") as fh:
                wl = json.load(fh)
        except ValueError as e:
            raise BTError("%s is not valid JSON: %s" % (a.watchlist, e))
        rows = wl.get("hits", wl.get("symbols", [])) if isinstance(wl, dict) else wl
        for r in rows:
            s = r.get("symbol") if isinstance(r, dict) else r
            if s:
                syms.append(str(s).strip().upper())
    out = []
    for s in syms:
        if not re.match(r"^[A-Z][A-Z0-9.\-]{0,9}$", s):
            raise BTError("%r is not a ticker" % s)
        if s not in out:
            out.append(s)
    if not out:
        raise BTError("give tickers: --symbols TSLA,NVDA,AMD or --watchlist trader/watchlist.json")
    if len(out) > a.max:
        out = out[:a.max]
    return out


def backtest(symbols, load, rule, until_min, last_entry_min, filters, split=0.5, slippage=None,
             market=None, bys=()):
    """load(sym) -> days. Returns the result document (no network of its own)."""
    if not 0.2 <= split <= 0.8:
        raise BTError("--split must be between 0.2 and 0.8")
    if (until_min - tm.OPEN_MIN) % 5 or not tm.OPEN_MIN < until_min <= tm.CLOSE_MIN:
        raise BTError("--until must be a 5-minute time between 9:35 and 16:00")
    if last_entry_min >= until_min:
        raise BTError("--last-entry must be before --until")
    mdays, market_error = None, None
    if market and (any(f["name"] == "market" for f in filters) or "market" in bys):
        try:
            mdays = load(market)
        except tm.TMError as e:
            market_error = str(e)
    all_trades, failed, sessions = [], {}, set()
    for i, sym in enumerate(symbols):
        try:
            days = load(sym)
        except tm.TMError as e:
            failed[sym] = str(e)
            continue
        sessions |= {d for d, s in days.items() if len(s) == tm.SESSION_BARS}
        frac = (slippage["bps"] / 10000.0) if slippage else None
        all_trades += symbol_trades(sym, days, rule, until_min, last_entry_min, frac, mdays)
    if not sessions:
        raise BTError("no usable data for any ticker: " + "; ".join("%s: %s" % kv for kv in failed.items()))
    dates = sorted(sessions)
    cut = max(1, min(len(dates) - 1, int(len(dates) * split)))
    split_date = dates[cut]
    halves = lambda ts: {"in": summarize([t for t in ts if t["date"] < split_date]),  # noqa: E731
                         "out": summarize([t for t in ts if t["date"] >= split_date]),
                         "all": summarize(ts)}
    variants = [{"name": "baseline", "filters": [], "unknown": 0, **halves(all_trades)}]
    variants[0]["verdict"] = sign_words(variants[0])
    sets = [[f] for f in filters] + ([filters] if len(filters) > 1 else [])
    for fs in sets:
        kept, unknown = apply_filters(all_trades, fs)
        name = "all filters" if (len(filters) > 1 and fs is filters) else fs[0]["text"]
        v = {"name": name, "filters": [f["text"] for f in fs], "unknown": unknown}
        v.update(halves(kept))
        v["verdict"] = judge(variants[0], v)
        variants.append(v)
    final, _ = apply_filters(all_trades, filters)
    breakdown = {}
    for by in bys:
        groups = {}
        for t in final:
            groups.setdefault(bucket_of(t, by), []).append(t)
        breakdown[by] = {k: summarize(v) for k, v in sorted(groups.items())}
    return {
        "created_by": "trader-timemachine backtest",
        "rule": rule, "until": tm.clock24(until_min), "last_entry": tm.clock24(last_entry_min),
        "symbols": symbols, "failed": failed, "market": market, "market_error": market_error,
        "slippage": slippage, "sessions": len(dates), "first": dates[0], "last": dates[-1],
        "split": split, "split_date": split_date,
        "in_sample": [dates[0], dates[cut - 1]], "out_of_sample": [split_date, dates[-1]],
        "variants": variants, "by": breakdown,
        "trades": [dict(t, features=dict(t["features"], time=tm.clock24(t["features"]["time"])))
                   for t in all_trades],
    }


# ---------------------------------------------------------------- output

def pc(x):
    return "%.0f %%" % (100 * x)


def cell(s):
    if not s.get("n"):
        return "%-44s" % "  0 trades"
    rng = ("[%+.2f, %+.2f]" % tuple(s["avg_R_range"])) if s.get("avg_R_range") else ""
    return "%4d  won %4s  avg R %+.3f %-16s" % (s["n"], pc(s["win_rate"]), s["avg_R"], rng)


def report(doc):
    ru = doc["rule"]
    stop = {"or_mid": "the opening-range midpoint", "or_low": "the opening-range low"}.get(
        ru["stop_rule"], "%g %% below the entry" % ru.get("stop_pct", 0))
    sl = doc["slippage"]
    ok = [s for s in doc["symbols"] if s not in doc["failed"]]
    lines = [
        "Opening-range breakout, long: %d-min range, entry by %s, stop at %s, %gR target, out by %s."
        % (ru["or_minutes"], doc["last_entry"], stop, ru["target_r"], doc["until"]),
        "%d ticker%s, %d sessions (%s to %s). %s." % (
            len(ok), "" if len(ok) == 1 else "s", doc["sessions"], doc["first"], doc["last"],
            ("Slippage %.1f bps each side, from %s" % (sl["bps"], sl["source"])) if sl
            else "No slippage counted: perfect fills (add --slippage auto)"),
        "In sample %s to %s, out of sample %s to %s." % (doc["in_sample"][0], doc["in_sample"][1],
                                                         doc["out_of_sample"][0], doc["out_of_sample"][1]),
        "",
        "%-24s %-44s %-44s" % ("", "IN SAMPLE", "OUT OF SAMPLE"),
    ]
    for v in doc["variants"]:
        lines.append("%-24s %s %s" % (v["name"][:24], cell(v["in"]), cell(v["out"])))
        notes = []
        if v.get("verdict"):
            notes.append(v["verdict"])
        if v.get("unknown"):
            notes.append("%d trade(s) left out: value unknown" % v["unknown"])
        if notes:
            lines.append("%-24s %s" % ("", "; ".join(notes)))
    b = doc["variants"][0]["all"]
    if b.get("n"):
        lines += ["", "Baseline, all days: %d trades, won %s (95 %% range %s to %s), average R %+.3f "
                  "(%+.3f before costs), %d target, %d stop, %d out at %s." % (
                      b["n"], pc(b["win_rate"]), pc(b["win_range"][0]), pc(b["win_range"][1]), b["avg_R"],
                      b["avg_R_gross"], b["target"], b["stop"], b["close"], doc["until"])]
    for by, groups in doc["by"].items():
        lines += ["", "By %s (%s):" % (by, "all filters" if len(doc["variants"]) > 1 else "baseline")]
        for k, s in groups.items():
            lines.append("  %-14s %s%s" % (k, cell(s), "  (few)" if s["n"] < 10 else ""))
    if len(doc["variants"]) > 3:
        lines += ["", "You tried %d filter sets. Some will look good by chance alone; trust only the ones "
                  "that held up out of sample." % (len(doc["variants"]) - 1)]
    if doc["failed"]:
        lines.append("Skipped: " + "; ".join("%s (%s)" % kv for kv in doc["failed"].items()))
    if doc.get("market_error"):
        lines.append("No market data (%s): %s. The market filter could not be checked." % (doc["market"],
                                                                                        doc["market_error"]))
    lines.append("Past results over %d sessions are not a prediction. Education and tooling, not financial "
                 "advice." % doc["sessions"])
    return lines


# ---------------------------------------------------------------- commands

def cmd_run(a):
    now = tm.parse_now(a.now)
    symbols = symbols_from(a)
    rule = {"setup": "orb", "or_minutes": a.or_minutes, "stop_rule": a.stop_rule, "target_r": a.target_r}
    if a.or_minutes < 5 or a.or_minutes % 5 or a.or_minutes >= 120:
        raise BTError("--or-minutes must be a multiple of 5 under 120")
    if a.target_r <= 0:
        raise BTError("--target-r must be above 0")
    if a.stop_rule == "pct":
        if not a.stop_pct or a.stop_pct <= 0:
            raise BTError("--stop-rule pct needs --stop-pct, like --stop-pct 1.5")
        rule["stop_pct"] = a.stop_pct
    filters = [parse_filter(f) for f in a.filter]
    slip = tm.resolve_slippage(a.slippage, 100.0, a.broker_state) if a.slippage else None
    if slip:
        if slip["mode"] == "dollars":
            raise BTError("across tickers at different prices, give --slippage in basis points (5bps) or auto")
        slip.pop("per_share", None)   # applied as bps of each trade's own entry
    fetched = {"n": 0}

    def load(sym):
        if not a.offline:
            if fetched["n"]:
                tm._sleep(tm.PAUSE)
            fetched["n"] += 1
        return load_days(sym, a.offline, now)
    market = None if str(a.market).lower() == "none" else a.market.upper()
    doc = backtest(symbols, load, rule, tm.parse_clock(a.until, "--until"),
                   tm.parse_clock(a.last_entry, "--last-entry"), filters, a.split, slip, market, a.by)
    if a.write:
        d = os.path.dirname(a.write)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(a.write, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
            fh.write("\n")
    if a.json:
        print(json.dumps(dict(doc, trades=len(doc["trades"])), indent=2))
    else:
        print("\n".join(report(doc)))
        if a.write:
            print("Wrote %s (every trade, with its values)." % a.write)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Multi-ticker opening-range breakout backtest (trader-timemachine).")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run", help="backtest the rule on many tickers, in sample and out of sample")
    p.add_argument("--symbols", help="comma list, e.g. TSLA,NVDA,AMD")
    p.add_argument("--watchlist", help="trader-scanner's trader/watchlist.json")
    p.add_argument("--max", type=int, default=MAX_SYMBOLS, help="at most this many tickers (default 40)")
    p.add_argument("--or-minutes", type=int, default=15)
    p.add_argument("--stop-rule", default="or_mid", choices=["or_mid", "or_low", "pct"])
    p.add_argument("--stop-pct", type=float)
    p.add_argument("--target-r", type=float, default=1.0)
    p.add_argument("--last-entry", default="15:30", help="no entries after this bar close (default 15:30)")
    p.add_argument("--until", default="15:55", help="out at this bar's close (default 15:55, flat by)")
    p.add_argument("--filter", action="append", default=[], help='e.g. "rvol>=2", vwap, market, "time<=10:30"')
    p.add_argument("--by", action="append", default=[], choices=BY)
    p.add_argument("--split", type=float, default=0.5, help="share of the days in sample (default 0.5)")
    p.add_argument("--slippage", metavar="auto|0.03|5bps")
    p.add_argument("--broker-state", default="trader/state/broker.json")
    p.add_argument("--market", default="SPY", help="the market for the market filter (none to skip)")
    p.add_argument("--offline", metavar="DIR", help="folder of <SYM>-60d5m.json(.gz), no network")
    p.add_argument("--now", help='pretend it is this time ("2026-10-19 16:30" New York)')
    p.add_argument("--json", action="store_true")
    p.add_argument("--write", nargs="?", const="trader/backtest.json", metavar="PATH")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return cmd_run(a)
    except (BTError, tm.TMError) as e:
        print("backtest.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
