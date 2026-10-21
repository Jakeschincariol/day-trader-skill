---
name: trader-timemachine
description: >-
  Time Machine. Replays a planned trade before you risk a dollar: 10,000
  replays drawn from the stock's own last 60 days of 5-minute bars, plus the
  same rule on each of those sessions. Takes the plan from trader-exit
  (entry, stop, target, flat-by time), rebuilds the rest of the day 10,000
  times from those bars, and re-runs the same rule on each past session.
  Prints the odds of target first, stop first, or neither by the flat-by
  time, each with a 95 % interval, where the price sits at that time, the
  average R, the history, one plain verdict and what the model leaves out,
  then hands off to /trader-budget. Use when the user says "run the time
  machine", "replay this trade", "what are the odds", "simulate this trade",
  "monte carlo", "backtest this setup", "how often does this hit the
  target", "is this a coin flip", or after /trader-exit writes a plan,
  before /trader-budget.
argument-hint: "[path to plan.json, or TICKER]"
---

# trader-timemachine

The Time Machine sits between the plan and the money. trader-exit has set
the entry, the stop, the target and the flat-by time. Before anything is
sized or sent, this skill asks one question: if the rest of today is stitched
from the stock's own last 60 days of 5-minute bars, how often does this plan
hit the target first, the stop first, or neither? It answers with 10,000
replays and with the record of the same rule on each of those past sessions.
It is a bootstrap built from the stock's own recent bars, not a prediction,
and the section "What it cannot tell you" below is part of the answer. Day
trading loses most people money, and a good-looking replay does not change
that.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run                    # trader/plan.json, 10,000 replays, seed 19
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --write            # also save trader/timemachine.json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --until 16:00      # end at the close instead of the plan's flat_by
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --fill next-open   # fill at the next bar's open, not the signal close
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
| `trader/plan.json` | the plan from trader-exit: symbol, date, entry, entry_time / entry_bar, stop, stop_rule, target, target_r, opening range, flat_by |
| Yahoo chart API | one request: 60 days of 5-minute bars (`range=60d&interval=5m`), free and unofficial, can lag |
| `trader/timemachine.json` | with `--write`: `{plan, mc, history}` plus the verdict, its notes and the caveats. `mc` holds the odds with their intervals, the both-touched count, percentiles, the fan-chart bands, 160 sample paths and a 24-bin histogram of the close |

## How it works

1. **The pool.** It keeps only FULL sessions before the plan's date: all 78
   five-minute bars, 9:30 to 4:00 New York time. Half days, gaps and today
   are left out. Every bar becomes four ratios to the bar before it:
   open, high, low and close over the previous close.
2. **One replay.** Start at the entry price. For each bar left in the day,
   pick a past bar from the same time of day (plus or minus 2 bars) at
   random, and scale it to the current price. Bar by bar, it checks the stop
   first, then the target. A bar that touches both counts as the stop, and
   the run says how many replays were decided that way.
3. **10,000 replays** give four odds. Target first. Stop first. Neither,
   which means the trade was still open at `--until`. Green, which means
   target first or above the entry at `--until`. The default `--until` is
   the plan's flat-by time (trader-exit writes 15:55), so "neither" means
   still open when the plan says to be flat. A plan without one ends at the
   close (4:00 PM, or 1:00 PM on an NYSE early-close day). Target first and
   stop first carry a Wilson 95 % interval: the noise of 10,000 draws, about
   plus or minus one point, and nothing about whether the model is right.
   R is +1 at a 1R target, -1 at the stop, and otherwise the distance from
   the entry at `--until` divided by the risk. A gap through the stop still
   counts as -1R here. A real fill can be worse.
4. **The fill.** By default each replay is filled at the signal bar's close,
   the plan's entry. `--fill next-open` fills at the open of the next drawn
   bar instead, and measures R from that fill. Neither model adds a spread,
   slippage or a commission. The run prints which one it used.
5. **The history.** The plan's own rule (the same opening range, stop rule
   and target R) runs again on each of those past sessions. That is what
   happened on those days, not a simulation. Its decided win rate (target
   over target plus stop) carries its own 95 % interval, which is wide: 28
   decided trades say little.
6. **The verdict** is one line from the numbers. It looks only at the
   replays that hit one side, and asks how often the target came first. A
   bigger target needs to win less often to break even: 1 in (1 + R). That
   is 50 % at 1R, 33 % at 2R, 25 % at 3R. Less than 5 points from break-even:
   "Close to a coin flip" at 1R, "Close to break-even" at any other R. 5 to
   15 points: "Leans toward the target" or "Leans toward the stop". 15 or
   more: "Strongly toward" one of them. So a 2R plan with target first
   24.1 % and stop first 50.5 % is close to break-even (it needs 33 % of
   the 74.6 % that hit a side, and got 32 %), not a loser.
7. **Below the verdict**, when it applies: a line when more than 40 % of the
   replays hit neither (the price at `--until` decides those), and the
   average R when its sign goes against the lean. Those can only point the
   other way because of the replays that hit neither. Then, always, two
   caveats: the pool and the history share the same sessions, and the fill
   model with its missing costs.

**The seed.** The draws come from Python's `random.Random(seed)`, seed 19 by
default. Same plan, same data, same seed: the same numbers, on any machine.
Say the seed with every result so the user can repeat it.

