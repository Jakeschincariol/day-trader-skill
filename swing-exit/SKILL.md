---
name: swing-exit
description: >-
  Exit Planner for swing trades on NSE/BSE. Sets the stop, the target and a
  time stop before the entry, so you know how the trade ends before it
  starts. Reads the entry from swing-entry (or a price you give), puts the
  stop at the recent swing low by default (or the trigger day's low, a
  multiple of the daily ATR, a percent, or your price), rounds it DOWN to a
  valid NSE tick, and sets the target at 2R (or 1R, 3R, your price). Turns
  them into GTT OCO values: stop trigger plus a stop limit 1 % lower so a
  normal gap still fills, and the target. Adds a time stop N trading days
  out (default 15), skipping NSE holidays. Refuses a stop at or above the
  entry or closer than half a day's ATR, and says why. Writes
  trader/plan.json for the Time Machine, the Budget Manager and alerts.
  Long side, delivery only. Use when the user says "where's my stop", "set
  my stop and target", "plan the exit", "what's my R", "risk reward", "GTT
  values", "how long do I hold", or right after /swing-entry, before
  /swing-timemachine.
argument-hint: "[--stop swing-low|setup-low|atr:K|pct:X|price:X] [--target 2R|price:X]"
---

# swing-exit

The Exit Planner decides how a trade ends before it starts. The stop is
where the setup has failed. The target is where you take what you came for.
The time stop is when a trade that did neither is no longer the trade you
planned. All three are set BEFORE the entry, written down and handed on, so
nobody decides anything in the middle of a fast move.

This is not financial advice, and it never places an order. The user places
the GTT themselves, from the trade card, after the buy fills. A stop is a
plan, not a guarantee: a stock that gaps below the GTT's limit price leaves
the order unfilled, and the loss can be larger than planned.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan                                  # trader/entry.json: swing-low stop, 2R
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop atr:2 --target 3R --write # -> trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop swing-low:5 --max-hold 10
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol TCS --entry 3412.40 --stop price:3296.10
python3 "${CLAUDE_SKILL_DIR}/exit.py" show                                  # the current trader/plan.json
```

Other flags: `--entry PRICE` (plan ahead while entry.json is still
waiting), `--now "2026-11-18 16:00"` (IST), `--offline PATH`, `--json`,
`--dir trader`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/entry.json` | the trigger and the suggested order (swing-entry) |
| Yahoo daily bars | a year, for the swing low and ATR(14) |
| `trader/config.json` | `stop_method` (swing-low), `target` (2R), `max_hold_days` (15), `gtt_slippage_pct` (1), `tick_schedule` |
| `trader/plan.json` | entry, entry_date, stop and how, GTT stop limit, target, risk per share, reward:risk, time stop date, ATR |

## The stop methods

| method | stop | when |
| --- | --- | --- |
| `swing-low` (default), `swing-low:N` | lowest low of the last N sessions up to the trigger (N = 10) | most setups |
| `setup-low` | the trigger day's low | tight, for strong breakouts |
| `atr:K` | entry - K x ATR(14), daily | volatile stocks; K = 2 is common |
| `pct:X` | X % below the entry | simple |
| `price:X` | your level | a level you know |

Every stop is rounded DOWN to a valid NSE tick (0.01 under Rs 250, 0.05 to
Rs 1,000, 0.10 to Rs 5,000, and so on). The planner refuses a stop that is
not below the entry, or closer than 0.5 x ATR(14), because ordinary daily
noise would take it out.

## The target and the time stop

- `2R` puts the target two times the risk above the entry; `1R`, `3R` and
  `price:X` work too. Rounded to the nearest tick.
- The time stop is the close of the Nth trading day after the entry day
  (NSE holidays skipped). A swing trade that has done nothing in three
  weeks is tying up money that a better setup could use.

## GTT values

The plan writes the numbers for a GTT OCO (one cancels the other), which
most Indian brokers offer for delivery holdings:

- stop leg: trigger at the stop, limit 1 % below it (`gtt_slippage_pct`)
- target leg: trigger and limit at the target

Most brokers only accept a sell GTT once the shares are in your holdings,
so the card says to place it right after the buy fills.

## How to present it

1. Entry, stop (and how it was set), risk per share, target, reward:risk.
2. The GTT values and the time stop date.
3. If refused: the reason, and which method to try instead.
4. Next: `/swing-timemachine` to replay the odds, then `/swing-budget`.

Not financial advice.
