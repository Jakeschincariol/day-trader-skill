#!/usr/bin/env python3
"""News Monitor for swing-news: Indian headlines, NSE filings and the dates that move a swing trade.

    python3 news.py                              # watchlist + plan + positions
    python3 news.py --tickers TCS 'M&M' --hours 48
    python3 news.py --no-nse --json
    python3 news.py --all                        # include items already shown

Per stock: Yahoo Finance headlines (region IN), Google News India for the
company name, and, with the optional nse package, NSE corporate
announcements, the next results date and dividend / split / bonus ex-dates
in the next 15 trading days. Items are deduplicated across sources, tagged,
shown newest first in IST, and shown once (trader/state/news.json). Each
stock's move against its previous close sits beside its headlines.
"""

import argparse
import datetime
import email.utils
import hashlib
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from india import cli, data, market, money, symbols  # noqa: E402

TAGS = [
    ("results", r"\bq[1-4]\b|quarterly|\bresults?\b|net profit|profit (rises|falls|jumps|drops|up|down)|revenue|earnings|ebitda"),
    ("dividend", r"dividend|record date"),
    ("split/bonus", r"\bsplit\b|bonus"),
    ("deal", r"acqui|merger|demerger|stake|takeover|buyback|\bipo\b|qip|fund ?rais"),
    ("order win", r"\border\b|contract|\bbags\b|\bwins\b"),
    ("management", r"\bceo\b|\bcfo\b|\bmd\b|resign|appoint|chairman"),
    ("regulatory", r"\bsebi\b|\brbi\b|penalty|probe|\bban\b|raid|\bgst notice|show cause"),
    ("block deal", r"block deal|bulk deal|promoter (sells|buys)|pledge"),
    ("rating", r"upgrade|downgrade|target price|\brating\b|\bbuy call\b|\bsell call\b"),
    ("macro", r"\bnifty\b|sensex|\bfii\b|\bdii\b|rupee|budget|monetary policy|repo rate|inflation"),
]
TAG_RE = [(name, re.compile(rx, re.I)) for name, rx in TAGS]


def tags(title):
    return [name for name, rx in TAG_RE if rx.search(title)]


def to_ist(pub):
    try:
        dt = email.utils.parsedate_to_datetime(pub)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(market.IST).strftime("%Y-%m-%d %H:%M")


def parse_rss(raw, source):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        publisher = (it.findtext("source") or "").strip()
        if source == "google" and " - " in title:
            title, tail = title.rsplit(" - ", 1)
            publisher = publisher or tail.strip()
        t = to_ist(it.findtext("pubDate") or "")
        if title and t:
            out.append({"time_ist": t, "source": source, "publisher": publisher, "title": title.strip(),
                        "url": (it.findtext("link") or "").strip()})
    return out


def _norm(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def dedupe(items):
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x["time_ist"]):
        k = _norm(it["title"])
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def company_names(ctx):
    try:
        return {r["symbol"]: re.sub(r"\s+(Limited|Ltd\.?)$", "", r["name"], flags=re.I)
                for r in data.nse_equity_list(ctx.fetcher)}
    except data.DataError:
        return {}


def feeds(ctx, s, name):
    items = []
    y = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s&region=IN&lang=en-IN" % symbols.yahoo_path_part(s)
    q = urllib.parse.quote('"%s" share' % (name or s.code))
    g = "https://news.google.com/rss/search?q=%s&hl=en-IN&gl=IN&ceid=IN:en" % q
    for source, url in (("yahoo", y), ("google", g)):
        try:
            items += parse_rss(ctx.fetcher.get(url, "rss-%s-%s.xml" % (source, symbols.safe_filename(s))), source)
        except data.DataError:
            pass
    return items


