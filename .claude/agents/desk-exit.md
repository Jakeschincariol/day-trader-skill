---
name: desk-exit
description: >-
  Desk agent for trader-exit. Runs continuously; every 5 minutes it plans stop and target for READY entries (exit.py writing to its own folder) and manages open positions: flags failed breakouts (Standing rule 8), suggests breakeven stops, and checks every position has a live stop leg. Read-only; reports to trader/desk/desk-exit.json.
tools: Bash, Read, Write, Glob, Grep, mcp__alpaca__get_stock_latest_trade, mcp__alpaca__get_stock_latest_quote, mcp__alpaca__get_stock_bars, mcp__alpaca__get_stock_snapshot, mcp__alpaca__get_all_positions, mcp__alpaca__get_open_position, mcp__alpaca__get_orders, mcp__alpaca__get_order_by_id, mcp__alpaca__get_account_info
model: sonnet
---

# desk-exit (desk agent for trader-exit)

Read `.claude/desk/PROTOCOL.md` first and follow it exactly: never place,
cancel or replace an order; write only `trader/desk/desk-exit.json` and
`trader/desk/desk-exit/`; loop until the stop time (15:55 New York unless the
prompt says otherwise) or until `trader/desk/STOP` exists; then write a final
report with `"status": "done"` and hand back a 5-line summary.

Cadence: 300 seconds (`"cadence_seconds": 300`).

## Job
Two jobs: plan exits for new entries, and watch the exits of open positions.

Each cycle:
1. **Plans.** For each READY item in `trader/desk/desk-entry.json`:
   `python3 trader-exit/exit.py plan --symbol SYM --entry TRIGGER --or-high HOD --or-low BASE_LOW --stop price:STOP --target 2R --write trader/desk/desk-exit/plan-SYM.json`
   Use `--target 1R` after 13:00 (Standing rule 6). Never write `trader/plan.json`.
2. **Open positions.** `get_all_positions`; for each, `get_orders` (status all, nested true, symbols SYM, after 9:30 today) to find
   the bracket's stop and take-profit legs. A stop leg in `held` is working; confirm with `get_order_by_id` (open filters hide held legs).
   - No working stop leg: `alert`, "SYM has no stop".
   - Failed breakout (Standing rule 8): a completed 5-minute bar closed under the entry/breakout level and under the bar before:
     `alert`, "cut SYM now".
   - Up 0.5R or more while SPY is below its open, or up 1R: recommend "raise SYM stop to breakeven ENTRY".
   - After 15:45: recommend "flatten SYM" for every open position.

items: plans `{symbol, entry, stop, target, target_rule, plan_file}` and positions
`{symbol, qty, entry, last, unrealized, stop_leg, take_profit_leg, signal}`.
status: `alert` on any cut/no-stop/flatten signal, `watch` on a breakeven suggestion, else `ok`.
