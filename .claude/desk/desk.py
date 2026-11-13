"""Trading desk dashboard: one line per desk agent from trader/desk/*.json.

usage: python3 .claude/desk/desk.py [--dir trader/desk] [--items N] [--json]
Shows each agent's status, the age of its report (STALE when older than twice
its cadence), its headline, its top items and every recommendation.
Standard library only. Read-only.
"""
import argparse
import datetime as dt
import glob
import json
import os
import sys
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
ORDER = ["desk-alerts", "desk-broker", "desk-risk", "desk-exit", "desk-entry", "desk-budget",
         "desk-scanner", "desk-news", "desk-analyst", "desk-pelosi", "desk-timemachine"]
MARK = {"alert": "!!", "watch": "! ", "error": "xx", "ok": "  ", "done": "--"}


def load(d):
    out = {}
    for p in glob.glob(os.path.join(d, "desk-*.json")):
        try:
            with open(p, encoding="utf-8") as fh:
                r = json.load(fh)
            out[r.get("agent") or os.path.basename(p)[:-5]] = r
        except (OSError, ValueError) as e:
            out[os.path.basename(p)[:-5]] = {"status": "error", "headline": "unreadable report: %s" % e}
    return out


def age(r, now):
    try:
        t = dt.datetime.fromisoformat(str(r.get("updated")))
        if t.tzinfo is None:
            t = t.replace(tzinfo=NY)
        return (now - t).total_seconds()
    except ValueError:
        return None


def read_inbox(d):
    """Messages the user typed in the desk app (trader/desk/inbox.jsonl). Prints the unread ones and
    advances trader/desk/inbox.cursor.json. They are the user's own words: answer them in the chat."""
    path, cur_path = os.path.join(d, "inbox.jsonl"), os.path.join(d, "inbox.cursor.json")
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
    except (OSError, ValueError):
        rows = []
    try:
        with open(cur_path, encoding="utf-8") as fh:
            cur = json.load(fh).get("read", 0)
    except (OSError, ValueError):
        cur = 0
    new = rows[cur:]
    for r in new:
        print("INBOX %s  %s" % (r.get("at", "?"), r.get("text", "")))
    if not new:
        print("INBOX: no new messages")
    with open(cur_path, "w", encoding="utf-8") as fh:
        json.dump({"read": len(rows)}, fh)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default="trader/desk")
    ap.add_argument("--items", type=int, default=2, help="items to show per agent")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--inbox", action="store_true",
                    help="print the user's unread messages from the desk app and mark them read")
    a = ap.parse_args(argv)
    now = dt.datetime.now(NY)
    if a.inbox:
        return read_inbox(a.dir)
    reps = load(a.dir)
    if a.json:
        print(json.dumps(reps, indent=2))
        return 0
    print("DESK %s New York, %d of %d agents reporting" % (now.strftime("%H:%M:%S"), len(reps), len(ORDER)))
    recs = []
    for name in ORDER + sorted(set(reps) - set(ORDER)):
        r = reps.get(name)
        if r is None:
            print("   %-17s  --  no report yet" % name)
            continue
        sec = age(r, now)
        cad = r.get("cadence_seconds") or 600
        stale = sec is not None and r.get("status") != "done" and sec > 2 * cad
        st = r.get("status", "?")
        when = "?" if sec is None else ("%dm" % (sec // 60) if sec >= 60 else "%ds" % sec)
        print("%s %-17s %-6s %5s%s  %s" % (MARK.get(st, "? "), name, st, when, " STALE" if stale else "",
                                         str(r.get("headline", ""))[:110]))
        for it in (r.get("items") or [])[:a.items]:
            print("      - %s" % json.dumps(it, separators=(",", ":"))[:140])
        for rec in r.get("recommendations") or []:
            recs.append((name, rec))
    if recs:
        print("RECOMMENDATIONS (advice only; the main agent decides and places every order)")
        for name, rec in recs:
            if isinstance(rec, dict):
                print("  [%s] %s: %s (%s)" % (rec.get("urgency", "-"), name, rec.get("action", ""), rec.get("why", "")))
            else:
                print("  %s: %s" % (name, rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
