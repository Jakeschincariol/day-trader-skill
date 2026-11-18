---
name: swing-news
description: >-
  News Monitor for swing trades on NSE/BSE. For every stock on the
  watchlist, in the plan or held, reads Yahoo Finance headlines (India),
  Google News India for the company name and, with the optional nse
  package, NSE corporate announcements, the next results date and
  dividend, split and bonus ex-dates in the next 15 trading days. Shows only
  what is new since the last check, newest first, in IST, deduplicated
  across sources and tagged (results, dividend, split/bonus, deal, order
  win, management, regulatory, block deal, rating, macro), with each
  stock's move against its previous close. Use when the user says "any news
  on TCS", "why is this stock moving", "when are the results", "is there a
  dividend coming", "check the filings", "news on my watchlist", "morning
  briefing", or after /swing-scanner, before /swing-entry.
argument-hint: "[--tickers TCS M&M] [--hours 24]"
---

# swing-news

A chart can look perfect and still be days away from a results gap, a
regulatory order or a block deal. Before a setup becomes a trade, this
skill reads the feeds that carry those first, for every stock on the
watchlist, and shows only what is new. The most useful line it prints is
often UPCOMING: a results date inside the planned hold changes the trade
more than any headline.

This is not financial advice, and nothing in this pack ever places an
order. A headline is not a signal.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                              # watchlist + plan + positions
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers TCS M&M --hours 48
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-nse --json
python3 "${CLAUDE_SKILL_DIR}/news.py" --all                        # include items already shown
```

Other flags: `--now "2026-11-19 09:00"` (IST), `--offline PATH`, `--dir trader`.

## What it reads and writes

| file / feed | what |
| --- | --- |
| `--tickers`, else `trader/watchlist.json`, `plan.json`, `positions.json` | which stocks |
| Yahoo Finance headline RSS, `region=IN` | headlines per symbol |
| Google News RSS, India edition | the company's name + "share" |
| NSE `EQUITY_L.csv` | company names for the Google search |
| NSE announcements, board meetings, corporate actions (optional `nse` package) | filings, results dates, ex-dates |
| Yahoo daily bars | the last close against the one before |
| `trader/state/news.json` | items already shown |

Without the `nse` package it prints one line saying the NSE data is off and
carries on with the RSS feeds. `pip install -r requirements-nse.txt` turns
it on.

## How to present it

1. Per stock: its last close and move, then any UPCOMING results or
   ex-dates, then the new headlines with their tags.
2. Call out results dates that fall inside a plan's hold (the plan's
   `time_stop_date`); swing-risk will warn about them too.
3. Group repeated coverage of one event into one line.
4. Do not turn a headline into a call. Offer the next step:
   `/swing-entry` on the stock the user picks.

Free feeds can lag, miss items or carry noise (sponsored pieces, other
companies with similar names). Not financial advice.