def tickers(ctx, a):
    if a.tickers:
        return a.tickers
    out = [h["symbol"] for h in (ctx.read("watchlist.json") or {}).get("hits", [])]
    plan = ctx.read("plan.json")
    if plan:
        out.append(plan["symbol"])
    out += [p["symbol"] for p in (ctx.read("positions.json") or {}).get("positions", [])]
    return list(dict.fromkeys(out))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="news.py", description=__doc__.split("\n")[0])
    ap.add_argument("--tickers", nargs="*")
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--no-nse", action="store_true")
    ap.add_argument("--all", action="store_true")
    cli.common_args(ap)
    a = ap.parse_args(argv)
    ctx = cli.Ctx(a)
    names = tickers(ctx, a)
    if not names:
        ctx.emit({"error": "no tickers"}, "news: no tickers: pass --tickers, or run /swing-scanner first")
        return 2
    since = (ctx.now - datetime.timedelta(hours=a.hours)).strftime("%Y-%m-%d %H:%M")
    state = ctx.read("state/news.json") or {"seen": []}
    seen = set(state["seen"])
    cnames = company_names(ctx)
    use_nse = not a.no_nse
    if use_nse:
        ctx.nse_notice()
    today = ctx.now.date()
    horizon = market.add_trading_days(today, 15)
    items, moves, events = [], {}, {}
    for n in names:
        try:
            s = symbols.parse(n)
        except ValueError:
            continue
        got = feeds(ctx, s, cnames.get(s.code))
        if use_nse and ctx.nse.available:
            got += [{"time_ist": x["time_ist"], "source": "nse", "publisher": "NSE filing", "title": x["subject"] +
                     (": " + x["text"][:160] if x["text"] else ""), "url": x["url"]}
                    for x in ctx.nse.announcements(s.code, today - datetime.timedelta(days=7), today)]
            ev = []
            ev += ["results %s" % d for d in (ctx.nse.results_dates([s.code], today, horizon) or {}).get(s.code, [])]
            ev += ["ex-date %s (%s)" % (x["ex_date"], x["purpose"])
                   for x in (ctx.nse.corporate_actions([s.code], today, horizon) or {}).get(s.code, [])]
            if ev:
                events[s.code] = ev
        for it in dedupe(got):
            if it["time_ist"] < since:
                continue
            key = hashlib.sha1((it["url"] + it["title"]).encode("utf-8")).hexdigest()[:16]
            if key in seen and not a.all:
                continue
            seen.add(key)
            items.append(dict(it, symbol=s.code, tags=tags(it["title"])))
        try:
            bars = data.drop_unfinished(data.yahoo_daily(ctx.fetcher, s, "1y"), ctx.now)
            if len(bars) >= 2:
                moves[s.code] = {"date": bars[-1]["d"], "close": bars[-1]["c"],
                                 "pct": round((bars[-1]["c"] / bars[-2]["c"] - 1) * 100, 2)}
        except data.DataError:
            pass
    items.sort(key=lambda x: x["time_ist"], reverse=True)
    state["seen"] = list(seen)[-3000:]
    ctx.write("state/news.json", state)
    lines = []
    codes = []
    for n in names:
        try:
            codes.append(symbols.parse(n).code)
        except ValueError:
            lines.append("%s: not an NSE/BSE symbol" % n)
    for code in dict.fromkeys(codes):
        m = moves.get(code)
        head = "%s%s" % (code, "  %s close %s (%+.2f%%)" % (m["date"], money.inr(m["close"]), m["pct"]) if m else "")
        lines.append(head)
        for e in events.get(code, []):
            lines.append("  UPCOMING " + e)
        mine = [i for i in items if i["symbol"] == code]
        for i in mine[:12]:
            lines.append("  %s  %-7s %s%s" % (i["time_ist"], i["source"], i["title"],
                                             "  [%s]" % ", ".join(i["tags"]) if i["tags"] else ""))
        if not mine:
            lines.append("  nothing new in the last %g hours" % a.hours)
    lines.append("Headlines are not signals; results inside a planned hold are the main thing to act on. "
                 "Not financial advice. Next: /swing-entry.")
    ctx.emit({"since": since, "items": items, "moves": moves, "events": events}, "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
