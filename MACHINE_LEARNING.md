# Machine Learning

A running log of what went wrong (and right) in each live trading session, and
the rule each one taught. Claude reads this before every session and adds to it
after. Newest session first. Rules that have been learned are collected in
**Standing rules** at the top so they are applied, not just remembered.

## Standing rules

1. **Check the live broker quote before ranking or planning a late entry.**
   Yahoo's 5-minute bars lag. The watchlist scan can show a stock holding above
   its breakout level when the live quote is already back below it.
   Rank candidates on Alpaca's `get_stock_latest_quote`, not the watchlist's
   `last` column. *(2026-11-12, MSFT)*
2. **Plan the exit from the live ask, not the old trigger price.** For a late
   entry run `exit.py plan --symbol X --entry <live ask> --or-high H --or-low L`.
   The `--from trader/entry.json` default uses a trigger price from hours ago.
   *(2026-11-12)*
3. **On the free IEX feed, ignore wide spreads.** Some IEX quotes show
   $10–$20 spreads (LYV, ABNB, EXPE on 2026-11-12). Don't size off them. Use
   the mid on tight quotes only, or check the last trade. *(2026-11-12)*
4. **Windows shell: `TZ=America/New_York date` is ignored in Git Bash.** It
   printed GMT. Work out New York time in Python with `zoneinfo`, or use
   `alerts.py clock`. Don't hard-code UTC-5, because daylight saving changes
   the offset. *(2026-11-12)*
5. **Test monitoring scripts once before the long loop.** A price regex
   `([\d.]+)` grabbed the sentence's trailing period ("406.44.") and crashed
   the first watch. Use `(\d+\.\d+)`. *(2026-11-12)*
6. **A 2R target late in the day rarely fills.** ROK, entered at 1:52 PM,
   never got within $6 of its 2R target. For entries after 1:00 PM ET use
   `--target 1R`. *(2026-11-12)*
7. **Don't take ORB breakouts more than about 2 hours after they trigger.**
   ROK (breakout at 9:50 AM, entered at 1:52 PM) chopped sideways, then slid
   back under the breakout level. By mid-afternoon the opening range is no
   longer the level that matters. For late trades, use the day's high and a
   fresh 30-minute structure. *(2026-11-12)*
8. **Cut a trade early once it closes back under its breakout level.** That
   is the failed-breakout signal. Closing ROK there lost $12.42 instead of
   risking the full $29.52. *(2026-11-12)*
9. **Screen late-day setups at about 11:00 AM–1:30 PM, not at 3:00 PM.** By
   3:00 PM there are 30 minutes of entry window left, and the 3 parallel
   screeners found nothing that passed. Run the agents earlier, while there
   is still time to act. *(2026-11-12)*
10. **The free IEX quote feed is unusable for most names.** About 80% of
    symbols showed spreads of 1–11%. Screen spread and size on liquid
    large-caps only, or check `get_stock_latest_trade`. Treat "no quote" as
    unknown, not as wide. *(2026-11-12)*
11. **Buy-stop triggers beat chasing.** Placing bracket buy-stops just above
    the day high (DVN, XOM, CVX) meant no fill unless the breakout happened.
    None triggered, so the cost was zero, which beats buying a fade. Cancel
    unfilled triggers at `no_entries_after` (3:30 PM). Stage them with
    `exit.py --stop price:X --target 1R`, then `size.py --write`, then set
    `type: stop` and `stop_price` in orders.json, then run `check.py`.
    *(2026-11-12)*
12. **Keep `trader/portfolio.json` cash in line with the budget.** After raising
    `budget`, also raise the portfolio cash, or `size.py` stays bound by the
    old cash. *(2026-11-12)*

## Session log

### 2026-11-12 (Thu), paper account

**Setup.** The scan ran at 1:39 PM ET: 145 opening-range breakouts, all
triggered between 9:50 AM and 1:25 PM. I ranked the ones still holding above
the range high by the distance from the live price to the range-midpoint stop.

**Mistakes.**
- Chose MSFT from the Yahoo-based list, then the live Alpaca quote ($523.84)
  showed it back under its $525.83 breakout. That wasted a step and nearly
  planned a failed breakout. → Rule 1.
- The first watch script crashed on a regex bug. → Rule 5.
- Assumed `TZ=` worked in Git Bash. It didn't. → Rule 4.
- Entered ROK about 4 hours after its breakout. That is a late, weaker trade,
  and it started drifting toward the breakout level right after the fill.
  Lesson: late breakouts need a clear reason to still work (a fresh push or
  new highs), not just "still above the level".

**Trades.**
| symbol | entry | stop | target | qty | max loss | result |
| --- | --- | --- | --- | --- | --- | --- |
| ROK | 406.60 (1:52 PM, market) | 403.60 | 413.44 (2R) | 9 | $29.52 | closed early at 405.22 (2:54 PM): **-$12.42** |
| DVN | buy-stop 46.52 | 46.27 | 46.77 (1R) | 85 | $21.25 | never triggered (high 46.47), canceled 3:30 PM |
| XOM | buy-stop 170.93 | 170.40 | 171.46 (1R) | 23 | $12.19 | never triggered (high about 170.78), canceled 3:30 PM |
| CVX | buy-stop 218.10 | 217.37 | 218.83 (1R) | 18 | $13.14 | never triggered (high about 217.93), canceled 3:30 PM |

**Day:** -$12.42 (paper equity $99,987.58). One filled trade, a loss.

**Process changes made today.** The user gave standing approval for paper
orders (`auto_approve`, `ticket.py approve --auto`). Research fanned out to 3
parallel screener agents, and all orders were placed centrally. The budget was
raised to $20,000 with the $50/trade and $150/day loss limits unchanged.

**Tooling gap (fixed the same day).** `ticket.py` had no way to record a
canceled order. Added `ticket.py canceled --broker-id ID`. trader-risk now
leaves an order canceled before it filled out of the day's trade count and
max loss. Use it for every unfilled trigger canceled at the cutoff.

**Plan for the next session.**
1. 9:00–9:30 AM ET: run the scanner pre-market. Read the Standing rules.
2. 9:45 AM–11:00 AM: opening-range breakouts with buy-stop triggers just
   above the range high. Check the live Alpaca quote first (Rule 1).
3. 11:00 AM–1:30 PM: parallel screener agents for second-leg setups
   (Rule 9), with 1R targets after 1:00 PM (Rule 6).
4. 3:30 PM: cancel unfilled triggers and run `ticket.py canceled`.
   3:55 PM: flat.

**What went right.** All three gates held (risk PASS, explicit yes, Allow
once). The bracket put the stop at the broker the moment the entry filled, and
the max loss was known before entry.
