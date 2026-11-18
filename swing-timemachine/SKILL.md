---
name: swing-timemachine
description: >-
  Time Machine for swing trades on NSE/BSE. Replays a planned trade before
  you risk a rupee: 10,000 simulated holds of up to max_hold_days trading
  days, built from the stock's own last 3 years of daily bars in blocks of 5
  sessions (so gap-downs through the stop are in the odds), plus every time
  the same setup fired on this stock in the last 5 years, walked through
  what really happened with the same stop, target and time stop. Prints the
  odds of target first, stop first or time stop, how often the stop gapped,
  the worst loss in R, the average R, the median days held, a fan chart,
  and one plain verdict. Warns when results are due inside the hold. Use
  when the user says "run the time machine", "what are the odds", "replay
  this trade", "backtest this setup", "monte carlo", "how often does this
  hit the target", "is this a coin flip", or after /swing-exit, before
  /swing-budget.
argument-hint: "[run | chart] [--n 10000] [--seed 19]"
---

# swing-timemachine

The Time Machine sits between the plan and the money. swing-exit has set
the entry, the stop, the target and the time stop. Before anything is sized,
this skill asks one question: if the next few weeks look like this stock's
own last three years, how often does the plan hit the target first, the stop
first, or neither? It answers with 10,000 replays and with the real record
of the same setup on the same stock.

It is a simulation built from the stock's own past, not a prediction. This
is not financial advice, and nothing here places an order. A good-looking
replay does not make a trade win; most active traders lose money.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run                  # trader/plan.json, 10,000 replays, seed 19
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --write          # also save trader/timemachine.json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --n 20000 --seed 7 --json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" chart                # ASCII fan of the saved run
```

Other flags: `--now "2026-11-18 16:00"` (IST), `--offline PATH`, `--dir trader`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | entry, stop, target, max hold, setup, stop method (swing-exit) |
| Yahoo daily bars | 5 years for the stock (3 for the simulation, 5 for the history) |
| NSE board meetings (optional `nse` package) | is a results date inside the hold? |
| `trader/timemachine.json` | with `--write`: the plan, the odds, the history, the fan |

## How it works

1. **Simulation.** Each of the 10,000 paths starts at the entry and adds
   one day at a time, each day a real day from the last 756 sessions,
   written as ratios to its previous close (open, high, low, close). Days
   are drawn in blocks of 5 in a row, so streaks and gaps come along.
   Seeded (19 by default) so anyone can repeat the numbers.
2. **History.** For every session in the last 5 years where the setup
   fired on this stock, it buys the next open, sets the stop with the same
   method and the target at the same R, and walks the real bars that
   followed. Overlapping fires all count; it is the setup's record on this
   stock, not a trading account.
3. **Per day, in order:** opened at or below the stop: out at the open (a
   gap through the stop; in real life the GTT's limit may not even fill);
   opened at or above the target: out at the open; touched the stop: out at
   the stop (also when the target was touched the same day: the cautious
   reading); touched the target: out at the target; after the last day: out
   at that close (the time stop).

## The verdict

- **edge in its own history**: both the replay and the record average more
  than +0.2 R.
- **close to a coin flip**: both between -0.2 R and +0.2 R.
- **history is against it**: either one below -0.2 R.

Say it plainly. A coin flip is a useful answer: it is the point of looking
before you risk money.

## How to present it

1. The odds: target first, stop first, time stop.
2. The gap risk: how often the stop was gapped and the worst R.
3. The history line and the verdict.
4. If results are due inside the hold, say the odds do not include a
   results move, and suggest a shorter hold or waiting.
5. Next: `/swing-budget` to size it.

## Limits

The future can do what the last three years never did: results, a block
deal, a regulatory order, a market-wide fall. Daily bars cannot tell
whether the stop or the target came first inside one day; the tool assumes
the stop. Not financial advice.
