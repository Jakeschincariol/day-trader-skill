#!/usr/bin/env python3
"""Trade journal for trader-broker. Standard library only.

Turns the fills in trader/state/broker.json into round-trip trades and scores
each one in R (the result divided by the risk you planned a share), so you can
see what actually works for you, not what feels like it works:

  show   every closed trade (entry, exit, how it ended, R, dollars, slippage),
         then the totals: win rate with its 95 % range, average R with its
         95 % range, total R, and the fill costs. --by groups them by setup,
         symbol, hour, weekday, exit or tag.
  note   tags a day's trade in a symbol ("news", "choppy", "chased", ...) and
         keeps a line of text with it, in trader/state/journal.json.

    python3 journal.py show
    python3 journal.py show --by hour --by exit
    python3 journal.py show --from 2026-10-01 --csv trader/journal.csv
    python3 journal.py note --symbol TSLA --date 2026-10-19 --tag news --text "earnings next week"

How trades are built: fills are matched first in, first out, per symbol. Each
buy is one trade; it closes when sells have covered all of its shares (the exit
price is the share-weighted average of those sells). Long only, like the rest
of the pack. R = (exit - entry) / the planned risk a share, from the entry
fill's plan (entry - stop), else from the placed order's max loss / qty. A
trade with no known risk is still listed, in dollars, without an R.

Fill prices already include slippage, so the R here is what you really got.
A small sample says little: with 20 trades a 50 % win rate could really be
anywhere from about 30 % to 70 %. The 95 % ranges say how much to trust it.
"""

import argparse
import csv
import datetime
import json
import math
import os
import re
import statistics
import sys

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
FEW = 30            # below this many trades the totals carry a warning
BY = ("setup", "symbol", "hour", "weekday", "exit", "tag")


class JournalError(Exception):
    pass


# ---------------------------------------------------------------- files

def read_json(path, default):
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as e:
        raise JournalError("%s is not valid JSON: %s" % (path, e))


def write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _day(rec):
    return str(rec.get("date") or str(rec.get("at", ""))[:10])


# ---------------------------------------------------------------- stats

def wilson(k, n, z=1.96):
    """95 % range for a win rate of k out of n (Wilson score interval)."""
    if not n:
        return None
    p = float(k) / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4.0 * n * n)) / den
    return [round(max(0.0, mid - half), 4), round(min(1.0, mid + half), 4)]


def summarize(trades):
    """Totals for a list of closed trades."""
    n = len(trades)
    out = {"n": n}
    if not n:
        return out
    with_r = [t["R"] for t in trades if t.get("R") is not None]
    wins = sum(1 for t in trades if t["pnl"] > 0)
    out.update({"wins": wins, "losses": n - wins, "win_rate": round(float(wins) / n, 4),
                "win_range": wilson(wins, n), "pnl": round(sum(t["pnl"] for t in trades), 2),
                "slippage_cost": round(sum(t.get("slippage_cost") or 0 for t in trades), 2)})
    if with_r:
        avg = statistics.mean(with_r)
        half = 1.96 * statistics.stdev(with_r) / math.sqrt(len(with_r)) if len(with_r) > 1 else None
        out.update({"with_R": len(with_r), "avg_R": round(avg, 3), "total_R": round(sum(with_r), 2),
                    "avg_R_range": [round(avg - half, 3), round(avg + half, 3)] if half is not None else None,
                    "worst_R": round(min(with_r), 2), "best_R": round(max(with_r), 2),
                    "beyond_stop": sum(1 for r in with_r if r < -1.05)})
    return out


# ---------------------------------------------------------------- trades from fills

def risk_from_orders(rows, symbol, day):
    """Planned risk a share from the day's placed/approved entry: max_loss / qty."""
    for r in reversed(rows):
        if r.get("symbol") == symbol and _day(r) == day and r.get("status") in ("placed", "approved") \
                and r.get("kind", "entry") == "entry":
            ml, q = _f(r.get("max_loss")), _f(r.get("qty"))
            if ml and q:
                return ml / q
    return None


