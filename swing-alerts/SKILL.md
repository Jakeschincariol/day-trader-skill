---
name: swing-alerts
description: >-
  Price Alerts for open swing positions on NSE/BSE. After the close, checks
  every position in trader/positions.json against the day's bar and rings
  once for each thing that matters: the stock gapped through the stop, the
  low hit the stop (check the GTT sold), the low went under the GTT's limit
  (the stop may not have filled), the high hit the target, the time stop
  date has come, results are due next session, a dividend, split or bonus
  goes ex next session, or NSE changed the price band. Also tells you
  whether NSE is open (IST, NSE holidays) and fetches delayed quotes into
  trader/prices.json. Use when the user says "check my positions", "did my
  stop hit", "anything I need to know about my trades", "is the market open
  today", "is tomorrow a holiday", "get me a price", "watch my trade", or
  daily after 15:50 IST.
argument-hint: "[check | clock | quote SYMBOLS]"
---

# swing-alerts

Price Alerts watches the open trades so the user does not have to stare at
a chart for three weeks. It checks once a day, after the close, because a
swing plan lives on daily closes and the GTT at the broker does the actual
selling.

An alert is information, never an order. This pack never places,
changes or cancels an order. This is not financial advice.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

Symbols with `&` (M&M) must be single-quoted on the command line, e.g. `'M&M'` or
`--symbols 'TCS,M&M'`: an unquoted `&` makes the shell cut the symbol and run the rest
in the background.

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                    # after 15:50 IST; exit 0 = something rang
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                    # NSE open or closed, next session
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote TCS 'M&M' --write  # -> trader/prices.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote --holdings --write # positions + plan
```

Other flags: `--now "2026-11-18 16:00"` (IST), `--offline PATH`, `--json`,
`--dir trader`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/positions.json` | open positions with stop, GTT limit, target, time stop (swing-card `record`) |
| Yahoo daily bars | the day's open, high, low, close |
| NSE `sec_list.csv` | price bands |
| NSE board meetings and corporate actions (optional `nse` package) | results and ex-dates next session |
| `trader/state/alerts.json` | alerts already rung, last known bands |
| `trader/prices.json` | `quote --write`: last price and previous close |

## The alerts

| kind | when | what the user should do |
| --- | --- | --- |
| `gap_through` | opened below the stop | check the GTT; the fill may be far below the stop |
| `stop_touched` | low reached the stop | check that the GTT sold; record the exit with swing-card |
| `below_gtt_limit` | low went under the GTT's limit price | the stop order may NOT have filled: check holdings now |
| `target_touched` | high reached the target | check that the GTT sold; record the exit |
| `time_stop` | the time stop date has come | the plan says sell at the close |
| `results_tomorrow` | results next session | expect a gap; decide before the open |
| `ex_date_tomorrow` | dividend / split / bonus ex next session | the price drop is mechanical; adjust the GTT if needed |
| `band_changed` | NSE moved it to another band | a tighter band can lock the stock |

## Run it every day

Schedule `check` for about 16:00 IST on trading days (Claude Code's
`/schedule`, or cron). Before 15:50 it reads the previous session and says
so. On holidays `clock` says which holiday it is (from
`india/holidays.json`; refresh it each year with
`python3 -m india.market refresh-holidays`).

## How to present it

1. Say the date of the close it read.
2. Each alert in one line, most urgent first (`below_gtt_limit`,
   `gap_through`, then the rest).
3. When an exit happened, ask for the real fill and record it with
   `/swing-card close`.

Free data is delayed and unofficial: the broker's holdings and order book
are the truth. Not financial advice.
