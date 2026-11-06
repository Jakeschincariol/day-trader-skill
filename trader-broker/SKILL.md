---
name: trader-broker
description: >-
  Order Ticket for Zerodha Kite. You place every order yourself; this skill
  never talks to a broker. It shows each approved order as a plain ticket and
  the Kite order form to fill in (exchange NSE, product MIS, order type,
  quantity, price, trigger), lists the stop-loss (SL-M) and target (LIMIT)
  sell orders to place once the entry fills (Kite has no bracket order),
  shows the max loss at the stop, and only shows an order as READY if
  trader-risk passed that exact order today. After you place it, it logs the
  Kite order id and the fill, keeps trader/portfolio.json, builds the sell
  ticket that closes a position by flat-by time, and logs each trade's max
  loss so trader-risk can hold the daily limit. Use when the user says "show
  me the ticket", "what do I put in Kite", "I placed it", "log my fill",
  "close my position", "flatten", "get me out", or after /trader-risk passes.
argument-hint: "[order number]"
---

# trader-broker

You place the order. This skill makes sure you place the same order the rest
of the pack checked, in the form Kite wants, and keeps the books afterwards.
It never opens a connection to Zerodha, never holds a key, and never places
anything.

An order shows as READY only when trader-risk passed this exact order today
(matched by fingerprint). Change the quantity or a price, and it is NOT READY
until trader-risk checks it again.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                     # every ticket, READY or not
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show --index 1 --json    # one ticket as JSON
python3 "${CLAUDE_SKILL_DIR}/ticket.py" placed --index 1 --broker-id 2611060001234 --filled-qty 45 --filled-price 1311.90
python3 "${CLAUDE_SKILL_DIR}/ticket.py" fill --symbol RELIANCE --side sell --qty 45 --price 1323.00
python3 "${CLAUDE_SKILL_DIR}/ticket.py" decline --index 1        # you chose to skip it
python3 "${CLAUDE_SKILL_DIR}/ticket.py" flatten --symbol RELIANCE --qty 45
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

`--now "2026-11-06 10:15"` pins the clock (IST).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders (trader-budget writes it; `flatten` replaces it) |
| `trader/state/risk.json` | trader-risk's verdicts; only a PASS from today is READY |
| `trader/state/broker.json` | what you placed, skipped and filled, with each entry's max loss |
| `trader/portfolio.json` | cash and shares, updated by `placed --filled-*` and `fill` |
| `trader/plan.json` | the flat-by time for `flatten` |
| `trader/config.json` | `product` ("MIS" intraday by default, or "CNC" delivery) and `flat_by` |

## What a ticket looks like

```
ORDER 1 of 1, Zerodha Kite, MIS (you place it yourself)
  BUY 45 RELIANCE, market, good for today
  stop-loss 1300.80
  take-profit 1323.00
  max loss about ₹499.50 if the stop fills at 1300.80 (it can fill worse in a fast market)
  READY: trader-risk PASS. Place it yourself in Kite, then log it with ticket.py placed
  Kite order form:
    exchange          NSE
    tradingsymbol     RELIANCE
    transaction_type  BUY
    product           MIS
    order_type        MARKET
    quantity          45
    validity          DAY
  Once the entry has filled, place these two SELL orders (Kite has no bracket order):
    stop-loss:   SELL, SL-M, trigger_price 1300.80
    target:      SELL, LIMIT, price 1323.00
```

(The tool prints every field of the two sell forms; they are shortened here.)

## Steps

1. Run `ticket.py show`. Read the ticket to the user in plain words: what, how many,
   the stop, the target, the max loss. If it says NOT READY or BLOCKED, say why and
   stop: send the user back to `/trader-risk` or `/trader-budget`.
2. The user opens Kite and places the BUY from the form. This skill does not do
   it for them and does not ask for a "yes": placing it is their decision.
3. When it has filled, `ticket.py placed --index N --broker-id <Kite order id>
   --filled-qty Q --filled-price P`. That logs it and updates the portfolio.
4. Kite has no bracket order, so the user places the stop-loss (SL-M) and the
   target (LIMIT) as two separate SELL orders. **They do not cancel each other.**
   When one fills the other must be cancelled in Kite at once, or it can fill too
   and leave a short position. Say this every time.
5. When the stop or target fills, `ticket.py fill --symbol S --side sell --qty Q --price P`.
6. By `flat_by` (15:10 IST by default), if the position is still open: `ticket.py
   flatten --symbol S`. It writes a sell ticket to `trader/orders.json`; run
   `/trader-risk` on it (a sell that only closes what you hold is never blocked by
   the daily limits), then `ticket.py show`. Cancel any open stop or target order
   in Kite first.

## Things the user should know about Kite (verify in Kite, they change)

- Zerodha squares off open MIS positions on its own around 3:20 PM IST and
  charges for it. `flat_by` is earlier on purpose.
- Bracket orders are not available on Kite equity; this pack uses two plain orders.
- The ticket shows the stop as an SL-M order (market once the trigger is hit).
  A fast market or a gap can fill it well past the trigger.
- Prices must be multiples of the 0.05 tick. The pack rounds stops down and
  targets to the nearest tick.
- There is no paper account on Kite. Start with a small budget and a small
  `max_loss_per_trade_inr`.

## Rules

- Never place an order, call a broker, or ask for a broker key, token or password.
- Never show an order as READY unless trader-risk passed that exact order today.
- Never change an order to make it pass; send it back to trader-budget.
- Say the stop is an order, not a promise.
- Never log a fill the user did not report.

## Safety

- Education and tooling, not financial advice.
- No skill in this pack places an order. You place every order yourself in Zerodha Kite.
- No margin, short selling or leverage unless the config allows it.
