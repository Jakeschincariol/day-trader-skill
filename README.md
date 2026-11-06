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

You need Python 3.8 or newer (check with `python3 --version`) and [Claude Code](https://claude.com/claude-code) or the Claude desktop app. Nothing to pip install. Tested on macOS only; Linux should work, Windows is untested.

**1. Get the code**

```bash
git clone -b nse-port https://github.com/yuvrajyadav3141/day-trader-skill-nse.git
cd day-trader-skill-nse
```

(Drop `-b nse-port` once the port is merged to `main`.)

**2. Install the skills, either way**

*A. Copy the folders (simplest; gives plain names like `/trader-scanner`):*

```bash
mkdir -p ~/.claude/skills
cp -R trader-* ~/.claude/skills/
```

Copy `trader-data` too: the `trader-*` pattern includes it, and the tools import it. Start a new Claude session afterwards. To update later, `git pull` and run the same `cp -R` again.

*B. As a plugin:* in Claude Code, add the cloned folder as a marketplace and install from it:

```
/plugin marketplace add /full/path/to/day-trader-skill-nse
/plugin install day-trader-skills-nse@day-trader-skills-nse
```

In the desktop app `/plugin` opens a window instead: add the folder path there. Plugin skills are namespaced, e.g. `/day-trader-skills-nse:trader-scanner`.

*No Claude Code?* Paste any one `SKILL.md` at the top of a chat and it works as a mode. You lose the Python tools, but the method stays.

**3. Set your rules**

In the folder where you will trade (any folder; the tools write a `trader/` folder there):

```bash
mkdir -p trader
cp ~/.claude/skills/trader-budget/config.example.json trader/config.json
```

Edit `trader/config.json`: `budget`, `max_loss_per_trade_inr` and `max_daily_loss_inr` first. The example uses 1,00,000 rupees, 500 and 1,500. Everything else (entry window 09:30 to 15:00, flat by 15:10, `"product": "MIS"`) can stay.

**4. Run it**

Ask Claude, or run the tools directly:

```bash
python3 ~/.claude/skills/trader-scanner/scan.py universe     # once: the NSE EQ list
python3 ~/.claude/skills/trader-scanner/scan.py daily        # before the open
python3 ~/.claude/skills/trader-scanner/scan.py orb          # after 9:35 AM IST
```

Then the order of the pack is: scanner, news, entry, exit, timemachine, budget, risk, broker. Each step reads what the one before wrote into `trader/`.

**5. Optional: Zerodha Kite Connect for prices**

The default is free Yahoo data and needs no account. If you have a Kite Connect plan with historical data:

```bash
export TRADER_DATA_SOURCE=kite
export KITE_API_KEY=your_key
export KITE_ACCESS_TOKEN=today_token     # Zerodha expires it every morning
```

You run Zerodha's login yourself; the tools never see your password or TOTP and never log in for you. See `trader-data/README.md`. The Kite path is untested against the live API: compare one `entry.py check` with Yahoo before relying on it.

**Troubleshooting**

- *NSE feed returns 403 or times out:* NSE's CDN refuses some clients. The tools say so and stop; they do not try to look like a browser. Try again later, or use `--offline` with saved files.
- *"holiday list unknown":* the built-in NSE holiday list covers 2026 only. Check nseindia.com, and see Contributing below.
- *Yahoo is slow or rate-limiting:* wait a minute; the tools retry once.

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

## Contributing

Issues and pull requests are welcome, especially: the 2027 NSE holiday list when it is published (it lives in `NSE_HOLIDAYS` in each script, and `tests/test_nse.py` checks that they agree), a live test of the Kite path, and ports of the old engine tests. Run `python3 -m unittest discover -s tests` before sending anything. Keep the standard-library-only rule.

## Files

```
trader-*/SKILL.md      the skill (what Claude reads)
trader-*/*.py          the tool (what Claude runs)
trader-data/           optional Kite Connect source, shared by the tools
tests/                 offline tests and fixtures
```

MIT, as the original. See LICENSE.
