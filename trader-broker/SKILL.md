---
name: trader-broker
description: >-
  Order Executor for Codex. Prepare and record one explicitly approved stock
  order at a time after trader-risk passes. Show the plain ticket and exact
  Alpaca MCP payload, require the user's yes plus separate tool approval,
  record fills, or prepare a flatten ticket. Paper trading by default.
  Use when the user says "place the order", "buy it", "execute", "send it to
  my broker", "close my position", "flatten", "connect Alpaca", or "set up
  paper trading". Never submit from an unattended or scheduled task.
---

# trader-broker

The Order Executor is the only skill in this pack that can lead to a real
order, so it is the strictest. An order reaches the market only after three
separate gates, every time, for every order:

1. **trader-risk passed this exact order today** (matched by fingerprint).
2. **The user typed an explicit yes for this one order** in the chat.
3. **The user approved the exact broker tool call separately in Codex**,
   with the broker MCP server configured to prompt for tool calls.
   If the client cannot enforce this separate approval, prepare the ticket
   only and let the user submit it in the broker UI.

Two yeses from the user, one PASS from the rules. No yes, no order.

Resolve this SKILL.md file's directory to an absolute path and set `SKILL_DIR`
to that path in each shell call below. `SKILL_DIR` is a shell variable you set,
not a Codex-provided environment variable. Keep the working directory at the
user's trading project so relative `trader/` files stay in that project.
When calling another skill's tool, resolve that skill's directory separately.

```bash
python3 "${SKILL_DIR}/ticket.py" show                     # every ticket, READY or not
python3 "${SKILL_DIR}/ticket.py" approve --index 1 --reply "yes"
python3 "${SKILL_DIR}/ticket.py" result --index 1 --status placed --broker-id ID --filled-qty 8 --filled-price 364.20
python3 "${SKILL_DIR}/ticket.py" fill --symbol TSLA --side sell --qty 8 --price 370.04
python3 "${SKILL_DIR}/ticket.py" flatten --symbol TSLA --qty 8
python3 "${SKILL_DIR}/ticket.py" log
```

`ticket.py` never talks to a broker. It renders tickets, checks that a reply
is a real yes for that order, builds the flatten ticket, and keeps the log in
`trader/state/broker.json`. `--now "2026-10-19 10:15"` pins the clock (New York time).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders (trader-budget writes it; `flatten` replaces it) |
| `trader/state/risk.json` | trader-risk's verdicts; only a PASS from today is READY |
| `trader/state/broker.json` | every yes, no, placed, failed and filled, with each entry's max loss |
| `trader/portfolio.json` | cash and shares, updated by `fill` and by `result --filled-qty` |
| `trader/plan.json` | the flat-by time for `flatten` |

## Setup A: Alpaca (official MCP server, Codex)

Alpaca's server is [alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server).
It runs as a local STDIO process. Its order payload described below was
checked against version 2.4.0 on 2026-10-20; verify the installed server's
current tool schema before sending a ticket.

1. The user creates **paper trading** API keys in the Alpaca dashboard.
   Paper keys are separate from live keys.
