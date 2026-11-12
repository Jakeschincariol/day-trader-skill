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
6. **A 2R target late in the day rarely fills.** With about 2 hours to the
   close, a 2R target often can't be reached. Consider `--target 1R` for
   entries after 1:00 PM ET, or expect the flat-by close to decide the trade.
   *(2026-11-12, pending the ROK outcome)*

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

**Trade.**
| symbol | entry | stop | target | qty | max loss | result |
| --- | --- | --- | --- | --- | --- | --- |
| ROK | 406.60 (1:52 PM) | 403.60 | 413.44 | 9 | $29.52 | open, about -$6.60 at 2:09 PM |

**What went right.** All three gates held (risk PASS, explicit yes, Allow
once). The bracket put the stop at the broker the moment the entry filled, and
the max loss was known before entry.
