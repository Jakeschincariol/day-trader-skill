---
name: trader-budget
description: >-
  Budget Manager. Sizes every position to your budget and your max loss per
  trade. Reads the trade plan from trader-exit (entry, stop, target), finds
  the whole shares that fit inside four limits (max loss per trade, position
  cap, max order, cash after your buffer), says which limit decided it, and
  writes ONE bracket order (entry, stop-loss, take-profit) to
  trader/orders.json in a plain order shape (Alpaca-style field names) that trader-broker turns into a Kite form. A stop
  too far away for your max loss is a plain refusal, not a smaller order.
  Nothing is placed. Use when the user says "how many shares", "size this
  trade", "how much should I buy", "I have ₹5,000", "I only want to risk ₹50
  a trade", "set my rules", "keep 10% in cash", or after /trader-exit writes
  a plan.
argument-hint: "[budget in rupees]"
---

# trader-budget

The Budget Manager turns a plan ("buy RELIANCE at 1311.90, stop 1300.80") into an
exact order ("buy 8 shares"), inside rules the user sets once. The stop
decides the size: the further away the stop, the fewer shares. It writes a
proposal only. trader-risk checks it and trader-broker prints the Kite form
no. Day trading loses most people money. Sizing to a max loss keeps each
loss small; it does not make a trade win.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py"                        # trader/plan.json + trader/config.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --write                # write trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit --write        # a limit order at the plan's entry
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit 1311.00 --json  # a limit order at 1311.00
python3 "${CLAUDE_SKILL_DIR}/size.py" --weights RELIANCE=40,TCS=60 --config split.json   # weights mode, below
```

`--now "2026-11-06 10:15"` pins the clock (IST). A plan for
another day is refused: make a new one with trader-exit.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/config.json` | the rules (start from `config.example.json` in this folder) |
| `trader/plan.json` | the trade: entry, stop, target, setup, flat-by time (trader-exit writes it) |
| `trader/prices.json` | optional: a fresh price above the plan's entry means a bigger risk (trader-alerts writes it) |
| `trader/portfolio.json` | optional: its cash caps the size (trader-broker keeps it) |
| `trader/orders.json` | the one proposed bracket order it writes with `--write` |

## Step 1: set the rules once

If `trader/config.json` does not exist, copy `config.example.json` into
`trader/config.json` and ask the user for each value in plain words:

- **budget**: how much money this is for. Only money they can afford to lose.
- **cash_buffer_pct**: how much always stays in cash (default 10).
- **max_loss_per_trade_inr**: the most one trade may lose if the stop fills at the stop (default 50).
- **max_position_pct**, **max_order_inr**, **min_order_inr**: the biggest position (75% of the
  budget), the biggest order (₹4,000) and the smallest order (₹5).
- The day limits trader-risk enforces: **max_daily_loss_inr** (150), **max_trades_per_day** (3),
  **min_reward_risk** (1.0), **require_stop** (true), **no_entries_before** / **no_entries_after**
  ("09:30" / "15:00") and **flat_by** ("15:10"), all IST.
- **blocked**: tickers they never want to trade.
- There is no paper account on Kite: start with a small budget and a small max loss.

