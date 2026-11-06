#!/usr/bin/env python3
"""Results Monitor for trader-news: quarterly results and board meetings for the stocks you
watch, from NSE's own public RSS feeds. Standard library only.

    python3 news.py                                  # watchlist + plan + portfolio
    python3 news.py --tickers RELIANCE TCS --hours 24
    python3 news.py --days 7 --json
    python3 news.py --offline tests/fixtures/trader-news --now "2026-11-06 16:00" --all

Three things, per ticker, newest first, times in IST:
  UPCOMING   a board meeting that will consider financial results, with the days left
             and what it means for a day trade (results that drop mid-session gap a stock).
  RESULTS    results filed in the last --hours: the period, standalone or consolidated, the
             filing link, and whether it landed before the open, in the session or after it.
  FILINGS    other exchange announcements in that window (order wins, fund raising,
             directors, dividends...), by their NSE subject line.
A stock 3 % or more from yesterday's close (--move-pct) is marked MOVING.

Feeds (no key, no login; a plain request with an honest User-Agent works):
  https://nsearchives.nseindia.com/content/RSS/Board_Meetings.xml
  https://nsearchives.nseindia.com/content/RSS/Financial_Results.xml
  https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml
  https://archives.nseindia.com/content/equities/EQUITY_L.csv   (company name -> symbol)
The feeds carry company names, not symbols, and only recent filings: a meeting announced
two weeks ago may no longer be in the feed. No UPCOMING line is NOT proof that no results are
due; check the NSE board-meetings page for anything you plan to hold.

The feeds give the filing, not the numbers: open the link (a PDF or XBRL file) and read it.
For the last quarters' revenue and profit side by side, use /trader-analyst.

State: trader/state/news.json remembers what was shown (30 days), so a repeat run shows only
what is new. --all shows everything again.
"""

import argparse
import csv
import datetime
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trader-data"))
import kitefeed  # noqa: E402  (Zerodha Kite Connect source, off unless TRADER_DATA_SOURCE=kite)

UA = "day-trader-skills-nse/1.0 (personal research tool)"   # NSE's CDN drops a User-Agent that carries a URL
FEEDS = {
    "board": "https://nsearchives.nseindia.com/content/RSS/Board_Meetings.xml",
    "results": "https://nsearchives.nseindia.com/content/RSS/Financial_Results.xml",
    "announcements": "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml",
}
EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
CHART = "https://query2.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=5m"
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)   # India has no daylight saving
OPEN, CLOSE = datetime.time(9, 15), datetime.time(15, 30)
KEEP_DAYS = 30
STALE_PERIOD_DAYS = 150     # a "result" for a period ended this long before it was filed is a late filing
RESULT_WORDS = re.compile(r"financial results?|results? for the (quarter|period|year|half)|unaudited|audited", re.I)
NAME_NOISE = re.compile(r"\b(LIMITED|LTD|THE)\b")


class NewsError(Exception):
    pass


# ---------------------------------------------------------------- time

def to_ist(utc):
    return utc.replace(tzinfo=None) + IST_OFFSET


def parse_now(text):
    """--now -> naive IST. "2026-11-06 16:00" is IST; an offset or Z makes it absolute."""
    if not text:
        return to_ist(datetime.datetime.now(datetime.timezone.utc))
    t = text.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(t)
    except ValueError:
        raise NewsError('--now wants an IST time like "2026-11-06 16:00" (or ...Z for UTC)')
    return dt if dt.tzinfo is None else to_ist(dt - dt.utcoffset())


def parse_feed_time(text):
    """'06-Nov-2026 15:48:50' (IST) -> naive datetime, or None."""
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return datetime.datetime.strptime(text.strip(), fmt)
        except ValueError:
            pass
    return None


def parse_date(text):
    try:
        return datetime.datetime.strptime(text.strip(), "%d-%b-%Y").date()
    except ValueError:
        return None


def session_word(t):
    """Where a filing time sits against the trading day."""
    if t.weekday() >= 5:
        return "on a weekend"
    if t.time() < OPEN:
        return "before the open"
    if t.time() <= CLOSE:
        return "during the session"
    return "after the close"


# ---------------------------------------------------------------- network