def build_trades(state, notes=None):
    """(closed trades, open lots) from trader-broker's log."""
    rows = state.get("orders", [])
    fills = [r for r in rows if r.get("status") == "filled"]
    fills.sort(key=lambda r: str(r.get("at", "")))
    open_lots = {}
    closed = []
    for f in fills:
        sym = str(f.get("symbol", "")).upper()
        qty, px = _f(f.get("qty")), _f(f.get("price"))
        if not qty or not px:
            continue
        slip = (f.get("slippage") or {}).get("dollars") or 0.0
        if f.get("side") == "buy":
            risk = _f(f.get("risk_per_share")) or risk_from_orders(rows, sym, _day(f))
            open_lots.setdefault(sym, []).append({
                "symbol": sym, "date": _day(f), "entry_at": f.get("at"), "qty": qty, "left": qty,
                "entry": px, "risk_per_share": risk, "setup": f.get("setup") or "unknown",
                "stop": _f(f.get("stop")), "target": _f(f.get("target")),
                "exits": [], "slippage_cost": slip})
            continue
        left = qty
        lots = open_lots.get(sym, [])
        while left > 1e-9 and lots:
            lot = lots[0]
            take = min(left, lot["left"])
            lot["exits"].append({"qty": take, "price": px, "at": f.get("at"), "kind": f.get("kind") or "other"})
            lot["slippage_cost"] += slip * take / qty
            lot["left"] -= take
            left -= take
            if lot["left"] <= 1e-9:
                closed.append(finish(lots.pop(0)))
    by_key = {}
    for n in (notes or {}).get("notes", []):
        by_key.setdefault((str(n.get("symbol", "")).upper(), n.get("date")), []).append(n)
    for t in closed:
        ns = by_key.get((t["symbol"], t["date"]), [])
        t["tags"] = sorted({tag for n in ns for tag in n.get("tags", [])})
        t["notes"] = [n["text"] for n in ns if n.get("text")]
    still_open = [dict(l, shares_open=l["left"]) for ls in open_lots.values() for l in ls]
    return closed, still_open


def finish(lot):
    q = sum(e["qty"] for e in lot["exits"])
    exit_px = sum(e["qty"] * e["price"] for e in lot["exits"]) / q
    kinds = sorted({e["kind"] for e in lot["exits"]})
    per = exit_px - lot["entry"]
    risk = lot["risk_per_share"]
    entry_t = str(lot["entry_at"] or "")[11:16]
    try:
        wd = WEEKDAYS[datetime.date.fromisoformat(lot["date"]).weekday()]
    except ValueError:
        wd = "?"
    return {
        "date": lot["date"], "symbol": lot["symbol"], "setup": lot["setup"], "qty": lot["qty"],
        "entry": round(lot["entry"], 4), "entry_time": entry_t, "exit": round(exit_px, 4),
        "exit_time": str(lot["exits"][-1]["at"] or "")[11:16],
        "exit_kind": kinds[0] if len(kinds) == 1 else "mixed",
        "pnl": round(per * lot["qty"], 2), "risk_per_share": round(risk, 4) if risk else None,
        "R": round(per / risk, 3) if risk else None,
        "slippage_cost": round(lot["slippage_cost"], 2),
        "hour": (entry_t[:2] + ":00") if entry_t else "?", "weekday": wd,
    }


def group_key(t, by):
    if by == "exit":
        return [t["exit_kind"]]
    if by == "tag":
        return t.get("tags") or ["(no tag)"]
    return [str(t.get(by, "?"))]


def groups(trades, by):
    out = {}
    for t in trades:
        for k in group_key(t, by):
            out.setdefault(k, []).append(t)
    return {k: summarize(v) for k, v in sorted(out.items())}


# ---------------------------------------------------------------- output

def money(v):
    s = "{:,.2f}".format(abs(v))
    return ("-$" if v < 0 else "$") + s


def pct(x):
    return "%.0f %%" % (100 * x)


def total_lines(s, label="All trades"):
    if not s["n"]:
        return ["%s: none." % label]
    lines = ["%s: %d, won %d (%s; 95 %% range %s to %s), %s in all%s." % (
        label, s["n"], s["wins"], pct(s["win_rate"]), pct(s["win_range"][0]), pct(s["win_range"][1]),
        money(s["pnl"]), (", fill costs %s" % money(s["slippage_cost"])) if s["slippage_cost"] else "")]
    if s.get("with_R"):
        rng = (" (95 %% range %+.2f to %+.2f)" % tuple(s["avg_R_range"])) if s.get("avg_R_range") else ""
        lines.append("  Average R %+.3f%s, total %+.2fR, best %+.2fR, worst %+.2fR." % (
            s["avg_R"], rng, s["total_R"], s["best_R"], s["worst_R"]))
        if s["beyond_stop"]:
            lines.append("  %d loss%s went past -1R: the stop filled worse than planned, or there was no stop."
                         % (s["beyond_stop"], "" if s["beyond_stop"] == 1 else "es"))
        if s["with_R"] < s["n"]:
            lines.append("  %d trade(s) have no planned risk on record, so no R." % (s["n"] - s["with_R"]))
    if s["n"] < FEW:
        lines.append("  Only %d trades: too few to know your real win rate or edge. Keep the journal going."
                     % s["n"])
    return lines


