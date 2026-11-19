---
name: swing-entry
description: >-
  Entry Timer for swing trades on NSE/BSE. Takes a setup from swing-scanner
  (or a level you give it) and calls the entry on the first completed DAILY
  bar that closes above the level, with an optional volume check. Says
  waiting and how far, triggered with the date and the close, stale (a
  late entry), or failed (closed back under), and suggests the order for
  the next session on valid NSE ticks: a limit buy at the trigger close plus
  a small buffer, or a stop-limit buy above the trigger bar's high. Run it
  after 15:50 IST; --pre-close reads today's forming bar between 15:00 and
  15:30 and marks the answer provisional. Writes trader/entry.json for
  swing-exit. Long side only, delivery only. Use when the user says "has it
  broken out", "did TCS close above", "time my entry", "is it a buy
  tomorrow", "check my watchlist", "entry signal", or after /swing-news,
  before /swing-exit.
argument-hint: "[SYMBOL] [--setup NAME | --level PRICE]"
---

# swing-entry

The Entry Timer turns a setup into one moment: the daily bar that confirms
it. A price that pokes above the level during the day is not an entry. A day
that CLOSES above it is. Then it says the date and the close, suggests the
order for the next session, writes it down for the Exit Planner, and stops.

This is not financial advice, and it never places an order. The pack ends in
a trade card the user types into their own broker, after they decide yes.
A clean signal does not make a trade win; most active traders lose money.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

Symbols with `&` (M&M) must be single-quoted on the command line, e.g. `'M&M'` or
`--symbols 'TCS,M&M'`: an unquoted `&` makes the shell cut the symbol and run the rest
in the background.

```bash
python3 "${CLAUDE_SKILL_DIR}/entry.py" check TCS --setup breakout_20d          # level from the setup
python3 "${CLAUDE_SKILL_DIR}/entry.py" check TCS --setup bull_flag --write     # -> trader/entry.json
python3 "${CLAUDE_SKILL_DIR}/entry.py" check 'M&M' --level 3400                # your own level
python3 "${CLAUDE_SKILL_DIR}/entry.py" check TCS --level 3400 --pre-close      # 15:00-15:30 IST, provisional
python3 "${CLAUDE_SKILL_DIR}/entry.py" check TCS --level 3400 --entry-style sl-buy
python3 "${CLAUDE_SKILL_DIR}/entry.py" watchlist                               # every hit in trader/watchlist.json
```

Other flags: `--since YYYY-MM-DD` (only closes after this date count),
`--min-volume-x 1.5` (the trigger close must come on at least 1.5x the
20-day average volume), `--now "2026-11-18 16:00"` (IST), `--offline PATH`,
`--json`, `--dir trader`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/watchlist.json` | the scanner's hits (for `watchlist`) |
| Yahoo daily bars | one year, for the stock |
| `trader/config.json` | `entry_style` (limit or sl-buy), `entry_limit_buffer_pct` (0.5) |
| `trader/entry.json` | written with `--write`: symbol, setup, level, state, trigger date / close / high, the suggested order |

## The states

| state | means | what to say |
| --- | --- | --- |
| waiting | no daily close above the level yet | how far the last close is from the level |
| triggered | the first close above the level | the date, the close, the order for the next session |
| stale | triggered more than 2 sessions ago and now more than 3 % above the level | a late entry is a different trade: new level, new stop |
| failed | closed above, then closed back under | the setup failed; do not chase it |

A trigger day that closes far above the level is still triggered, but the
reason says it is extended: the stop will be further away, so the position
will be smaller.

The suggested order is always for the session after the latest completed
bar (or today, with `--pre-close`). If the trigger was a session or two
ago, the order is priced off the latest close and the reason says how late
it is. swing-risk blocks any order whose session has already passed.

## The suggested order

- **limit** (default): buy at the trigger close + 0.5 %, rounded UP to a
  valid NSE tick, good for the next session (`valid_for`). If the stock
  opens far above it, the order simply does not fill. That is fine.
- **sl-buy**: a stop-limit buy that triggers one tick above the trigger
  bar's high, limit 0.5 % above the trigger. Only buys if the next session
  trades above the high.

Product is always CNC (delivery). No intraday, no margin, no F&O.

## When to run it

After 15:50 IST, once the day's bar is final. Before that the tool uses the
previous session and says so. `--pre-close` exists for people who want to
buy in the last minutes of the session: it reads today's forming bar
between 15:00 and 15:30 IST and marks the answer PROVISIONAL, because the
close can still change.

## How to present it

1. The state, in one line, with the date and the close.
2. If triggered: the suggested order for the next session, in rupees.
3. If stale or failed: say plainly not to chase it.
4. Next step: `/swing-exit` to set the stop and target BEFORE sizing or
   placing anything.

Not financial advice. Free data can lag; check the close on your broker's
chart before acting.
