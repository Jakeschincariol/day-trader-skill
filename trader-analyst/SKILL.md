---
name: trader-analyst
description: >-
  Quarterly Results Analyst for the NSE. Lays out a company's reported
  quarters side by side: revenue, operating income, net income, diluted EPS,
  operating and net margins, growth against the same quarter a year earlier,
  and the last four quarters in total, in rupees crore. Numbers come from
  Yahoo Finance's fundamentals time series, with gaps shown as gaps (nothing
  is filled in) and a company that reports in dollars labelled as dollars.
  Use when the user says "how did TCS do last quarter", "show me the
  quarterly results", "revenue and profit trend", "is the profit growing",
  "compare these results", "results summary", or after /trader-news shows a
  company has filed results.
argument-hint: "[symbols]"
---

# trader-analyst

Numbers, laid out so you can read a company's last quarters in ten seconds.
It does not say whether a stock is a buy. It reports what the company reported.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE TCS INFY --quarters 8
python3 "${CLAUDE_SKILL_DIR}/facts.py" TCS --json
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE TCS --metrics trader/metrics.json   # one row per ticker, for notes or a sheet
```

## What it prints

```
TCS (NSE), quarterly results, INR crore (1 crore = 10 million) (Yahoo Finance, unofficial)
quarter end      revenue      YoY   net income      YoY     EPS  op mgn net mgn
2026-06-30        72,275    13.9%       13,349     4.6%   36.90   24.1%   18.5%
2026-09-30        73,188        -       13,884        -   38.37   24.0%   19.0%
Last four quarters (through 2026-09-30): revenue 283,248 cr, net income 51,608 cr, EPS 142.66.
```

(Run on 2026-11-06; the full table has up to the last five quarters Yahoo holds.)

## How the quarters are built, and what is missing

- A quarter is a value Yahoo marks as a 3-month period, keyed by its period-end date.
- **Nothing is filled in.** Yahoo's free feed holds only the latest few quarters and sometimes skips
  one: for TCS and RELIANCE on 2026-11-06 it had no 2025-09-30 quarter. A growth figure needs both
  the quarter and the same quarter a year earlier, so most rows show "-" for YoY. The tool prints
  every MISSING quarter and every blank YoY and why.
- The four-quarter total appears only when the latest four quarters are consecutive.
- **Consolidated vs standalone.** Yahoo mostly reports consolidated figures; the tool cannot tell
  which a quarter is. For a holding company the two can differ a lot.
- **Currency.** Some NSE companies report in dollars (Infosys shows USD in this feed). The tool then labels
  the table "USD million: NOT rupees" and does not convert. EPS is in the same currency.
- Banks and NBFCs report "revenue" differently, so their margins are not comparable and may be blank.
- When net income is above operating income, gains or tax items outside the business are inside it.
  The tool says so. Read the filing.
- Yahoo can lag a fresh filing by days. For a quarter that matters, open the filing that
  `/trader-news` links and read the numbers there.

## Steps

1. Run it for the companies in question (or the tickers on `trader/watchlist.json`).
2. Write the summary: one line on the latest quarter (revenue, profit, EPS, growth where it exists),
   one on margins, one on anything unusual (a one-off, a missing quarter, a currency), and say what the
   data does not have.
3. If results fall inside the planned trade (due today, or an overnight hold), say it before
   `/trader-exit` sets the stop: a stop does not protect against a gap.

## What it never does

- Never says a stock is cheap, expensive, a buy or a sell.
- Never invents a number or estimates a quarter it does not have.
- Never converts currencies.

## Safety

- Education and tooling, not financial advice. This skill only reads public data.
- No skill in this pack places an order. You place every order yourself in Zerodha Kite.