2. Install `uv` (which provides `uvx`) from [docs.astral.sh/uv](https://docs.astral.sh/uv/).
3. Merge the block from [config.example.toml](config.example.toml) into
   `~/.codex/config.toml`, or `.codex/config.toml` in a trusted project.
   Keep existing settings; do not replace the whole configuration file.
   The example forwards `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` from the
   environment of the Codex process using `env_vars`. The user supplies them
   privately before launching Codex. A desktop app launched outside that
   environment may not inherit them; configure its host environment privately.
   Never ask for keys in chat or read their values back into the conversation.
4. The example sets `ALPACA_PAPER_TRADE = "true"`, exposes account, trading
   and stock-data tools, and uses `default_tools_approval_mode = "prompt"`.
   This requires a current Codex client supporting that setting. Never use
   auto-approval for order tools or bypass the client's approval policy.
   High-impact bulk, options and crypto tools are disabled in the example.
5. Restart Codex. In the CLI, `codex mcp list` lists configured servers and
   `/mcp` inside the session shows connected servers. Check `get_account_info`
   (read only) and confirm in the Alpaca dashboard that it is the paper account.
   Confirm that the client requires separate tool approval before enabling
   order submission. Without that capability, stop at the ticket.

This configuration is for the machine running Codex. A local STDIO server
and local environment variables are not automatically available in a cloud
executor; configure and verify them on the execution host before use.
See the [Codex MCP documentation](https://developers.openai.com/codex/mcp/).

**Bracket orders on Alpaca.** `place_stock_order` takes
`take_profit_limit_price` and `stop_loss_stop_price` (and an optional
`stop_loss_limit_price`). When either is there, the server sets
`order_class` to "bracket" by itself; trader-budget writes it anyway so the
ticket shows it. A bracket is whole shares only, with `time_in_force` day or
gtc. After the entry fills, the stop-loss and the take-profit wait at the
broker as two orders that cancel each other. They are day orders too, so they
end at the close: one more reason to be flat by then.

## Setup B: Interactive Brokers (verify compatibility first)

The original pack described an Interactive Brokers connector for another
client. That listing does not establish that the connection works in Codex.
Use an IBKR MCP connection only after verifying Codex support, authentication,
the installed tool schemas, and separate approval for draft instructions.
Set `"broker": "ibkr"` in `trader/config.json` only for that workflow. The
local tool can prepare an IBKR ticket, but this pack does not install or
validate an IBKR connection. Without one, present the ticket for the user
to enter and approve manually in IBKR. Never send an Alpaca payload to IBKR.

## Steps: the entry

1. `ticket.py show`. Only READY tickets go to the user. A ticket that is NOT
   READY or BLOCKED goes back to `$trader-risk`.
2. Show ONE ticket and ask: "Place this order? Reply yes or no." One order
   per question. Never offer "yes to all".
3. Run `ticket.py approve --index N --reply "<the user's reply, word for word>"`.
   If it prints "Not recorded", the reply was not an explicit yes for this
   order (for example "sure", "yes to all", or a yes that names a different
   stock or amount). Ask again. Never turn a reply into a yes yourself.
4. Only after "Recorded your yes", call `place_stock_order` with exactly the
   JSON the ticket printed, after verifying the connected tool's schema.
   Require the separate Codex approval for that exact call; a chat yes alone
   is not permission to bypass it. If unavailable, stop at the ticket.
5. Record what happened: `ticket.py result --index N --status placed
   --broker-id <id> --filled-qty Q --filled-price P` (the fill from the
   response or `get_open_position`), or `--status denied`, or `--status failed`
   with `--note`. A failed order is not retried without a new check and a new yes.
   The log keeps the entry's max loss for trader-risk's daily limit.

## Steps: while it is open, and out by the close

- trader-alerts watches the stop, the target and the flat-by time
  (`alerts.py add --from-plan`). The bracket's own orders do the stopping.
- When the stop-loss or the take-profit fills, record it:
  `ticket.py fill --symbol TSLA --side sell --qty 8 --price 358.32`.
- By `flat_by` (15:55 New York), anything still open gets closed:
  1. Ask Alpaca how many shares are held: `get_open_position` (read only).
  2. `ticket.py flatten --symbol TSLA --qty 8` writes a market sell for those
     shares to `trader/orders.json`.
  3. `$trader-risk`. A sell that only closes what the user holds is never
     blocked by the daily limits or the entry window.
  4. `ticket.py show`, then the user's yes for that one order, as above.
  5. The bracket's stop-loss and take-profit still hold those shares, so
     Alpaca rejects a new sell until they are canceled: `get_orders` (status
     open, nested true) shows them; `cancel_order_by_id` each one (separate Codex tool
     approval required). Then `place_stock_order` with the ticket, then `result`.

## Example: the reel

```
ORDER 1 of 1, PAPER account, Alpaca
  BUY 8 TSLA, market, good for today
  stop-loss 358.32
  take-profit 370.04
  max loss about $46.88 if the stop fills at 358.32 (it can fill worse in a fast market)
  why: opening-range breakout on TSLA: 8 shares, bound by your $50 max loss per trade (8 x 5.86 = $46.88 at the stop)
  READY: trader-risk PASS, waiting for your yes
  Codex will call place_stock_order with exactly:
    {"symbol": "TSLA", "side": "buy", "qty": "8", "type": "market", "time_in_force": "day",
     "order_class": "bracket", "take_profit_limit_price": "370.04", "stop_loss_stop_price": "358.32"}
```

The user replies "yes". Codex records it and requests separate tool approval
for that exact `place_stock_order` payload. If approved, it sends the order
to the verified paper account and records the response. If approval is denied,
record `denied`; if unavailable, stop at the ticket. The `why` and the plan
stay in the file; they are never sent.

## What it never does

- Never places an order without all three gates, and never two orders on one yes.
- Never places orders from a scheduled or background task: nobody is there to say yes.
- Never asks for, reads, stores or repeats API keys or passwords.
- Never switches `ALPACA_PAPER_TRADE` or `"paper"` to live. The user does that themselves.
- Never calls `close_all_positions`, `cancel_all_orders`, option or crypto order tools on its own.
- Never promises a fill price: a market order and a stop fill at whatever the market gives.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Paper trading by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order except trader-broker, and only when all three hold: trader-risk
  passed that exact order today, the user typed an explicit yes for that one order in the chat, and the
  user approved the exact broker tool call in Codex. Configure the broker MCP server with
  `default_tools_approval_mode = "prompt"`; never bypass or auto-approve order calls.
  If the client cannot require a separate tool approval, stop at the ticket and use the broker UI.
- No options, margin, short selling or leverage unless the config allows it and the user confirms.
- Broker keys live in environment variables forwarded by Codex MCP config, never in the chat.
