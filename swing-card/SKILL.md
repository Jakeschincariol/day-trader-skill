---
name: swing-card
description: >-
  Trade Card for swing trades on NSE/BSE: the last step, and the only
  output meant for your broker. Prints one plain card per proposal that
  passed /swing-risk today: BUY symbol, exchange, CNC, quantity, the limit
  or SL-buy price and the session it is for, the GTT OCO stop trigger and
  limit and the target, the risk at the stop, estimated charges,
  reward:risk and the time stop date. You type it into your own broker app
  (Zerodha, Groww, Upstox, Dhan, Angel One, ICICI Direct, any). This skill
  never talks to a broker and never places an order. Then it keeps your
  journal: record the fill, record the exit, and see the running record
  (win rate, average R, P&L after charges). Use when the user says "show me
  the trade", "give me the order", "what do I enter in Zerodha", "trade
  card", "I bought it", "it filled at", "I sold", "my stop hit", "close
  TCS", "show my journal", "how am I doing", or after /swing-risk.
argument-hint: "[show | record | close | log]"
---

# swing-card

The Trade Card is where the pack hands over to the user. Everything before
it was analysis. The card is the order, written out so the user can type it
into their own broker without doing any arithmetic, IF they decide yes.

This is not financial advice. Nothing in this pack ever places an order, and
this skill does not touch the network at all: it reads the JSON files in
`trader/` and prints. Claude never logs in to a broker, never asks for
broker credentials, and never says a trade is a good idea.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

Symbols with `&` (M&M) must be single-quoted on the command line, e.g. `'M&M'` or
`--symbols 'TCS,M&M'`: an unquoted `&` makes the shell cut the symbol and run the rest
in the background.

```bash
python3 "${CLAUDE_SKILL_DIR}/card.py" show                                   # cards that passed today
python3 "${CLAUDE_SKILL_DIR}/card.py" record --id TCS-2026-11-19 --qty 29 --price 3412.40
python3 "${CLAUDE_SKILL_DIR}/card.py" close --symbol TCS --price 3645 --reason target
python3 "${CLAUDE_SKILL_DIR}/card.py" close --symbol TCS --price 3300 --qty 10 --reason manual   # part
python3 "${CLAUDE_SKILL_DIR}/card.py" log                                    # the journal
```

Other flags: `--date YYYY-MM-DD` (record / close), `--now`, `--json`, `--dir trader`.

## The card

```
BUY TCS (NSE) · CNC · 29 shares · LIMIT ₹3,412.40 · valid 2026-11-19
GTT OCO  stop trigger ₹3,296.10 / limit ₹3,263.10
         target trigger ₹3,645.00 / limit ₹3,645.00
Risk at stop ₹3,372.70 + charges ~₹230 · R:R 2.0 · time stop 2026-12-10
Place the GTT after the buy fills: most brokers need the shares in your holdings first.
```

A WARN verdict prints its warnings above the card. A BLOCK, a proposal
changed since the risk check, or one not checked today gets no card, only
the reason.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | proposals (swing-budget) |
| `trader/state/risk.json` | today's verdicts and fingerprints (swing-risk) |
| `trader/positions.json` | open positions: `record` adds, `close` removes |
| `trader/journal.json` | closed trades: entry, exit, reason, R, P&L after estimated charges |

## How to walk the user through it

1. Show the card exactly as printed. Do not round, restate or "improve"
   the numbers: they are on valid NSE ticks.
2. Remind them: it is their decision, in their own broker app. Buy first
   (CNC, the limit price, for the session shown). After it fills, place the
   GTT OCO with the stop trigger and limit and the target.
3. When they say it filled, run `record` with the real quantity and price.
4. When it exits (stop, target, time stop or by hand), run `close` with the
   real price and reason, and remind them to cancel any leftover GTT.
5. `log` shows the record. Be plain about losses; they are part of it.

## If the order did not fill

A limit buy for one session that did not fill is simply gone. Do not chase
it: run `/swing-entry` again after the next close; the setup may be stale.
Not financial advice.
