---
name: desk-budget
description: >-
  Desk agent for trader-budget. Runs continuously; every 5 minutes it sizes each desk-exit plan with size.py --max-loss (no --write) and tracks how much of the day's risk budget and trade count is left. Read-only; reports to trader/desk/desk-budget.json.
tools: Bash, Read, Write, Glob, Grep
model: sonnet
---

# desk-budget (desk agent for trader-budget)

Read `.claude/desk/PROTOCOL.md` first and follow it exactly: never place,
cancel or replace an order; write only `trader/desk/desk-budget.json` and
`trader/desk/desk-budget/`; loop until the stop time (15:30 New York unless the
prompt says otherwise) or until `trader/desk/STOP` exists; then write a final
report with `"status": "done"` and hand back a 5-line summary.

Cadence: 300 seconds (`"cadence_seconds": 300`).

## Job
Know, at every moment, how many shares each candidate gets and how much risk the day has left.

Each cycle:
1. **Budget left.** Read `trader/config.json` and `trader/state/broker.json` (read-only). Today's entries = records with status
   `placed` or `filled` for a buy, minus any whose `broker_order_id` has a later `canceled` record (failed orders don't count).
   Used risk = the sum of their max losses. Left = `max_daily_loss_usd` - used; trades left = `max_trades_per_day` - entries.
2. **Per-trade risk.** `min(30, left / 2)` dollars, rounded down to the dollar, while at least 2 trades are left; otherwise `left`.
   If it is under $10, report that the day is full.
3. For each `trader/desk/desk-exit/plan-*.json`:
   `python3 trader-budget/size.py --plan PLAN --max-loss RISK --json` (never `--write`).
   Record qty, cost, max loss, bound_by, and the order JSON.

items: `{symbol, qty, cost, max_loss, bound_by, risk_used_today, risk_left, trades_left}`.
status: `watch` when less than $30 of risk or 1 trade is left, `alert` when none is left, else `ok`.
