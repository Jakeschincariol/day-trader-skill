---
name: trader-timemachine
description: >-
  Time Machine. Replays every possible outcome of a trade before you risk a
  dollar: 10,000 simulated sessions plus every past time the setup fired.
  Takes the plan from trader-exit (entry, stop, target), rebuilds the rest of
  the day 10,000 times from the stock's own 5-minute bars over the last 60
  days, and re-runs the same rule on every past session. Prints the odds of
  target first, stop first, or neither by the close, where the price sits at
  the close, the average R, the history, and one honest verdict, then hands
  off to /trader-budget. Use when the user says "run the time machine",
  "replay this trade", "what are the odds", "simulate this trade", "monte
  carlo", "backtest this setup", "how often does this hit the target", "is
  this a coin flip", or after /trader-exit writes a plan, before
  /trader-budget.
argument-hint: "[path to plan.json, or TICKER]"
---

# trader-timemachine

The Time Machine sits between the plan and the money. trader-exit has set
the entry, the stop and the target. Before anything is sized or sent, this
skill asks one question: if today plays out like the stock's own last 60
days, how often does this plan hit the target first, the stop first, or
neither? It answers with 10,000 replays and with the real record of the same
rule on every past session. It is a simulation built from the stock's own
recent bars, not a prediction. Day trading loses most people money, and a
good-looking replay does not change that.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run                    # trader/plan.json, 10,000 replays, seed 19
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --write            # also save trader/timemachine.json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --until 15:55      # end each replay at your flat-by time
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --slippage auto    # count fill costs from your own fills
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --symbol TSLA --date 2026-10-19 \
    --entry 364.18 --stop 358.32 --target 370.04 --entry-time "10:15 AM"
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" chart --from           # ASCII fan chart of the saved run
```

Other flags: `--replays N`, `--seed N` (default 19), `--window N` (default 2
bars), `--offline FILE` (a saved Yahoo chart JSON, `.json` or `.json.gz`),
`--now "2026-10-19 10:15"` (New York time) to pin the clock.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | the plan from trader-exit: symbol, date, entry, entry_time / entry_bar, stop, stop_rule, target, target_r, opening range |
| Yahoo chart API | one request: 60 days of 5-minute bars (`range=60d&interval=5m`), free and unofficial, can lag |
| `trader/state/broker.json` | with `--slippage auto`: trader-broker's measured fills (`--broker-state` to point elsewhere) |
| `trader/timemachine.json` | with `--write`: `{plan, mc, history}` plus the verdict. `mc` holds the odds, percentiles, the fan-chart bands, 160 sample paths and a 24-bin histogram of the close |

## How it works

1. **The pool.** It keeps only FULL sessions before the plan's date: all 78
   five-minute bars, 9:30 to 4:00 New York time. Half days, gaps and today
   are left out. Every bar becomes four ratios to the bar before it:
   open, high, low and close over the previous close.
2. **One replay.** Start at the entry price. For each bar left in the day,
   pick a past bar from the same time of day (plus or minus 2 bars) at
   random, and scale it to the current price. Bar by bar, it checks the stop
   first, then the target. A bar that touches both counts as the stop.
3. **10,000 replays** give four odds. Target first. Stop first. Neither,
   which means the trade was still open at `--until` (default 4:00 PM, the
   close, or 1:00 PM on an NYSE early-close day). Green, which means target
   first or above the entry at `--until`.
   R is +1 at a 1R target, -1 at the stop, and otherwise the distance from
   the entry at `--until` divided by the risk. A gap through the stop still
   counts as -1R here. A real fill can be worse.
4. **The history.** The plan's own rule (the same opening range, stop rule
   and target R) runs again on every one of those past sessions. That is
   what really happened, not a simulation.
5. **The verdict** is one line from the numbers. It looks only at the
   replays that hit one side, and asks how often the target came first. A
   bigger target needs to win less often to break even: 1 in (1 + R). That
   is 50 % at 1R, 33 % at 2R, 25 % at 3R. Less than 5 points from break-even:
   "Close to a coin flip" at 1R, "Close to break-even" at any other R. 5 to
   15 points: "Leans toward the target" or "Leans toward the stop". 15 or
   more: "Strongly toward" one of them. So a 2R plan with target first
   24.1 % and stop first 50.5 % is close to break-even (it needs 33 % of
   the 74.6 % that hit a side, and got 32 %), not a loser.
6. **Below the verdict**, when it applies: a line when more than 40 % of the
   replays hit neither (the price at `--until` decides those), and the
   average R when its sign goes against the lean. Those can only point the
   other way because of the replays that hit neither.

**Slippage.** Without `--slippage` every replay fills perfectly, which is
too rosy. With it, each side costs that much: `--slippage 0.03` (dollars a
share), `--slippage 5bps` (basis points of the entry), or `--slippage auto`,
the average of the user's own measured fills from trader-broker
(`ticket.py slippage`; entries, stops and flattens, 5 or more of them, and
an average better than zero counts as zero). Until there are 5, auto assumes
5 bps and says so. With slippage on, the entry fills that much worse. A stop
fills at the stop, or at the bar's open when the bar opens through it (a
gap), then that much worse. The close at `--until` fills that much worse.
The target is a limit and fills at its price. The random draws do not change, so
target first, stop first and neither stay the same. R, green, the history's
average R and the verdict's break-even become net of costs, and the report
prints the average R both ways.

**The seed.** The draws come from Python's `random.Random(seed)`, seed 19 by
default. Same plan, same data, same seed: the same numbers, on any machine.
Say the seed with every result so the user can repeat it.

**5-minute bars only.** Yahoo keeps 60 days of 5-min bars but only about 7
days of 1-min bars, too few sessions for a fair pool. It refuses, in one
plain line, when there are fewer than 20 full sessions, when the entry bar is
not in the data (wrong date, not closed yet, a future day), or when the plan
does not make sense (a stop above a buy's entry, an entry off the 5-minute
grid). A live in-progress bar is never used.

## Steps

1. Make sure `trader/plan.json` is today's plan from `/trader-exit`. If there
   is none, run that first, or pass the plan as flags.
2. Run `timemachine.py run --write --slippage auto`. Add `--until 15:55`
   when the plan has a flat-by time, so "neither" means still open at the
   time you would get out. Leave slippage off only when the user asks for
   perfect fills.
3. Tell the user, in this order: the four odds, the median and the 5 to 95
   range of the price at the close, the average R (after slippage and with
   perfect fills), the slippage used and where it came from, the history line,
   then the verdict line and any line under it exactly as printed. Say the seed.
4. If the verdict is a coin flip or close to break-even, say so plainly. Do
   not dress it up. If the history and the replays disagree, say that too.
5. Say once that this is built from the last 60 days and is not a prediction.
   Earnings, news and halts can do things those 60 days never did. Check
   `/trader-news` for the stock before going on.
6. If the user still wants the trade, hand off to `/trader-budget` to size it.

## The multi-ticker backtest

One stock's history is about 30 trades in 60 days: too few to tell an edge
from luck. `backtest.py` runs the same opening-range breakout (long only) on
many tickers and tests filters with an in-sample / out-of-sample split.

```bash
python3 "${CLAUDE_SKILL_DIR}/backtest.py" run --symbols TSLA,NVDA,AMD,AAPL,META --slippage auto
python3 "${CLAUDE_SKILL_DIR}/backtest.py" run --watchlist trader/watchlist.json --slippage 5bps \
    --filter "rvol>=2" --filter vwap --filter market --filter "time<=10:30" --by time --by rvol
