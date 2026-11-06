---
name: trader-alerts
description: >-
  Price Alerts. Rings when a price, a stop or the opening bell hits. Turns
  the trade plan into three alerts in one go (the stop, the target and "flat
  by close" at your flat-by time), plus above / below / stop / target levels,
  percent moves from the previous close, any time of day, and the NSE
  opening bell, each ringing once so you are not spammed. Knows NSE hours
  with the 2026 holidays, works out
  IST itself, fetches free delayed quotes (Yahoo chart JSON
  CSV) one ticker at a time, and writes trader/prices.json for sizing and the
  risk check. Use when the user says "alert me when", "tell me if RELIANCE hits",
  "watch my stop", "watch my trade", "remind me to close by 3:10", "is the
  market open", "when does the market open", "get me a price", or right
  after /trader-exit writes a plan.
argument-hint: "[ticker] [price]"
---

# trader-alerts

Price Alerts watches the numbers so the user does not have to stare at a
chart. An alert is information, never an order: when a stop alert rings,
nothing is sold by this skill. With a bracket order the stop-loss and the
take-profit already sit at the broker and do the work; the alerts tell the
user what happened and when it is time to be flat.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                          # NSE open or closed, next open
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --from-plan                # stop, target, flat by close from trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --opening-bell
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --stop 1300.80
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --target 1323.00
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --at 15:10 --label "flat by 15:10"
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol TCS --pct 3
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                          # exit 0 = something rang
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote RELIANCE --write             # -> trader/prices.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote --holdings --write       # portfolio + plan tickers
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list
python3 "${CLAUDE_SKILL_DIR}/alerts.py" reset reliance-plan-stop
```

`--now "2026-11-06 15:10"` pins the clock (IST); `--offline DIR`
reads saved quote files instead of the network.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | the trade from trader-exit, for `add --from-plan` |
| `trader/alerts.json` | the rules (`alerts.example.json` in this folder) |
| `trader/state/alerts.json` | which rules rang and when, so each rings once |
| `trader/prices.json` | the latest quotes, merged in, for trader-budget and trader-risk |
| `trader/portfolio.json` | the tickers held, for `quote --holdings` |

## Rule types

| type | rings when | rings again |
| --- | --- | --- |
| `above` / `target` | price at or above `price` | after `reset`, or on its own if `"rearm": true` and the price fell back |
| `below` / `stop` | price at or below `price` | same |
| `pct_move` | moved `pct` percent from the previous close (or `ref`), optional `direction` up or down | once per day at most |
| `time` | the IST clock passed `at` ("15:10") on a trading day | once per trading day |
| `opening_bell` | the NSE is open | once per trading day |

A rule with `"date"` is watched on that IST date only; `--from-plan`
rules carry the plan's date, so yesterday's stop never rings today. A `time`
rule with `"before_close": true` would move earlier on an early close; the NSE has none, so it rings at the time you set.

## Quotes

- `yahoo` (default): `query2.finance.yahoo.com/v8/finance/chart/<SYMBOL>.NS`, an
  unofficial free JSON endpoint, one request per ticker, half a second apart.
  On a 429 it waits and tries once more; on a 429 or a 5xx after that it
  tries `query1`. It identifies itself as `day-trader-skill/2.0`.
- Free quotes are unofficial, delayed and can lag. They are fine for alerts
  and for checking a size, not for timing an order. The broker's price is the
  one that fills. Each price in `trader/prices.json` keeps its quote time, and
  trader-risk only uses one under 15 minutes old.
- If Yahoo is down, read the price in Kite and write it into
  `trader/prices.json` as `{"as_of": "...Z", "prices": {"RELIANCE": 1320.00}}`.

## The NSE clock

Regular session 9:15 a.m. to 3:30 p.m. IST, closed on weekends and on the
sixteen 2026 weekday holidays (Jan 15, Jan 26, Mar 3, Mar 26, Mar 31, Apr 3,
Apr 14, May 1, May 28, Jun 26, Sep 14, Oct 2, Oct 20, Nov 10, Nov 24, Dec 25),
as listed by brokers from NSE's circular (read 2026-11-06). The 2027 list is
not published yet: the tool says "holiday list unknown" beyond 2026 instead of
guessing. India has no daylight saving, so IST is UTC+5:30 all year. The Diwali
Muhurat evening session is not modelled. Check nseindia.com before a day you
care about.

## Steps

1. Right after trader-exit writes the plan, run `add --from-plan`. Confirm
   the three alerts back to the user: the stop, the target and the flat-by time.
2. Run `check` while the trade is open: every few minutes from a Claude
   scheduled task or `/loop`. Each run fetches only the tickers in today's
   rules and rings each alert once. A check reads the latest delayed quote;
   it is not a live feed, and a price can pass a level between two checks.
3. Tell the user what rang in one line each. A stop or target alert means the
   Kite order has probably filled: check the Kite Positions tab and record the
   fill with trader-broker. "Flat by close" means close anything still open:
   trader-broker `flatten`, then trader-risk, then you place it in Kite. Never act
   for them.

## Example: a live run on the NSE

RELIANCE, Friday 2026-11-06: entry 1311.90 at 9:50 AM, stop 1300.80, target
1323.00, flat by 15:10. `add --from-plan` writes `reliance-plan-stop`,
`reliance-plan-target` and `reliance-flat-by` for that day. `alerts.py clock` at 10:53:

```
IST 2026-11-06 10:53 (Friday): NSE OPEN, regular session.
Today's session: 09:15 to 15:30.
```

and on Tuesday 2026-11-10: `NSE closed, NSE holiday: Diwali-Balipratipada.
Next open: 2026-11-11 09:15 IST.` A `check` rings once per rule: at 15:10 the
"flat by close" alert says to close anything still open with trader-broker
`flatten`. The plan's three alerts carry the plan's date, so they are not
watched the next day; `add --opening-bell` rings at 9:15.

## Rules

- An alert is a fact about a price or the clock. Say it as a fact.
- Never present a quote as live. Free quotes are delayed and unofficial.
- Confirm every new rule back to the user: ticker, type, level, day.

## What it never does

It never places, cancels or changes an order, never claims a quote is
live, and never predicts where a price is going.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- No skill in this pack places an order. You place every order yourself in Zerodha Kite; trader-broker
  only prints the ticket for an order that trader-risk passed today.
- No margin, short selling or leverage unless the config allows it.
- Kite keys live in environment variables, never in the chat.