## Step 2: size the trade

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py" --write
```

Whole shares only: the NSE has no fractional shares. The size is
the smallest of four limits:

| limit | shares |
| --- | --- |
| max loss | `max_loss_per_trade_inr` / risk a share (entry minus stop) |
| position cap | budget x `max_position_pct` / entry |
| max order | `max_order_inr` / entry |
| cash | (budget minus the cash buffer) / entry, never more than the cash in `trader/portfolio.json` |

The entry it sizes at: the limit price with `--limit`. For a market order, the
plan's entry, or the price in `trader/prices.json` if it is fresh (under 15
minutes old) and higher. A price that ran up since the plan means a bigger
loss at the same stop, so fewer shares. A lower price never shrinks the risk.

It refuses, and writes no order, when: the size is zero shares, the order is
under the minimum, reward:risk is under `min_reward_risk`, the stop is not
below the entry, the target is not above it (the move already happened), the
plan is for another day, the ticker is blocked, or the plan is a short. Say
the reason to the user in one line.

## Step 3: show the user

Show the four limits, which one decided the size, the shares, the rupees
and the max loss at the stop. Say plainly that a stop is an order, not a
promise: in a fast market it can fill below the stop. Then hand over to
`/trader-risk`.

## Example: a live run on the NSE

RELIANCE, Friday 2026-11-06. Opening-range breakout: entry 1311.90 at 9:50 AM,
stop 1300.80 (the opening-range midpoint), target 1323.00 (1R). Risk 11.10 a
share. The example config: ₹1,00,000 budget, 10% cash buffer, ₹500 max loss per trade.

| limit | the math | shares |
| --- | --- | --- |
| max loss | ₹500 / 11.10 | **45 (decides it)** |
| position cap | 75% of ₹100,000 = ₹75,000 / 1311.90 | 57 |
| max order | ₹75,000 / 1311.90 | 57 |
| cash | ₹100,000 minus ₹10,000 = ₹90,000 / 1311.90 | 68 |

45 shares = ₹59,035.50. Max loss at the stop: 45 x 11.10 = ₹499.50. It writes:

```json
{"symbol": "RELIANCE", "side": "buy", "qty": "45", "type": "market", "time_in_force": "day",
 "order_class": "bracket", "take_profit_limit_price": "1323.00", "stop_loss_stop_price": "1300.80",
 "why": "opening-range breakout on RELIANCE: 45 shares, bound by your ₹500 max loss per trade (45 x 11.10 = ₹499.50 at the stop)",
 "plan": {"entry": 1311.9, "stop": 1300.8, "target": 1323.0, "risk_per_share": 11.1, "max_loss": 499.5,
          "setup": "orb", "entry_time": "9:50 AM", "flat_by": "15:10"}}
```

`order_class: bracket` is this pack's internal shape. Kite has no bracket order:
trader-broker turns it into one Kite buy form plus two sell forms (stop-loss and
target) for you to place. `why` and `plan` are notes for trader-risk and
trader-broker. Prices are multiples of the NSE tick (0.05).

The budget counts the full price of the shares against your cash. Zerodha's MIS
margin would let you hold the same shares on less money; this tool does not use
it, so its sizes are conservative on purpose.

## Weights mode (kept from v1)

`--weights RELIANCE=60,TCS=40` or `--targets FILE` (`targets.example.json`
here) splits a budget across a list by weight: the cash buffer comes off the
top, weights are renormalised to 100, any stock over `max_position_pct` is
pinned at the cap and its excess shared out, slices under the minimum order
are dropped, and amounts round to whole rupees so nothing is left idle by
accident. The example file (five stocks at 20 % each) shows the shape; it is not a recommendation.
With `"fractional": false` (the example config) it buys whole shares and
needs prices (`--prices trader/prices.json`). These are plain buys with no stop: trader-risk blocks them while
`require_stop` is true and counts each one against `max_trades_per_day`. Use
a separate config (`--config`) for a long-term split.

## Rules

- Proposals only. This skill never calls a broker tool.
- Never size money the user has not said is for this. Ask for the budget and the max loss.
- Every number comes from the config, the plan or the prices. Nothing is guessed.
- No projections: never say what a trade will make. A target is a plan, not a forecast.
- Free Yahoo prices are unofficial and can lag. The price Kite fills at is the one that counts.

## What it never does

It never places, approves or schedules an order, never raises a limit on its
own, never shrinks a stop to fit more shares, and never sizes options,
margin or short positions.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- No skill in this pack places an order. You place every order yourself in Zerodha Kite; trader-broker
  only prints the ticket for an order that trader-risk passed today.
- No margin, short selling or leverage unless the config allows it.
- Kite keys live in environment variables, never in the chat.