def _read(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch(url, retries=1):
    last = None
    for attempt in range(retries + 1):
        try:
            return _read(url)
        except urllib.error.HTTPError as e:
            last = "HTTP %d" % e.code
            e.close()
            if e.code in (403, 401):
                raise NewsError("NSE refused %s (HTTP %d). It does not answer every client; try again later, "
                                "or use --offline with saved feeds." % (url, e.code))
            if e.code != 429 and e.code < 500:
                break
        except (urllib.error.URLError, OSError) as e:
            last = "could not connect: %s" % getattr(e, "reason", e)
        if attempt < retries:
            time.sleep(3)
    raise NewsError("%s did not answer (%s)" % (url, last))


def load_text(name, url, offline):
    if offline:
        path = os.path.join(offline, name)
        if not os.path.exists(path):
            raise NewsError("no %s in %s" % (name, offline))
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    return fetch(url)


# ---------------------------------------------------------------- parsing

def norm_name(name):
    s = re.sub(r"[^A-Z0-9 ]", " ", name.upper().replace("&", " AND "))
    return " ".join(NAME_NOISE.sub(" ", s).split())


def parse_names(csv_text):
    """EQUITY_L.csv -> {normalised company name: SYMBOL} for the EQ series."""
    out = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        row = {k.strip().upper(): (v or "").strip() for k, v in row.items() if k}
        if row.get("SERIES") == "EQ" and row.get("SYMBOL"):
            out.setdefault(norm_name(row.get("NAME OF COMPANY", "")), row["SYMBOL"].upper())
    if not out:
        raise NewsError("EQUITY_L.csv had no EQ rows")
    return out


def parse_rss(text, feed):
    """RSS -> [{company, link, desc, subject, time}]. NSE puts 'text |SUBJECT: x' in description."""
    try:
        root = ET.fromstring(text.strip())
    except ET.ParseError as e:
        raise NewsError("%s feed is not valid XML: %s" % (feed, e))
    items = []
    for it in root.iter("item"):
        desc = " ".join((it.findtext("description") or "").split())
        subject = ""
        if "|SUBJECT:" in desc:
            desc, subject = [x.strip() for x in desc.split("|SUBJECT:", 1)]
        items.append({"feed": feed, "company": " ".join((it.findtext("title") or "").split()),
                      "link": (it.findtext("link") or "").strip(), "desc": desc, "subject": subject,
                      "time": parse_feed_time(it.findtext("pubDate") or "")})
    return items


def meeting_date(desc):
    m = re.search(r"Meeting Date:\s*(\d{1,2}-[A-Za-z]{3}-\d{4})", desc) or \
        re.search(r"to be held on\s*(\d{1,2}-[A-Za-z]{3}-\d{4})", desc)
    return parse_date(m.group(1)) if m else None


def result_facts(desc):
    """'RELATING TO:First Quarter |...|PERIOD ENDED: 30-Jun-2024' -> dict of the pieces."""
    f = {}
    for part in desc.split("|"):
        if ":" in part:
            k, v = part.split(":", 1)
            f[k.strip().upper()] = v.strip()
    return {"relating_to": f.get("RELATING TO", ""), "audit": f.get("AUDITED/UNAUDITED", ""),
            "basis": f.get("CONSOLIDATED/NON-CONSOLIDATED", ""), "period": f.get("PERIOD", ""),
            "period_ended": parse_date(f.get("PERIOD ENDED", ""))}


# ---------------------------------------------------------------- what to watch

def _read_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        return None


def watched(args):
    if args.tickers:
        return [t.upper() for t in args.tickers], "--tickers"
    out, src = [], []
    wl = _read_json(args.watchlist)
    for h in (wl or {}).get("hits", []):
        if h.get("symbol"):
            out.append(h["symbol"].upper())
    if out:
        src.append(args.watchlist)
    plan = _read_json(args.plan) or {}
    if plan.get("symbol"):
        out.append(plan["symbol"].upper())
        src.append(args.plan)
    pf = _read_json(args.portfolio) or {}
    for p in pf.get("positions", []):
        if p.get("ticker"):
            out.append(p["ticker"].upper())
            src.append(args.portfolio)
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq, ", ".join(dict.fromkeys(src))


# ---------------------------------------------------------------- the three lists

def build(items, names, symbols, now, hours, days):
    want = set(symbols)
    upcoming, results, filings, unmatched = [], [], [], 0
    cutoff = now - datetime.timedelta(hours=hours)
    for it in items:
        sym = names.get(norm_name(it["company"]))
        if sym is None:
            unmatched += 1
            continue
        if sym not in want or it["time"] is None:
            continue
        it["symbol"] = sym
        if it["feed"] == "board":
            md = meeting_date(it["desc"])
            if md and now.date() <= md <= now.date() + datetime.timedelta(days=days) and \
                    (RESULT_WORDS.search(it["desc"]) or "Board Meeting Intimation" in it["desc"]):
                about_results = bool(RESULT_WORDS.search(it["desc"]))
                upcoming.append({"symbol": sym, "company": it["company"], "meeting": md.isoformat(),
                                 "days": (md - now.date()).days, "results": about_results,
                                 "announced": it["time"].strftime("%Y-%m-%d %H:%M"), "link": it["link"]})
            continue
        if it["time"] < cutoff or it["time"] > now:
            continue
        is_result = it["feed"] == "results" or (it["subject"] == "Outcome of Board Meeting" and RESULT_WORDS.search(it["desc"]))
        if is_result:
            f = result_facts(it["desc"]) if it["feed"] == "results" else {}
            late = bool(f.get("period_ended") and (it["time"].date() - f["period_ended"]).days > STALE_PERIOD_DAYS)
            results.append({"symbol": sym, "company": it["company"], "time": it["time"].strftime("%Y-%m-%d %H:%M"),
                            "when": session_word(it["time"]), "relating_to": f.get("relating_to", ""),
                            "basis": f.get("basis", ""), "audit": f.get("audit", ""),
                            "period_ended": f["period_ended"].isoformat() if f.get("period_ended") else "",
                            "late_filing": late, "link": it["link"],
                            "note": "" if f else it["desc"][:160]})
        elif it["feed"] == "announcements":
            filings.append({"symbol": sym, "company": it["company"], "time": it["time"].strftime("%Y-%m-%d %H:%M"),
                            "subject": it["subject"] or it["desc"][:80], "link": it["link"]})
    dedupe = lambda rows, key: list({key(r): r for r in rows}.values())
    merged = {}
    for r in upcoming:                       # one line per meeting; a results purpose beats "intimation"
        k = (r["symbol"], r["meeting"])
        if k not in merged or r["results"]:
            merged[k] = r
    upcoming = list(merged.values())
    results = dedupe(results, lambda r: (r["symbol"], r["link"], r["time"]))
    filings = dedupe(filings, lambda r: (r["symbol"], r["link"]))
    upcoming.sort(key=lambda r: (r["meeting"], r["symbol"]))
    results.sort(key=lambda r: r["time"], reverse=True)
    filings.sort(key=lambda r: r["time"], reverse=True)
    return upcoming, results, filings, unmatched


def day_trade_note(u):
    if not u["results"]:
        return "purpose not stated: open the link before trading it"
    if u["days"] == 0:
        return "results due TODAY, often mid-session: a mid-day filing can gap the stock; skip it or be flat before the meeting"
    if u["days"] == 1:
        return "results tomorrow: today's trade is out by flat_by, but tomorrow's open can gap on them"
    return "results in %d days: not today's risk" % u["days"]


# ---------------------------------------------------------------- price move

def move_today(sym, offline=None):
    """(last, prev_close, pct) from today's chart, or None. Kite when switched on, else Yahoo."""
    if offline:
        return None
    path = "/v8/finance/chart/%s?range=1d&interval=5m" % urllib.parse.quote(sym + ".NS", safe="")
    try:
        text = kitefeed.maybe_get(path)
        if text is None:
            text = fetch("https://query2.finance.yahoo.com" + path, retries=0)
        meta = json.loads(text)["chart"]["result"][0]["meta"]
    except (kitefeed.KiteError, NewsError, ValueError, KeyError, TypeError, IndexError):
        return None
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if not price or not prev:
        return None
    return price, prev, (price / prev - 1) * 100.0


# ---------------------------------------------------------------- state

def load_state(path):
    st = _read_json(path) or {}
    st.setdefault("seen", {})
    return st


def prune(state, now):
    keep = (now - datetime.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    state["seen"] = {k: v for k, v in state["seen"].items() if v >= keep}


def save_state(path, state):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------- output

def render(doc):
    out = ["Results monitor, %s IST. Watching %d: %s." % (doc["as_of"], len(doc["symbols"]), ", ".join(doc["symbols"]))]
    for sym, mv in doc["moves"].items():
        if mv and abs(mv["pct"]) >= doc["move_pct"]:
            out.append("  MOVING  %s %+.2f%% (last %.2f, prev close %.2f)" % (sym, mv["pct"], mv["last"], mv["prev_close"]))
    out.append("")
    out.append("UPCOMING board meetings, next %d days:" % doc["days"])
    for u in doc["upcoming"]:
        out.append("  %s  %s  in %d day%s  %s" % (u["meeting"], u["symbol"], u["days"], "" if u["days"] == 1 else "s", day_trade_note(u)))
        out.append("      %s" % u["link"])
    if not doc["upcoming"]:
        out.append("  none in the feed. That is not proof none is due: the feed only holds recent filings.")
    out.append("")
    out.append("RESULTS filed in the last %d hours:" % doc["hours"])
    for r in doc["results"]:
        what = " ".join(x for x in (r["relating_to"], r["basis"], r["audit"]) if x) or r["note"]
        late = "  [LATE FILING for period ended %s]" % r["period_ended"] if r["late_filing"] else (
            "  [period ended %s]" % r["period_ended"] if r["period_ended"] else "")
        out.append("  %s  %s  %s (%s)%s" % (r["time"], r["symbol"], what, r["when"], late))
        out.append("      %s" % r["link"])
    if not doc["results"]:
        out.append("  none new.")
    out.append("")
    out.append("OTHER FILINGS:")
    for f in doc["filings"][:25]:
        out.append("  %s  %s  %s" % (f["time"], f["symbol"], f["subject"]))
        out.append("      %s" % f["link"])
    if not doc["filings"]:
        out.append("  none new.")
    if len(doc["filings"]) > 25:
        out.append("  ... and %d more (use --json)." % (len(doc["filings"]) - 25))
    out.append("")
    out.append("%d feed item%s could not be matched to a symbol (company name not in the NSE EQ list). "
               "Filings are leads, not facts: open the link and read it. Not financial advice."
               % (doc["unmatched"], "" if doc["unmatched"] == 1 else "s"))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Quarterly results and board meetings for your watchlist (trader-news).")
    ap.add_argument("--tickers", nargs="+", help="NSE symbols (default: watchlist, plan and portfolio)")
    ap.add_argument("--hours", type=int, default=24, help="how far back to look for filed results (default 24)")
    ap.add_argument("--days", type=int, default=7, help="how far ahead to look for board meetings (default 7)")
    ap.add_argument("--move-pct", type=float, default=3.0)
    ap.add_argument("--all", action="store_true", help="show items again, even ones shown before")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-chart", action="store_true", help="skip the price-move lookup")
    ap.add_argument("--offline", metavar="DIR", help="read Board_Meetings.xml, Financial_Results.xml, "
                    "Online_announcements.xml and EQUITY_L.csv from DIR")
    ap.add_argument("--now", help='pretend it is this IST time, e.g. "2026-11-06 16:00"')
    ap.add_argument("--watchlist", default="trader/watchlist.json")
    ap.add_argument("--plan", default="trader/plan.json")
    ap.add_argument("--portfolio", default="trader/portfolio.json")
    ap.add_argument("--state", default="trader/state/news.json")
    a = ap.parse_args(argv)
    try:
        now = parse_now(a.now)
        symbols, src = watched(a)
        if not symbols:
            raise NewsError("nothing to watch: pass --tickers, or run trader-scanner first")
        names = parse_names(load_text("EQUITY_L.csv", EQUITY_URL, a.offline))
        items = []
        for key, fname in (("board", "Board_Meetings.xml"), ("results", "Financial_Results.xml"),
                           ("announcements", "Online_announcements.xml")):
            items += parse_rss(load_text(fname, FEEDS[key], a.offline), key)
        upcoming, results, filings, unmatched = build(items, names, symbols, now, a.hours, a.days)
        state = load_state(a.state)
        prune(state, now)
        today = now.strftime("%Y-%m-%d")
        if not a.all:
            fresh = lambda key: key not in state["seen"]
            upcoming = [u for u in upcoming if fresh("u|%s|%s" % (u["symbol"], u["meeting"]))]
            results = [r for r in results if fresh("r|%s|%s" % (r["symbol"], r["link"]))]
            filings = [f for f in filings if fresh("f|%s|%s" % (f["symbol"], f["link"]))]
        moves = {}
        if not a.no_chart:
            for i, s in enumerate(symbols):
                if i and not a.offline:
                    time.sleep(0.4)
                mv = move_today(s, a.offline)
                moves[s] = {"last": mv[0], "prev_close": mv[1], "pct": round(mv[2], 2)} if mv else None
        doc = {"as_of": now.strftime("%Y-%m-%d %H:%M"), "symbols": symbols, "source": src, "hours": a.hours,
               "days": a.days, "move_pct": a.move_pct, "upcoming": upcoming, "results": results,
               "filings": filings, "moves": moves, "unmatched": unmatched}
        print(json.dumps(doc, indent=2) if a.json else render(doc))
        for u in upcoming:
            state["seen"]["u|%s|%s" % (u["symbol"], u["meeting"])] = today
        for r in results:
            state["seen"]["r|%s|%s" % (r["symbol"], r["link"])] = today
        for f in filings:
            state["seen"]["f|%s|%s" % (f["symbol"], f["link"])] = today
        if not a.offline:
            save_state(a.state, state)
        return 0
    except NewsError as e:
        print("news.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
