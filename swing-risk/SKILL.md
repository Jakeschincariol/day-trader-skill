---
name: swing-risk
description: >-
  Risk Manager for swing trades on NSE/BSE. Checks every proposal from
  swing-budget against your limits before it can become a trade card, and
  prints PASS, WARN or BLOCK with the reasons. Blocks: no GTT stop, anything
  but a CNC (delivery) buy, prices off the NSE tick, a loss at the stop over
  your risk per trade, reward:risk under your minimum, too many open
  positions, portfolio heat (open risk to stops plus this trade) over your
  limit, the position cap, the cash buffer, your blocked list, and stocks
  in the 2 % or 5 % price bands. Warns on the 10 % band, results due inside
  the planned hold (or blocks, if you choose), a position over 1 % of the
  day's average volume, and missing data. Records the verdicts so
  swing-card only shows what passed. Use when the user says "check my
  trade", "is this safe", "risk check", "does this break my rules", "how
  much am I risking in total", "can I take this trade", or before
  /swing-card, always.
argument-hint: "[--no-write]"
---

# swing-risk

The Risk Manager is the gate between a proposal and a trade card. Every
proposal written by swing-budget passes through it. A BLOCK is final for
that proposal: swing-card will not show it, and Claude does not help place
it. Most people who trade actively lose money. These limits keep each loss,
and the sum of open losses, small. They do not make a trade win.

This is not financial advice, and this pack never places an
order: the user places every order themselves, after they decide yes.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                           # trader/orders.json -> trader/state/risk.json
python3 "${CLAUDE_SKILL_DIR}/check.py" --json
python3 "${CLAUDE_SKILL_DIR}/check.py" --no-write                # look without recording
```

Other flags: `--now "2026-11-18 16:00"` (IST), `--offline PATH`, `--dir trader`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposals (swing-budget) |
| `trader/positions.json` | open positions (swing-card), for heat, count and cash |
| `trader/config.json` | the limits below |
| `trader/results.json` | optional, by hand: `{"TCS": ["2027-01-09"]}` results dates |
| NSE `sec_list.csv` | price band per stock |
| NSE board meetings (optional `nse` package) | results dates |
| Yahoo daily bars | 20-day average volume |
| `trader/state/risk.json` | the verdicts, with a fingerprint of each proposal |

## The limits (trader/config.json)

| key | default | rule |
| --- | --- | --- |
| `risk_per_trade_pct` | 1.0 | loss at the stop <= this % of capital (5 % tolerance) |
| `min_reward_risk` | 1.5 | target distance / stop distance |
| `max_open_positions` | 5 | open swing positions |
| `max_heat_pct` | 5.0 | sum of every open position's risk to its stop, plus this one |
| `max_position_pct` | 20.0 | cost of one position |
| `cash_buffer_pct` | 10.0 | cash never spent |
| `blocked` | [] | symbols you never trade |
| `block_bands` / `warn_bands` | ["2","5"] / ["10"] | NSE price bands |
| `block_on_results` | false | true: block a trade with results inside the hold |

No margin, no MTF, no F&O, no short selling: only CNC buys pass.

## How to present it

1. One line per proposal: PASS, WARN or BLOCK.
2. Every reason, in plain words.
3. For WARN, ask the user to read the warnings before going on. Results
   inside the hold is the big one: a results day can gap a stock straight
   through the stop.
4. For BLOCK, say which rule and what would have to change. Do not look for
   a way around a block.
5. Next: `/swing-card` for anything that passed or warned.

Without the optional `nse` package the results check is off and every
proposal WARNs about it; `pip install -r requirements-nse.txt`, or keep
`trader/results.json` by hand. Not financial advice.
