# The Day Trader skill, for the NSE

11 Claude skills for day trading on the NSE: scan the market for setups, track quarterly results, time every entry and exit, and replay every outcome before you risk a rupee. You place the orders.

This is a port of [jakeschincariol/day-trader-skill](https://github.com/jakeschincariol/day-trader-skill) (MIT, US stocks) to India: IST clock, NSE holidays, NSE symbols, rupees and the 0.05 tick. The original is the work of its author; the port changes the market, not the method.

Free, MIT, no signup. The tools are plain Python (3.8 or newer, nothing to pip install) that read public data: Yahoo Finance charts for NSE symbols (or Zerodha Kite Connect, optional), NSE's own RSS feeds and CSV files.

## What changed from the US version

| | US original | This port |
| --- | --- | --- |
| Clock | New York, DST, NYSE holidays, 9:30 to 16:00 | IST (UTC+5:30, no DST), 16 NSE holidays for 2026, 9:15 to 15:30 |
| Opening range | 9:30, 9:35, 9:40 bars | 9:15, 9:20, 9:25 bars |
| Entry window / flat by | 09:45 to 15:30 / 15:55 | 09:30 to 15:00 / 15:10 (Zerodha squares off MIS around 3:20 PM) |
| Universe | Nasdaq Trader lists | NSE `EQUITY_L.csv`, EQ series (about 2,390 stocks) |
| Prices | Yahoo | Yahoo `SYMBOL.NS`, or Kite Connect for single-symbol charts (`trader-data/`) |
| Orders | Alpaca or IBKR connector, with a typed "yes" | **You place every order yourself in Kite**; `/trader-broker` prints the form and keeps the log |
| News | Yahoo headlines and SEC 8-Ks | NSE RSS: quarterly results, board meetings, announcements |
| Earnings analyst | SEC XBRL | Yahoo fundamentals time series, in crore |
| Pelosi tracker | House Clerk disclosures | `/trader-deals`: NSE bulk and block deals |
| Money | dollars, cents | rupees, 5-paisa tick; config keys end `_inr` |

## Install

In Claude Code, from this folder:

```
/plugin marketplace add /Users/yuvraj/Desktop/day-trader-skills-nse
/plugin install day-trader-skills-nse@day-trader-skills-nse
```

Or copy the folders for plain `/trader-scanner` names (copy `trader-data` too, the tools import it):

```bash
cp -r trader-* ~/.claude/skills/
```

## The eleven

| command | job |
| --- | --- |
| `/trader-scanner` | Scans the NSE EQ list for opening-range breakouts, flags, oversold bounces. |
| `/trader-news` | Quarterly results, board meetings and announcements for your watchlist, from NSE's feeds. |
| `/trader-entry` | Watches a setup bar by bar and tells you the moment to get in. |
| `/trader-exit` | Sets your stop and target (on the 0.05 tick) before you enter. |
| `/trader-timemachine` | Replays the rest of the session 10,000 times plus every past day the setup fired. |
| `/trader-risk` | Checks every trade against your limits. PASS or BLOCK, with the reason. |
| `/trader-budget` | Sizes the position to your budget and max loss per trade, in rupees. |
| `/trader-broker` | Prints the Kite order form (MIS), the stop-loss and target to place, and logs your fills. |
| `/trader-alerts` | Rings on the stop, the target, the 9:15 open and flat-by 15:10. |
| `/trader-analyst` | Last quarters' revenue, profit, EPS and margins side by side. |
| `/trader-deals` | Bulk and block deals, with the clients who made them. |

## One trade, run live on 2026-11-06

RELIANCE, Friday 2026-11-06, Yahoo data, replayed at 10:30 AM IST:

1. `/trader-entry`: opening range 1295.60 to 1306.00; the 9:45 bar closed at 1311.90, above it: **TRIGGERED, 9:50 AM**.
2. `/trader-exit`: stop 1300.80 (range midpoint), target 1323.00 (1R), risk 11.10 a share, flat by 15:10.
3. `/trader-timemachine`: 10,000 replays on RELIANCE's last 58 full sessions: target first 27.4 %, stop first 38.9 %, 33.7 % still open at 3:10 PM. On those sessions the same rule fired 28 times: 13 target, 10 stop, 5 neither. Verdict: leans toward the stop.
4. `/trader-budget` (₹1,00,000 budget, ₹500 max loss per trade): 45 shares, ₹59,035.50, max loss ₹499.50.
5. `/trader-risk`: PASS at 10:30; BLOCK at 09:20 (before 09:30), at 15:05 (after 15:00) and on 2026-11-10 (Diwali-Balipratipada, NSE closed).
6. `/trader-broker`: the Kite form, READY. You place the buy, then the SL-M stop and the LIMIT target, and log them.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Offline. The fixtures are saved NSE feeds (2026-11-06), Yahoo fundamentals for TCS and RELIANCE, and a made-up session for the trade chain.
**The US version's 300-odd tests were written around its US fixtures (TSLA bars, SEC filings, House PTRs) and were not ported:**
they are in the git history's first commit. The new suite covers the NSE changes and the trade chain, not every engine
path the old one did. The Time Machine's engine, for example, was checked by a live run, not by its old tests.

## Fine print

**Not financial advice.** This is software that reads public data and does arithmetic. It cannot see the future.
Most people who day trade lose money. You can lose money. Talk to a SEBI-registered adviser if you need advice.

**You place every order.** Nothing in this pack can place an order. `/trader-risk` can say PASS, and `/trader-broker`
prints the form; the click in Kite is yours.

**A stop is a plan, not a guarantee.** Kite has no bracket order, so the stop (SL-M) and the target (LIMIT) are
two separate orders that do not cancel each other: cancel the other one when one fills. In a fast market or across
a gap a stop can fill well past its trigger.

**The data is free and unofficial.** Yahoo's chart endpoint can lag, change or rate-limit you, and has no price for the last
two five-minute bars on most NSE days. NSE's RSS feeds hold only recent filings, and the feeds name companies, not symbols.
Check anything that matters in Kite before you act on it.

**Not modelled:** the Diwali Muhurat session, 2027 holidays (not published when this was written; the tools say
"unknown" instead of guessing), brokerage and statutory charges (STT, GST, exchange fees), MIS leverage (the budget
counts full price), F&O, and SEBI insider-trading (PIT) disclosures.

**Taxes.** Intraday equity gains are taxed as speculative business income in India. Nothing here is tax advice.

## Files

```
trader-*/SKILL.md      the skill (what Claude reads)
trader-*/*.py          the tool (what Claude runs)
trader-data/           optional Kite Connect source, shared by the tools
tests/                 offline tests and fixtures
```

MIT, as the original. See LICENSE.