def report(trades, still_open, bys):
    lines = []
    if trades:
        lines.append("%-10s %-6s %-7s %5s %5s %10s %10s %-8s %7s %10s" % (
            "date", "symbol", "setup", "in", "out", "entry", "exit", "exit by", "R", "result"))
        for t in trades:
            lines.append("%-10s %-6s %-7s %5s %5s %10.2f %10.2f %-8s %7s %10s%s" % (
                t["date"], t["symbol"], t["setup"][:7], t["entry_time"], t["exit_time"], t["entry"], t["exit"],
                t["exit_kind"], ("%+.2f" % t["R"]) if t["R"] is not None else "-", money(t["pnl"]),
                ("  [%s]" % ", ".join(t["tags"])) if t.get("tags") else ""))
        lines.append("")
    lines += total_lines(summarize(trades))
    for by in bys:
        lines += ["", "By %s:" % by]
        for k, s in groups(trades, by).items():
            avg = ("%+.3f" % s["avg_R"]) if s.get("avg_R") is not None else "  -"
            lines.append("  %-14s %3d trade%s  won %4s  avg R %s  total %s%s" % (
                k, s["n"], " " if s["n"] == 1 else "s", pct(s["win_rate"]), avg, money(s["pnl"]),
                "  (few)" if s["n"] < 10 else ""))
    if still_open:
        lines += ["", "Still open (not in the totals): " + ", ".join(
            "%s %g sh from %s" % (l["symbol"], l["shares_open"], l["date"]) for l in still_open)]
    lines += ["", "R is the result over the risk you planned a share. Education and tooling, not financial advice."]
    return lines


# ---------------------------------------------------------------- commands

def _date(text, what):
    if text and not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        raise JournalError("%s wants a date like 2026-10-19" % what)
    return text


def cmd_show(a):
    state = read_json(a.state, {"orders": []})
    notes = read_json(a.notes, {"notes": []})
    trades, still_open = build_trades(state, notes)
    lo, hi = _date(a.date_from, "--from"), _date(a.date_to, "--to")
    trades = [t for t in trades if (not lo or t["date"] >= lo) and (not hi or t["date"] <= hi)]
    if a.setup:
        trades = [t for t in trades if t["setup"] == a.setup]
    if a.csv:
        cols = ["date", "symbol", "setup", "qty", "entry_time", "entry", "exit_time", "exit", "exit_kind",
                "risk_per_share", "R", "pnl", "slippage_cost", "hour", "weekday"]
        d = os.path.dirname(a.csv)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols + ["tags", "notes"])
            for t in trades:
                w.writerow([t.get(c) for c in cols] + [";".join(t.get("tags", [])), " | ".join(t.get("notes", []))])
    if a.json:
        print(json.dumps({"trades": trades, "open": still_open, "summary": summarize(trades),
                          "by": {b: groups(trades, b) for b in a.by}}, indent=2))
        return 0 if trades else 1
    if not trades:
        print("No closed trades in %s yet. Fills come from ticket.py result --filled-price and ticket.py fill."
              % a.state)
        if still_open:
            print("Open: " + ", ".join("%s %g sh" % (l["symbol"], l["shares_open"]) for l in still_open))
        return 1
    print("\n".join(report(trades, still_open, a.by)))
    if a.csv:
        print("Wrote %s." % a.csv)
    return 0


def cmd_note(a):
    _date(a.date, "--date")
    if not a.tag and not a.text:
        raise JournalError("a note needs --tag or --text")
    doc = read_json(a.notes, {"notes": []})
    tags = sorted({t.strip().lower() for t in (a.tag or []) if t.strip()})
    doc.setdefault("notes", []).append({"date": a.date, "symbol": a.symbol.upper(), "tags": tags,
                                        "text": a.text or ""})
    write_json(a.notes, doc)
    print("Noted %s %s%s." % (a.symbol.upper(), a.date, (": " + ", ".join(tags)) if tags else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Trade journal (trader-broker): your trades scored in R.")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("show", help="closed trades and totals")
    p.add_argument("--state", default="trader/state/broker.json")
    p.add_argument("--notes", default="trader/state/journal.json")
    p.add_argument("--from", dest="date_from")
    p.add_argument("--to", dest="date_to")
    p.add_argument("--setup")
    p.add_argument("--by", action="append", default=[], choices=BY)
    p.add_argument("--csv", metavar="PATH")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("note", help="tag a day's trade in a symbol")
    p.add_argument("--notes", default="trader/state/journal.json")
    p.add_argument("--symbol", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--tag", action="append")
    p.add_argument("--text")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"show": cmd_show, "note": cmd_note}[a.cmd](a)
    except JournalError as e:
        print("journal.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