python3 "${CLAUDE_SKILL_DIR}/backtest.py" run --symbols TSLA,NVDA --stop-rule or_low --target-r 2 --write
```

Rule flags: `--or-minutes 15`, `--stop-rule or_mid|or_low|pct` (`--stop-pct`),
`--target-r 1`, `--last-entry 15:30`, `--until 15:55`. A stop that the next
bar opens through fills at that bar's open. `--slippage` takes `5bps` or `auto`
(not dollars: the tickers have different prices). Up to 40 tickers, one Yahoo
request each, half a second apart. `--offline DIR` reads `<SYM>-60d5m.json(.gz)`.

**Filters**, on what each trade looked like when it fired: `rvol>=2`
(volume from the open to the entry vs the last 20 sessions), `gap>=0.5`
(open vs the previous close, %), `or_pct<=2` (range width, %), `price>=10`,
`time<=10:30`, `vwap` (entry above the session VWAP), `market` (`--market`,
SPY by default, above its own VWAP at that bar). A trade whose value is
unknown is left out and counted.

**How it judges.** The days are split in time order, the first half in
sample and the second half out of sample (`--split 0.5`). It scores the
baseline, each filter alone and all of them together in both halves: trades,
win rate, average R with its 95 % range, all after slippage. The baseline is
labeled positive, losing or mixed after costs. A filter "held up" only when
it beat the baseline's average R in both halves, with 30 or more trades in
each, and its average R is above zero after costs in both; it also says
whether the out-of-sample 95 % range clears zero. A filter that beat a losing
baseline but still loses is labeled "less bad than the baseline in both
halves, but still loses after costs": never present that as an edge. Better
in sample only is labeled "likely noise". When several filters are tried, it
says some will look good by chance.

Tell the user the verdict per filter as printed, and the trade counts. Never
recommend a filter that did not hold up, and never call a filter proven on
fewer than 30 out-of-sample trades. 60 days is one market mood: a filter that
held up is a candidate to keep watching in the journal (`/trader-broker`,
`journal.py`), not a sure thing.

## Example: the reel

TSLA, Monday 2026-10-19. The 15-minute opening range is 354.47 to 362.18.
The 10:10 bar closes above it: entry 364.18 at 10:15 AM (bar 8), stop 358.32
(the range midpoint, rounded down), target 370.04 (1R, risk 5.86 a share).

```
10,000 replays of the rest of the session, 10:15 AM to 4:00 PM (69 five-minute bars), seed 19.
  target first   29.4 %
  stop first     25.5 %
  neither        45.1 %   still open at 4:00 PM
  green          51.7 %   target first, or above the entry at 4:00 PM
  Price at 4:00 PM: median 364.36, 90 % of replays between 355.54 and 373.54.
  Average R: +0.034
