---
name: trader-deals
description: >-
  Bulk and Block Deals tracker for the NSE, the India stand-in for the US
  Congress-trades skill. Reads NSE's own daily bulk-deal and block-deal files,
  names the client who bought or sold, the quantity, the price and the value
  in crore rupees, nets buys against sells per stock, filters to your
  watchlist, and can keep a history file because NSE publishes only the
  latest session. Use when the user says "any bulk deals", "block deals
  today", "who bought RELIANCE", "big buyers", "what did the funds trade",
  "institutional activity", or after /trader-scanner finds a stock moving on
  volume.
argument-hint: "[symbols]"
---

# trader-deals

Large trades on the NSE must be disclosed, and the exchange publishes who
traded. This skill reads those daily files and lays them out. It shows who
traded and at what price. It does not show why, and one day's seller is not
tomorrow's signal.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/deals.py"                              # every deal in the latest files
python3 "${CLAUDE_SKILL_DIR}/deals.py" --symbols RELIANCE TCS
python3 "${CLAUDE_SKILL_DIR}/deals.py" --min-value-cr 5 --json
python3 "${CLAUDE_SKILL_DIR}/deals.py" --append trader/state/deals.jsonl   # keep a history, one row once
```

## What it reads

| file | what |
| --- | --- |
| `archives.nseindia.com/content/equities/bulk.csv` | bulk deals of the latest session |
| `nsearchives.nseindia.com/content/equities/block.csv` | block deals of the latest session ("NO RECORDS" on a quiet day) |

No key, no login. Each file holds one trading day, so run it every evening if you want a history.

## Reading it

- **Bulk deals** are large day totals a buyer or seller must disclose; **block deals** are single large trades.
- Many bulk rows are the same client buying and selling the same quantity on the same day (an intraday
  round trip). They net to about zero and say little. The "Net by stock" lines help you see that.
- A big net buyer is a fact about one day. Do not call it a signal, and do not say what the stock will do.

## Steps

1. Run it for the watchlist symbols (or all). Tell the user the date of the files, the biggest deals by
   value, and the net by stock.
2. If a watchlist stock appears, say who, which side, how big, and that it is public data and not why.
3. Hand a chosen stock on to `/trader-news` and `/trader-entry`.

## What it never does

It never says a deal is a reason to buy or sell, never infers intent, and never places an order.

## Not built (and why)

SEBI insider-trading (PIT) disclosures also exist. NSE's insider feed
(`.../RSS/Insider_Trading.xml`) held only 20 items, some months old, on 2026-11-06, and the filings are
heavy XBRL files, so this skill does not read them. Ask before relying on a feed that thin.

## Safety

- Public data, not inside information. Education and tooling, not financial advice.
- No skill in this pack places an order. You place every order yourself in Zerodha Kite.