**5-minute bars only.** Yahoo keeps 60 days of 5-min bars but only about 7
days of 1-min bars, too few sessions for a fair pool. It refuses, in one
plain line, when there are fewer than 20 full sessions, when the entry bar is
not in the data (wrong date, not closed yet, a future day), or when the plan
does not make sense (a stop above a buy's entry, an entry off the 5-minute
grid). A live in-progress bar is never used.

## What it cannot tell you

- **Bars are drawn independently.** Each 5-minute bar is picked on its own
  from the same time of day. A quiet morning does not make a quiet
  afternoon, a wide bar does not make the next one wide, and nothing
  trends. There is no volatility clustering, no news, no halt, nothing the
  last 60 days did not do.
- **Fills are at the close of the signal bar.** The plan's entry is a bar's
  close, and the replay starts there. A real order fills at the next bar's
  open or worse. `--fill next-open` shows that case, still with no spread,
  slippage or commission.
- **The history is the same 59 sessions.** The pool is built from the
  sessions the history runs on, so when the two agree they are one piece
  of evidence, not two.
- **No costs.** No spread, no slippage, no commission, no borrow. Every R
  here is before all of those.
- **The intervals are sampling noise only.** The 95 % interval on target
  first and stop first says how much another 10,000 draws would move the
  number. It says nothing about whether drawing bars this way is a fair
  picture of today.

## Steps

1. Make sure `trader/plan.json` is today's plan from `/trader-exit`. If there
   is none, run that first, or pass the plan as flags.
2. Run `timemachine.py run --write`. The replays end at the plan's flat-by
   time on their own; pass `--until 16:00` only if the user wants the close.
3. Tell the user, in this order: the four odds with their intervals, the
   both-touched count, the median and the 5 to 95 range of the price at the
   end time, the average R, the history line, then the verdict line and
   every line under it exactly as printed. Say the seed.
4. If the verdict is a coin flip or close to break-even, say so plainly. Do
   not dress it up. If the history and the replays disagree, say that too.
5. Say once what the model leaves out: bars drawn one at a time from the
   last 60 days, fills at the signal bar's close, no costs, and a history
   that is not independent of the pool. Earnings, news and halts can do
   things those 60 days never did. Check `/trader-news` for the stock
   before going on.
6. If the user still wants the trade, hand off to `/trader-budget` to size it.

## Example: the reel

TSLA, Monday 2026-10-19. The 15-minute opening range is 354.47 to 362.18.
The 10:10 bar closes above it: entry 364.18 at 10:15 AM (bar 8), stop 358.32
(the range midpoint, rounded down), target 370.04 (1R, risk 5.86 a share),
flat by 15:55. `timemachine.py run` on that plan:

```
10,000 replays of the rest of the session, 10:15 AM to 3:55 PM, the plan's flat_by (68 five-minute bars), seed 19.
Each bar is drawn whole from TSLA's own 5-min bars at the same time of day (+-2 bars) over its last 59 full sessions (2026-07-27 to 2026-10-16).
Fills at the signal bar's close. No spread, slippage or commission is included.

  target first   29.2 %  (95 % interval 28.3 to 30.1)
  stop first     24.2 %  (95 % interval 23.4 to 25.1)
  neither        46.6 %   still open at 3:55 PM
  green          52.1 %   target first, or above the entry at 3:55 PM
  both touched in one bar: 0 (0.0 %), counted as the stop

  Price at 3:55 PM: median 364.37, 90 % of replays between 355.78 and 373.19.
  Average R: +0.045 (R = the 5.86 risk: +1R at the target, -1R at the stop).

History: the same rule (15-min opening range, stop at the opening-range midpoint, 1R target) on each of those 59 real sessions fired 33 times: 13 target, 15 stop, 5 neither. 13 of 28 decided, 46 % (95 % interval 30 to 64). Average R -0.070.

Close to a coin flip: target first 29.2 % vs stop first 24.2 %.
46.6 % of the replays hit neither by 3:55 PM; the price at 3:55 PM decides those.
Built from the same 59 sessions as the history: the two are not independent evidence.
Fills at the signal bar's close; a real fill is the next bar's open or worse. No costs included.
```

At 1R the target has to come first in half of the replays that hit one
side. It did in 54.7 %, with the interval on each side about a point wide.
The real history was slightly worse than even, on 28 decided trades, from
the same sessions. That is the honest answer for this setup, and it is what
the user should hear before `/trader-budget` sizes 8 shares. At `--until
16:00` the same seed gives target first 29.4 %, stop first 25.5 %, neither
45.1 %, average R +0.034.

## Rules

- Every number comes from the run. Never round a coin flip up into an edge.
- The verdict line and the lines under it are printed by the tool. Repeat
  them, do not rewrite them. Never judge a 2R or 3R plan by target first vs
  stop first alone: the verdict already weighs the target's R.
- Simulated odds are not predictions and not promises. Say it once, plainly,
  with what the model leaves out.
- Free Yahoo data is unofficial and can lag. Bars are 5-minute bars, checked
  bar by bar, never tick by tick and never real time.
- Always say the seed, so any run can be repeated.
- One plan per run. A changed entry, stop, target, date or fill model is a
  new run.

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
