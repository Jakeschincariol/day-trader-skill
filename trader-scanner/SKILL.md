---
name: trader-scanner
description: >-
  Chart Scanner for the NSE. Scans the whole NSE EQ list for setups:
  opening-range breakouts, flags, oversold bounces. Builds the universe from
  NSE's own EQUITY_L.csv (EQ series only, so every name can be bought and
  sold the same day), runs a pre-market scan of daily closes (20-day closing-high
  breakout, bull flag, reclaimed the 20-day average, oversold, oversold bounce)
  and an intraday opening-range breakout scan on 5-minute bars from the 9:15
  open, then writes trader/watchlist.json for trader-news and trader-entry.
  Free Yahoo data (RELIANCE is read as RELIANCE.NS). Use when the user says
  "scan the market", "find me setups", "what is breaking out", "opening range
  breakouts", "scan for bull flags", "oversold stocks", "pre-market scan",
  "build my watchlist", "what should I look at today", or at the start of a
  trading day before /trader-news.
argument-hint: "[universe | daily | orb] [--at HH:MM]"
---

# trader-scanner

The Chart Scanner is the first step of a day trade. It reads about 2,400
free charts and lists the ones that match a rule. That is all it does. A scan
is a list of charts that match a rule, not a list of stocks to buy, and a
setup on a chart is not a prediction. Most people who day trade lose money;
the scanner does not change that. It only saves you from flipping through
2,400 charts by hand.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe                          # -> trader/universe.txt
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily                             # before the open -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --symbols RELIANCE,TCS,INFY # or --watchlist FILE, --limit 200
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb                               # after 9:35 AM IST -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --at 10:15                    # cut the clock at 10:15 AM IST
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --watchlist trader/watchlist.json --json
```

Flags: `--min-price 50` (rupees) and `--min-volume` (daily 1,000,000, orb 0),
`--or-minutes 15`, `--max-confirm 200` (orb stage 2),
`--now "2026-11-06 10:15"` (IST) to pin the clock, `--offline PATH`
to read saved files, `--no-write`, `--show N`, `--json`. Exit code 0
when the scan found something, 1 when it found nothing or could not run (the
reason is one plain line).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/universe.txt` | written by `universe`: one `SYMBOL\|Name` a line, read by `daily` and `orb` |
| `trader/watchlist.json` | written by `daily` and `orb`: `mode`, `as_of`, `universe`, `scanned`, `failed`, `hits[]`. trader-news and trader-entry read `hits[].symbol` |
| `trader/config.json` | read by `orb`: `no_entries_after` (default 15:00) |

## The universe

`universe` downloads `EQUITY_L.csv` from archives.nseindia.com and keeps the
rows whose series is `EQ`. Series `BE` (trade-to-trade, delivery only) and
`BZ` (restricted) are dropped: you cannot buy and sell them on the same day.
SME-board stocks are not in that file. On 2026-11-06 it kept 2,390 of 2,630
rows. Exchange-traded funds are not filtered out by name, so a few ETFs can
appear.

## The daily scan (before the open)

Yahoo's spark endpoint returns closes for 20 symbols a request, so the whole
universe takes about 120 requests, with a polite pause between them. Liquidity
comes from the spark meta: last price at least `--min-price` and last
session's volume at least `--min-volume`. Run it before the open or after the
close: during the session the volume is the day's so far, and today's daily
bar is left out until the 3:30 PM close.

The setups are computed from daily closes only (spark has no highs or lows):

| setup | the rule on closes |
| --- | --- |
| `breakout_20d` | the last close is above every close of the 20 sessions before it |
| `bull_flag` | up more than 10 % over the 10 sessions before the last 5, then the last 5 closes inside a 5 % range |
| `reclaim_ma20` | the close before was under its 20-day average, the last close is above it |
| `oversold` | RSI 14 (Wilder) under 30 |
| `oversold_bounce` | RSI 14 was under 30 yesterday and today closed up |

Hits are listed most traded first (price times volume).

## The opening-range breakout scan (during the session)

The opening range is the first `--or-minutes` (15) of the session: the 9:15,
9:20 and 9:25 five-minute bars. A hit is the first completed 5-minute bar
to CLOSE above the range high, at that bar's close time.

1. Stage 1, every symbol: spark closes of today's 5-minute bars, 20 a
   request. A chart goes on only if a completed bar after the range closed at
   or above the highest close of the range. That is a necessary condition
   (the range high is at least every range close), so no breakout is lost.
2. Stage 2, each candidate: the v8 chart with real highs and lows, one
   request each (through Kite instead if `TRADER_DATA_SOURCE=kite`, see
   `trader-data`). Range high = the highest high of the range bars, range
   low = the lowest low. On a strong morning most charts are candidates, so
   stage 2 checks at most `--max-confirm` (200) of them, the most traded
   first, and prints PARTIAL with the count it skipped. `--max-confirm 0`
   checks them all.

A chart is usable only when every 5-minute bar from 9:15 to the cutoff is
there; a missing bar means a halt or a thin stock. Null closes are dropped,
a bar off the 5-minute grid (the live tick) is dropped, and a bar counts only
once it is complete (start + 5 minutes). Before 9:35 AM IST, on a weekend or
NSE holiday, after the close, or after `no_entries_after` (an expired setup)
it prints one plain line and writes nothing.

## Data and limits

- Yahoo's chart and spark endpoints are free, unofficial and can lag. Bars are
  5-minute bars, never tick by tick. query2 first, query1 on a 429 or 5xx, one
  retry after a 5-second wait on a 429.
- Yahoo has no price for the 15:20 and 15:25 bars on most NSE days (the closing
  auction), so nothing here depends on the last 10 minutes of the session.
- Partial results are said as partial: "Fetched 2,100 of 2,390 charts (290
  failed or had no data)". Never round a partial scan up to "the whole market".
- NSE holidays for 2026 are built in (16 weekdays, read from broker listings of
  NSE's circular on 2026-11-06). The 2027 list is not published yet: the tools
  say so instead of guessing. NSE has no scheduled early closes; the Diwali
  Muhurat session is not modelled.
- Tested live on 2026-11-06 with `daily --symbols RELIANCE,TCS,INFY,M&M,HDFCBANK`
  (5 of 5 fetched; M&M needs its `&` URL-encoded, which the tool does).

## Steps

1. Once a week or so: `scan.py universe`.
2. Before the open: `scan.py daily`. Tell the user the counts (fetched,
   liquid, scanned, hits) and the top few by setup.
3. After 9:35 AM IST (10:15 is the classic): `scan.py orb`. Tell the user how
   many usable charts broke their range and when, and that a later hit is
   closer to the price now.
4. The user picks one chart. Hand it on: `/trader-news TICKER` (results and
   filings), then `/trader-entry TICKER` (the entry bar by bar). Never pick
   for them.

## Rules

- Say what was scanned: how many symbols, how many charts came back, how many
  were usable, and the time of the data.
- Say "matched a rule", never "a buy", "a winner" or "a good trade".
- Never print a P&L, a return or a profit figure.
- A hit is stale once the price has moved on. Re-run before acting on it.

## What it never does

It never places, sizes or checks an order, never says which stock to buy,
never calls data real time, and never promises that a setup works.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- No skill in this pack places an order. You place every order yourself in Zerodha Kite; trader-broker
  only prints the ticket for an order that trader-risk passed today.
- No margin, short selling or leverage unless the config allows it.
- Kite keys live in environment variables, never in the chat.
