---
name: swing-scanner
description: >-
  Chart Scanner for swing trading Indian stocks. Builds the NSE equity list
  (series EQ) from NSE's EQUITY_L file and scans daily charts for swing
  setups after the close: 20-day closing-high breakout, 52-week-high
  breakout, bull flag, reclaimed the 20-day average, pullback to a rising
  50-day average, oversold and oversold bounce. Filters on price (Rs 50),
  20-day average traded value (Rs 5 crore a day) and NSE price band (2 %
  and 5 % bands are out), shows delivery % from NSE's bhavcopy, and writes
  trader/watchlist.json for swing-news and swing-entry. Free Yahoo and NSE
  data. Use when the user says "scan the market", "find me swing setups",
  "what is breaking out on NSE", "52-week highs", "bull flags", "oversold
  stocks", "build my watchlist", "what should I look at this week", or
  after the close before /swing-news.
argument-hint: "[universe | daily] [--symbols 'TCS,M&M']"
---

# swing-scanner

The Chart Scanner is the first step of a swing trade. It reads thousands of
free daily charts and lists the ones that match a rule. That is all it does.
A scan is a list of charts that match a rule, not a list of stocks to buy,
and a setup on a chart is not a prediction. Most people who trade actively
lose money; the scanner does not change that. It only saves you from flipping
through 2,000 charts by hand.

This is not financial advice. This pack never places an order: the
pack ends in a trade card the user types into their own broker, and only
after they decide yes.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

Symbols with `&` (M&M) must be single-quoted on the command line, e.g. `'M&M'` or
`--symbols 'TCS,M&M'`: an unquoted `&` makes the shell cut the symbol and run the rest
in the background.
The tools import the shared `india/` folder next to it.

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe                       # -> trader/universe.txt
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily                          # after 15:50 IST -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --symbols 'TCS,M&M,INFY' # or --limit 300
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --bands 10,20,-          # allow only these price bands
```

Flags: `--min-price 50`, `--min-traded-value 50000000` (rupees, 20-day
average of close x volume), `--max-confirm 200` (stage 2), `--include-be`
(universe: add the BE trade-for-trade series), `--now "2026-11-18 16:00"`
(IST) to pin the clock, `--offline PATH` to read saved data, `--json`,
`--dir trader`.

## What it reads and writes

| file / feed | what |
| --- | --- |
| `archives.nseindia.com/content/equities/EQUITY_L.csv` | every NSE-listed equity and its series |
| `archives.nseindia.com/content/equities/sec_list.csv` | price band per symbol |
| `archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv` | delivery % (when published) |
| Yahoo spark and chart (unofficial, can lag) | one year of daily bars per stock |
| `trader/universe.txt` | written by `universe`, read by `daily` |
| `trader/watchlist.json` | the hits, for swing-news and swing-entry |
| `trader/config.json` | optional overrides: `min_price`, `min_traded_value`, `block_bands`, `include_be` |

## The setups

Every rule is checked at the CLOSE of the last final daily bar. Each one
comes with a level: the price a later daily close has to clear for
swing-entry to call the entry.

| setup | rule | level |
| --- | --- | --- |
| `breakout_20d` | close above every close of the 20 sessions before it | that highest close |
| `breakout_52w` | close above every high of the 250 sessions before it (needs a year of bars) | that highest high |
| `bull_flag` | up more than 10 % from 15 to 5 sessions ago, then 5 closes inside a 5 % range | the flag's highest high |
| `reclaim_ma20` | closed under the 20-day average, then closed above it | today's high |
| `pullback_ma50` | 50-day average rising, today's low within 2 % of it, close above it | today's high |
| `oversold` | RSI 14 (Wilder) under 30 | none: watch only |
| `oversold_bounce` | RSI 14 under 30 yesterday, closed up today | today's high |

## When to run it

After the close. NSE's regular session is 09:15 to 15:30 IST; a day's bar
counts only from 15:50 IST (the close plus the delay of free data). Before
that, the scan is as of the previous trading day and says so (`as_of` in
the output). On a weekend or an NSE holiday it uses the last session.

## How to present it

1. Say the date the scan is as of and how many charts it read.
2. List the hits grouped by setup: symbol, close, level, average traded
   value, price band, delivery %.
3. Point out anything that needs care: a band of 10 % (can lock at the
   limit), low delivery % (mostly intraday churn), a level far above the
   close.
4. Never call a hit a buy. Offer the next step: `/swing-news` on the
   hits (results dates and announcements), then `/swing-entry` on the one
   the user picks.

## Notes

- Stage 1 uses closes only, so it is a filter; stage 2 re-checks every
  candidate with real highs, lows and volume.
- Stocks in the 2 % and 5 % price bands are left out by default: they can
  hit the band and freeze, and you may not be able to sell. Change
  `block_bands` in `trader/config.json` to include them.
- Yahoo and NSE's files are free and unofficial. A missing symbol is noted,
  not fatal. Check anything that matters against your broker's chart.
- Not financial advice. The scan cannot see results, news or the future.
