---
name: trader-futures
description: >-
  Index Futures Autotrader. Trades index futures only (Micro E-mini S&P 500
  MES, Micro Nasdaq-100 MNQ, Micro Dow MYM, Micro Russell M2K, their full-size
  versions, Micro Nikkei MNK in the Tokyo, European and US sessions, Micro/Mini-DAX and Euro Stoxx 50 on Eurex) through Interactive
  Brokers, with one strategy: the volume surge breakout on 5-minute bars (a
  bar with 2.5x the usual volume for its time of day that breaks the last
  hour's range, closes strong and above VWAP). Sizes every trade in EUR to a
  max loss per trade, checks margin, a daily loss limit, trades per day and a
  cooldown, sends one bracket order (limit entry, stop, target), and is flat
  by the close. Runs by itself on the user's computer through IB Gateway, in
  observe, paper or live mode; paper is the default and live needs a sentence
  the user types in the config. Backtests on real IBKR bars, writes an
  Excel-ready trade journal. Use when the user says "futures", "index
  futures", "MES", "ES", "NQ", "DAX future", "autotrader", "trade
  automatically", "backtest the strategy", "volume surge", "IBKR", "IB
  Gateway", or asks why it did or did not trade.
argument-hint: "[backtest | status | observe | journal]"
---

# trader-futures

An autotrader for index futures on Interactive Brokers. It watches the market
so the user does not have to, and it is built so a mistake costs as little as
possible: paper first, a fixed max loss per trade in euros, a daily loss limit
that closes everything and stops for the day, and never a position overnight.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/futures.py" specs                                   # the contracts it knows
python3 "${CLAUDE_SKILL_DIR}/futures.py" backtest --contract MES --bars trader/mes-5m.csv --out trader/backtest.csv
python3 "${CLAUDE_SKILL_DIR}/futures.py" signal   --contract MES --bars trader/mes-5m.csv --now "2026-11-03 16:30"   # Dutch time
python3 "${CLAUDE_SKILL_DIR}/ib_tools.py" status                                 # IB Gateway must run
python3 "${CLAUDE_SKILL_DIR}/ib_tools.py" download --contract MES --days 60 --out trader/mes-5m.csv
python3 "${CLAUDE_SKILL_DIR}/ib_tools.py" flatten  --contract MES
python3 "${CLAUDE_SKILL_DIR}/autotrader.py" --mode observe                       # watch + notify, read-only
python3 "${CLAUDE_SKILL_DIR}/autotrader.py" --mode paper                         # the user starts this
```

## The strategy: volume surge breakout

On every completed 5-minute bar inside the entry window (US index futures
09:45-15:30 New York time = 15:45-21:30 Dutch time; Eurex 09:15-17:00
Frankfurt time; Micro Nikkei MNK in three sessions, see below), a LONG signal
needs all five:

1. volume at least 2.5x the average of the same 5-minute slot over the last
   10 sessions (sessions with under half the busiest session's volume are left
   out, so a contract that was the thin back month before the quarterly roll
   does not look like one long surge);
2. a close above the highest high of the previous 12 bars (the last hour);
3. a strong bar: close above the open, in the top 30 % of its range;
4. a close above the session VWAP;
5. not a blow-off: the bar's range is at most 2.5x ATR(14).

The plan: a LIMIT entry 2 ticks above the signal close (if the market runs
away, no fill, no chase; it waits 60 seconds), a stop one tick under the
signal bar's midpoint (at least 4 ticks, at most 1.5x ATR, otherwise no
trade), a target at 2R, and flat by the end of the session the trade was opened in (15:55 New York,
17:25 Frankfurt, or the MNK session's flat-by). Shorts
are the mirror image and are off unless the user adds "short" to
`strategy.directions`. Every number is in `trader/config.json`.

## The rules before every entry

- contracts = whole contracts so that the loss at the stop, plus 2 ticks of
  stop slippage and both commissions, fits `max_loss_per_trade_eur` (USD
  contracts converted at the account's own EUR/USD rate); 0 contracts = no trade;
- at most `max_contracts`, `max_trades_per_day` (counted when an order is sent),
  `max_open_positions`;
- today's P&L (realized + open, from IBKR) plus a stop-out must stay above
  `-max_daily_loss_eur`; at the limit it flattens everything and stops for the day;
- `cooldown_after_loss_min` after a loss in that contract;
- IBKR's what-if initial margin at most `max_margin_pct` of available funds;
- the contract it trades is the nearest one that expires more than
  `roll_days` (8) days ahead, with multiplier and tick from IBKR itself;
- the contract keys and IBKR symbols are in `futures.py specs`; when IBKR uses
  another symbol for a contract, `"contract_overrides": {"MNK": {"symbol": "..."}}`
  in the config fixes it without code changes (ib_tools.py status shows it);
- a position the user opened by hand in the same contract blocks new entries
  and is never touched by the autotrader.

## Modes

| mode | connection | orders | account it accepts |
| --- | --- | --- | --- |
| `observe` | read-only | none, it only notifies | any |
| `paper` | normal | by itself, bracket orders | paper only (id starts with DU) |
| `live` | normal | by itself, real money | live only, and only with `"paper": false` plus `"live_confirm": "IK BEGRIJP DAT DIT ECHT GELD IS"` typed by the user |

Stop: Ctrl+C (open positions keep their stop and target at IBKR), or create
the file `trader/STOP`: it flattens what it opened and exits; it will not
start again until the file is deleted.

Notifications: every signal, order, fill, exit, block and error is printed
and logged to `trader/state/autotrader.log`. For the phone: install the free
ntfy app, subscribe to a long random topic name, and put it in
`notify.ntfy_topic`. Anyone who knows the topic name can read it: trades and P&L
are sent, account numbers (masked) and balances are not, so pick a name
nobody can guess.

## What Claude does and does not do

- Claude may run `specs`, `backtest`, `signal`, `ib_tools.py status` and
  `download`, and `autotrader.py --mode observe` when the user asks, and read
  `trader/journal.csv`, `trader/state/*.json` and the log to explain what
  happened and why.
- Claude never starts `--mode paper` or `--mode live` itself: the user starts
  the autotrader in their own terminal, so the decision to trade is theirs,
  every day. Claude explains how.
- Claude never sets `"paper": false`, never writes the `live_confirm`
  sentence, never raises a risk limit on its own, and never deletes
  `trader/STOP`. It can explain each setting; the user changes it.
- Claude never asks for, reads or repeats IBKR usernames, passwords or
  account numbers. The login happens in IB Gateway, never in the chat.
- After any change to the strategy, Claude runs the backtest again and shows
  the before and after, including the losing trades. It never presents a
  backtest as a forecast.
- For one-off manual trades, IBKR's own connector in Claude
  (Customize > Connectors) drafts orders the user approves in IBKR; this skill
  does not replace that check with anything weaker. The autotrader only
  places orders after the user started it in paper or live mode: that start,
  with its limits in the config, is the user's yes for the trades within them.

## Setup (once)

1. IBKR account with **futures trading permission** (Settings > Account
   Settings > Trading Permissions: Futures, for the US and/or Eurex).
   MNK is a CME contract: the US futures permission covers it.
2. **Market data**: real-time data for CME (and CBOT for MYM) and/or Eurex,
   requested in the Client Portal. The paper account gets the live
   account's data only when "share market data with paper account" is on.
   Without it the bars are delayed and every signal comes too late.
3. Install **IB Gateway** (stable), log in to the **paper** account. In
   Configure > Settings > API > Settings: enable ActiveX and Socket Clients,
   socket port 4002 (paper), untick "Read-Only API" for paper mode, trusted IP
   127.0.0.1. Turn on auto-restart so it survives IBKR's nightly reset.
4. Python 3.10 or newer, then `pip install ib_async` (on Windows also
   `pip install tzdata`).
5. Copy `config.example.json` to `trader/config.json` and set the limits.
6. `ib_tools.py status`: it must say PAPER, show the contract and the position 0.
7. `ib_tools.py download --days 60`, then `futures.py backtest` on that file.
8. A week or more in `observe`, then weeks in `paper`, then decide.

## The Micro Nikkei (MNK) and sessions

MNK is $0.50 per Nikkei point with a tick of 5 points ($2.50), quoted in USD
on CME Globex, and it trades almost around the clock. It is traded in three
sessions, each with its own VWAP, its own volume baseline per 5-minute slot
(a 03:00 bar is compared with earlier 03:00 bars, never with the US open), and
its own flat-by, so a trade never runs from one session into the next or into
CME's daily maintenance break:

| session | entry window (local) | flat by | Dutch time (winter / summer) |
| --- | --- | --- | --- |
| tokyo | 09:15-15:00 Tokyo | 15:25 | 01:15-07:00, flat 07:25 / 02:15-08:00, flat 08:25 |
| europe | 09:15-15:00 Frankfurt | 15:25 | 09:15-15:00, flat 15:25 (same all year) |
| us | 09:45-15:30 New York | 15:55 | 15:45-21:30, flat 21:55 |

In the weeks when the US and Europe change the clocks on different dates
(March, late October) the US session starts an hour earlier for us and
overlaps the end of the European one; `max_open_positions` still allows one
position at a time. Pick the sessions per contract in the config:
`"contract_overrides": {"MNK": {"sessions": ["tokyo", "us"]}}`; any contract
can get sessions this way. All times the tools print are Dutch time.

MNK is a younger and thinner contract than MES: expect wider spreads and more
slippage outside Tokyo hours, and judge it on a backtest of its own bars
(`ib_tools.py download --contract MNK`): the backtest reports every trade with
its session, so it shows which sessions earn their keep. With MES and MNK both
in `contracts`, the daily loss limit and the trade count are shared per Dutch
calendar day.

## Files

| file | what |
| --- | --- |
| `trader/config.json` | `"futures": {...}`: contracts, mode guards, strategy, risk, notify |
| `trader/journal.csv` | every closed trade, semicolon CSV with decimal commas (opens in Dutch Excel) |
| `trader/state/futures-YYYY-MM-DD.json` | today's trades, open trade, halt reason |
| `trader/state/autotrader.log` | everything it did and why |
| `trader/STOP` | the emergency stop |

## Safety

- Not financial advice. This is software that follows rules on price and
  volume; it does not know the news, and a rule that worked on past bars can
  stop working. Most people who day trade lose money.
- Futures are leveraged. One MES contract moves $5 per index point; on a
  1 % day in the S&P 500 that is about $300 per contract. A loss can be larger
  than the money in the account. A stop limits a loss only if it fills: in a
  fast market or across a halt it fills worse.
- Paper first, always. Live needs the user's own yes in the config and a
  live account; nothing in this skill switches to live by itself.
- Nothing here is tax advice.
