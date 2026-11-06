---
name: trader-news
description: >-
  Results Monitor for the NSE. Tracks quarterly results and board meetings for
  every stock you watch, from NSE's own public RSS feeds: which companies
  have a board meeting to approve financial results in the next few days
  (and what that means for a day trade), which have just filed results
  (period, standalone or consolidated, the filing link, and whether it landed
  before the open, in the session or after the close), and other exchange
  announcements by subject. Marks a stock 3 % or more from yesterday's close
  as MOVING. Shows only what is new since the last check, in IST, and never
  repeats an item. Use when the user says "any results today", "who reports
  this week", "why is this moving", "what's the news on my watchlist",
  "morning briefing", "did anything break", "check the board meetings", or
  after /trader-scanner finds setups.
argument-hint: "[tickers]"
---

# trader-news

A chart can look perfect and still be about to gap on a results announcement.
On the NSE, companies file results all through the day, often in the middle
of the session, so a stock that reports at 1 PM can move 5 % in minutes.
Before a setup becomes a trade, this skill reads NSE's feeds for every stock
on the watchlist and tells you only what is new. It also prints how far each
stock is from yesterday's close, so a filing and a move sit side by side.

Tool in this folder (standard library Python, no keys, no login):

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                              # watchlist + plan + portfolio
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE TCS --hours 24 --days 7
python3 "${CLAUDE_SKILL_DIR}/news.py" --all --json                 # show everything again, machine-readable
python3 "${CLAUDE_SKILL_DIR}/news.py" --offline DIR --now "2026-11-06 16:00"   # saved feeds
```

## What it reads and writes

| file / feed | what |
| --- | --- |
| `--tickers`, else `trader/watchlist.json` | the scanner's hits (trader-scanner) |
| `trader/plan.json`, `trader/portfolio.json` | the trade you are planning and what you hold |
| `nsearchives.nseindia.com/content/RSS/Board_Meetings.xml` | board meetings, with their date and purpose |
| `.../RSS/Financial_Results.xml` | results as they are filed (period, audited or not, consolidated or not) |
| `.../RSS/Online_announcements.xml` | all exchange announcements, by subject |
| `archives.nseindia.com/content/equities/EQUITY_L.csv` | company name to symbol (the feeds carry names, not symbols) |
| Yahoo chart (or Kite if `TRADER_DATA_SOURCE=kite`) | the last price against yesterday's close |
| `trader/state/news.json` | what has been shown (kept 30 days) |

## What it prints

- **UPCOMING**: board meetings in the next `--days` (default 7) that will consider
  results, with the days left and a day-trade note: results today may drop mid-session and
  gap the stock (skip it, or be flat first); results tomorrow do not touch a trade that is flat by 15:10.
- **RESULTS**: filings in the last `--hours` (default 24): "First Quarter", Consolidated
  or not, audited or not, the period ended, the time, and where that sits against the session
  (before the open / during the session / after the close / on a weekend). A filing for a
  period that ended more than 150 days before it was filed is marked LATE FILING, so an old
  quarter filed late is not mistaken for a fresh result.
- **OTHER FILINGS**: the NSE subject line of each other announcement (order wins, fund
  raising, directors, dividends), newest first.
- **MOVING**: a stock 3 % or more from yesterday's close (`--move-pct`).

## The rules

- **A filing is a lead, not a fact.** The feed gives the filing, not the numbers. Before telling the
  user what a company reported, open the link (a PDF or XBRL file) and read it, then quote the
  source. If you cannot read it, say so. For the last few quarters side by side, use `/trader-analyst`.
- **No UPCOMING line is not proof that nothing is due.** The feeds hold only recent filings; a meeting
  announced two weeks ago may be gone from them. For a stock the user plans to hold, tell them
  to check the board-meetings page on nseindia.com.
- **Unmatched names.** The feed names companies, and the match to a symbol goes through the NSE EQ list.
  SME, REIT and other non-EQ names do not match. The tool prints how many items it could not match.
  Tested on 2026-11-06: 24 of 91 "Outcome of Board Meeting" items had no EQ symbol (mostly SME and trusts).
- **Say what it touches.** Name the ticker, the period and the basis (standalone or consolidated).
- **No predictions.** Report what was filed and how far the price is from yesterday's close. Never
  say what the stock will do next, and never call a result good or bad: the market decides that,
  and the numbers need the filing's context.

## Steps

1. Run it for the watchlist (or the tickers the user names). Tell the user the counts: how many stocks,
   how many results filed, how many meetings coming, how many items could not be matched.
2. For each RESULTS line that matters, open the link and read the revenue, profit and any one-offs.
   Say if you could not open it.
3. For each UPCOMING line, say the date and the day-trade note.
4. Hand a chosen stock on to `/trader-entry TICKER`. If it reports today, say that first.

## Data and limits

- NSE's CDN refuses some clients. This tool sends a plain User-Agent with no URL in it (one with a URL
  was dropped on 2026-11-06). If NSE answers 403, the tool says so and stops; use `--offline` with
  saved feeds. It never tries to look like a browser.
- The feeds are public and unofficial in the sense that they can change shape. A broken feed is reported,
  not guessed around.
- Times in the feeds are IST.

## What it never does

It never says a result is good or bad, never predicts a move, never places an order, and never summarises
a filing it could not open.

## Safety

- Education and tooling, not financial advice.
- No skill in this pack places an order. You place every order yourself in Zerodha Kite.
