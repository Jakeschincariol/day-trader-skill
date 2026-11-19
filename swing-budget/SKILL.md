---
name: swing-budget
description: >-
  Budget Manager for swing trades in rupees. Sizes every position to your
  capital and your max loss per trade: reads the plan from swing-exit
  (entry, stop, GTT limit, target), finds the whole shares that fit inside
  three limits (risk per trade, default 1 % of capital; position cap,
  default 20 %; cash after a 10 % buffer and your open positions), says
  which limit decided it, adds an estimate of delivery charges (STT, stamp
  duty, exchange and SEBI fees, GST, DP charge) and the loss if a gap fills
  only at the GTT limit, and writes ONE proposal to trader/orders.json: a
  CNC buy plus its GTT OCO. A stop too far away for your risk is a plain
  refusal, not a smaller order. Nothing is placed. Use when the user says
  "how many shares", "size this trade", "how much should I buy", "I have 5
  lakh", "I only want to risk Rs 2,000 a trade", "set my rules", "keep 10 %
  in cash", or after /swing-timemachine.
argument-hint: "[--capital RUPEES] [--risk-pct 1]"
---

# swing-budget

The Budget Manager turns a plan ("buy TCS at ₹3,412.40, stop ₹3,296.10")
into an exact quantity ("29 shares"), inside rules the user sets once. The
stop decides the size: the further away the stop, the fewer shares. It
writes a proposal only. swing-risk checks it, and swing-card prints it for
the user to place themselves.

This is not financial advice, and this pack never places an order. Sizing
to a max loss keeps each loss small; it does not make a trade win.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py"                          # trader/plan.json + config + positions
python3 "${CLAUDE_SKILL_DIR}/size.py" --write                  # -> trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --capital 300000 --risk-pct 0.5
```

Other flags: `--now`, `--json`, `--dir trader`.

## Set the rules once

Copy `config.example.json` (in this folder) to `trader/config.json` and
edit it. The ones that matter for sizing:

| key | default | means |
| --- | --- | --- |
| `capital` | 500000 | the money set aside for swing trading, in rupees |
| `cash` | null | cash available now; null = capital minus open positions' cost |
| `risk_per_trade_pct` | 1.0 | max loss at the stop, as % of capital |
| `max_position_pct` | 20.0 | max cost of one position, as % of capital |
| `cash_buffer_pct` | 10.0 | cash never spent, as % of capital |
| `min_order` | 1000 | smaller orders are refused |
| `charges` | see `india/charges.py` | `brokerage_per_order`, `dp_per_sell` etc. for your broker |

When the user says "I have 5 lakh and want to risk 1 %", write those into
`trader/config.json` and say what you wrote.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | entry, stop, GTT stop limit, target (swing-exit) |
| `trader/positions.json` | open positions (swing-card), for the cash limit |
| `trader/config.json` | the rules above |
| `trader/orders.json` | with `--write`: one proposal, CNC BUY, qty, entry, GTT OCO legs, costs |

## How to present it

1. The quantity, the cost, and which limit decided it.
2. The loss at the stop, against the budget, plus estimated charges.
3. The gap case: the loss if the stock gaps and fills only at the GTT
   limit. If it gaps below that, the GTT does not fill at all; say so.
4. If refused: the reason (a stop too far away for the risk budget is
   the usual one) and the honest options: a closer stop from a real level,
   a smaller risk elsewhere, or skipping the trade. Never "just buy fewer"
   by quietly breaking the rule.
5. Next: `/swing-risk`.

Charges are an estimate; your contract note has the real numbers. Not
financial advice.