History: the same rule on each of those 59 real sessions fired 33 times:
13 target, 15 stop, 5 neither. Average R -0.062.
Close to a coin flip: target first 29.4 % vs stop first 25.5 %.
45.1 % of the replays hit neither by 4:00 PM; the price at 4:00 PM decides those.
```

At 1R the target has to come first in half of the replays that hit one
side. It did in 53.6 %. The replays came out close to a coin flip, and the
real history was slightly worse than even. That is the honest answer for this setup, and it is what
the user should hear before `/trader-budget` sizes 8 shares.

## Rules

- Every number comes from the run. Never round a coin flip up into an edge.
- The verdict line and the lines under it are printed by the tool. Repeat
  them, do not rewrite them. Never judge a 2R or 3R plan by target first vs
  stop first alone: the verdict already weighs the target's R.
- Simulated odds are not predictions and not promises. Say it once, plainly.
- Free Yahoo data is unofficial and can lag. Bars are 5-minute bars, checked
  bar by bar, never tick by tick and never real time.
- Always say the seed, so any run can be repeated.
- One plan per run. A changed entry, stop, target or date is a new run.

## What it never does

It never places an order, never sizes a position, never changes the plan,
and never calls a result a sure thing. It never prints a P&L or a profit.
It never uses a bar that has not closed yet, and never mixes today's bars
into the pool.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Paper trading by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order except trader-broker, and only when all three hold: trader-risk
  passed that exact order today, the user typed an explicit yes for that one order in the chat, and the
  user clicked Allow once on Claude's own card because the order tool is set to "Needs approval"
  (Customize > Connectors > tool permissions). Never set an order tool to "Always allow".
- No options, margin, short selling or leverage unless the config allows it and the user confirms.
- Broker keys live in environment variables or the Claude Desktop config, never in the chat.
