---
name: trader-zones
description: >-
  Zone Finder. Finds ICT-style supply and demand zones on the 1-hour, 30-minute
  and 15-minute charts of five markets (XAUUSD, GBPUSD, EURUSD, NQ and MGC), then
  looks for the 5-minute and 3-minute entry that follows a sweep of a zone: a
  fair value gap (FVG) or inverse FVG (IFVG) inside the 62% to 79% retracement,
  then a 3-minute change of character (CHoCH). Zones are one candle, high to
  low: a small body, long wicks, then a strong move away. Asia, London and New
  York windows only. Free Yahoo data. Use when the user says "find my zones",
  "supply and demand", "demand zone on gold", "any setups on GBPUSD", "FVG
  entry", "IFVG", "sweep and CHoCH", "check NQ", "check MGC", or at the start of
  a London or New York session.
argument-hint: "[markets | zones SYMBOL | setup SYMBOL] [--tf 30m] [--days 2] [--now \"YYYY-MM-DD HH:MM\"]"
---

# trader-zones

The Zone Finder is the forex, gold and futures sibling of the Chart Scanner. It
reads free charts and lists the supply and demand zones that match a written
rule, and the entries that matched the rule after a zone was swept. A zone is a
price area where a rule fired on past bars, not a prediction. Most people who
trade lose money; this tool does not change that. It only draws the same zones
the same way every time, so you can check them against your own marks.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/zones.py" markets                      # the five markets and their Yahoo tickers
python3 "${CLAUDE_SKILL_DIR}/zones.py" zones GBPUSD                 # last 2 days, 60m + 30m + 15m, max 3 a day
python3 "${CLAUDE_SKILL_DIR}/zones.py" zones XAUUSD --tf 30m --days 2 --max-per-day 3
python3 "${CLAUDE_SKILL_DIR}/zones.py" setup NQ                     # sweep + FVG/IFVG in the OTE + M3 CHoCH
python3 "${CLAUDE_SKILL_DIR}/zones.py" setup MGC --now "2026-10-26 08:15" --offline DIR
python3 "${CLAUDE_SKILL_DIR}/zones.py" setup EURUSD --write         # also writes trader/zones.json
```

Exit code 0 when something was found, 1 when nothing was, 2 on an error (the
reason is one plain line).

## The markets

| symbol | Yahoo ticker | what it really is |
| --- | --- | --- |
| XAUUSD | GC=F | COMEX gold futures, standing in for spot gold |
| GBPUSD | GBPUSD=X | spot forex |
| EURUSD | EURUSD=X | spot forex |
| NQ | NQ=F | Nasdaq 100 futures (NAS100, US100 and NDX are accepted) |
| MGC | MGC=F | micro gold futures |

Gold futures and spot gold are close but not the same price: the futures carry a
premium and roll to a new contract. Treat a gold zone as an area, not an exact
tick, and check it against your own chart. Yahoo's forex and futures bars can lag
and have gaps.

## The zone

One candle, high to low, drawn by a fixed rule so it is the same every run:

1. Displacement: a candle whose body is at least 1.5 x ATR(14) and 60 % of its
   own range, and that closes beyond the last confirmed swing high (demand) or
   swing low (supply).
2. Zone candle: the latest candle before it, up to 5 back, with a body under
   0.4 x ATR, wicks making up more than half its range, and a move away from its
   extreme of at least 2 x ATR.
3. Fresh until price trades back into it, then touched.
4. Only zones from the last 2 days, at most 3 per day, and only candles that
   opened in an Asia, London or New York window.

## The entry (long shown, short is the mirror image)

1. Price touches a demand zone.
2. On 5-minute bars it sweeps the latest swing low (wick below, close back
   above), with the wick reaching into the zone.
3. After the sweep a 5-minute FVG forms, or a bearish FVG is closed through (an
   IFVG), and its midpoint sits in the 62 % to 79 % retracement of the leg from
   the sweep low to the highest high since.
4. Price trades back into that gap without breaking the sweep low.
5. On 3-minute bars a close above the last lower high made after the sweep (the
   CHoCH) is the trigger, inside a session window.
6. The stop sits under the sweep low, the target is the nearest opposing zone or
   swing, and the entry is dropped when the reward to risk is under 2.

`setup` says how far each zone got when nothing triggered, for example "swept,
no FVG or IFVG with its midpoint in the OTE", so a quiet day is explained.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/config.json` | optional `zones` object that overrides any default, for example `{"zones": {"min_rr": 3, "sessions": {"ny": [7, 10]}}}` |
| `trader/zones.json` | written with `--write`: the zones or the setups, with times as Unix seconds |

Session hours are New York time, so daylight saving is handled. The 3-minute
bars are built from 1-minute bars, and Yahoo keeps about a week of 1-minute
history, so `setup` cannot look further back than that.

## Steps

1. At the start of a session: `zones.py zones SYMBOL` for each market. Say how
   many zones were found and how many are fresh.
2. During a session: `zones.py setup SYMBOL`. Report any entry with its zone,
   sweep time, gap, entry, stop, target and reward to risk, or the stage the
   best zone reached.
3. The user decides what to do. Never pick for them.

## Rules

- Say what was read: the market, the Yahoo ticker, the time of the data.
- Say "matched a rule", never "a buy", "a winner" or "a good trade".
- Never print a P&L, a return or a profit figure.
- A signal is stale once price has moved on. Re-run before acting on it.
- Say plainly that gold is read from futures.

## What it never does

It never places, sizes or checks an order, never says which market to trade, and
never promises that a zone or an entry works.

## Safety

- Education and tooling, not financial advice. A signal is a rules check, not a recommendation.
- This skill cannot place an order. The pack's only order path is trader-broker, and only when
  trader-risk passed that exact order, the user typed an explicit yes for that one order in the
  chat, and the user clicked Allow once on Claude's own card.
- Paper trading by default. Going live is the user's own decision, in their own config.
- Futures and forex are leveraged: a small move can lose more than the account holds. Set the stop
  and the size before any order.
- Broker keys live in environment variables or the Claude Desktop config, never in the chat.
