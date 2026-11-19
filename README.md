# India Swing skill

9 Claude skills for swing trading Indian stocks: scan NSE charts, track news and results, plan entry, stop and target, replay the odds, size in rupees, and print a trade card you place yourself.

Plain Python that reads free public data: Yahoo Finance daily charts for
`.NS` and `.BO` symbols, NSE's published files (the equity list, price
bands, the bhavcopy) and, with one optional package, NSE's results dates,
announcements and corporate actions.

Built for swing trades: delivery (CNC) positions held for days or weeks,
decided on daily closes, protected by a GTT OCO at your broker. Every price
the pack writes is on a valid NSE tick, every date skips NSE holidays, every
amount is in rupees.

**You place every order yourself.** Nothing in this pack talks to a broker.
It ends in a trade card you type into Zerodha, Groww, Upstox, Dhan, Angel One
or any other broker, if you decide yes.

> Adapted from Jake Schincariol's
> [Day Trader skill](https://github.com/Jakeschincariol/day-trader-skill)
> (MIT), a US day-trading pack. The method carried over; the market, the
> data, the time frame and the order flow are new.

## Install

As a plugin, in Claude Code:

```
/plugin marketplace add Ibrahimhass/day-trader-skill
/plugin install india-swing-skill@india-swing-skill
```

Or copy the folders. The skills share the `india/` folder, so copy it too:

```bash
git clone https://github.com/Ibrahimhass/day-trader-skill.git
cd day-trader-skill
cp -r india swing-* ~/.claude/skills/
```

Python 3.8 or newer, nothing else required. For NSE results dates,
announcements and corporate actions, install the optional
[`nse`](https://pypi.org/project/nse/) package (GPL-3.0, not bundled):

```bash
pip install -r requirements-nse.txt
```

Without it every tool still runs and says which checks are off.

## The nine

| command | job | what it does |
| --- | --- | --- |
| `/swing-scanner` | Chart Scanner | Scans the NSE list for daily swing setups: 20-day and 52-week breakouts, bull flags, 20-day reclaims, 50-day pullbacks, oversold bounces. |
| `/swing-news` | News Monitor | Indian headlines, NSE filings, the next results date and ex-dates for every stock you watch. |
| `/swing-entry` | Entry Timer | Calls the entry on a daily close above the level and suggests the next session's order. |
| `/swing-exit` | Exit Planner | Sets the stop, the target, the GTT values and a time stop before you enter. |
| `/swing-timemachine` | Time Machine | Replays the hold 10,000 times from the stock's own daily bars, gaps included, plus every past time the setup fired. |
| `/swing-budget` | Budget Manager | Sizes the position in rupees to your risk per trade, with estimated charges. |
| `/swing-risk` | Risk Manager | PASS, WARN or BLOCK: heat, open positions, price bands, results inside the hold, ticks, cash. |
| `/swing-card` | Trade Card | The order and the GTT, ready to type into your broker; then your journal. |
| `/swing-alerts` | Price Alerts | After the close: stop, gap, target, time stop, results and ex-dates tomorrow. |

## How to use it

Everything lands in a `trader/` folder in your project, and each skill reads
what the last one wrote:

```
scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> card   (one trade)
alerts: daily after 15:50 IST, while it is open
```

Set your rules once: copy `swing-budget/config.example.json` to
`trader/config.json` and edit `capital` and anything else (defaults: 1 %
risk per trade, 20 % max position, 10 % cash buffer, 5 open positions, 5 %
total heat, reward:risk at least 1.5, 15 trading days max hold).

An example, from the offline test data (real NSE data, Reliance, Tuesday
17 November 2026, after the close, ₹5 lakh capital):

1. **`/swing-scanner`**: of 20 charts, 7 candidates, 10 hits. RELIANCE
   closed at ₹1,367.00, above every close of the previous 20 sessions
   (the highest was ₹1,344.80): `breakout_20d`.
2. **`/swing-news`**: the day's headlines and any results date inside the
   next 15 sessions.
3. **`/swing-entry`**: TRIGGERED, the 17 November bar closed above
   ₹1,344.80. Next session (18 November): LIMIT buy at ₹1,373.90.
4. **`/swing-exit`**: stop at the lowest low of the last 10 sessions,
   ₹1,282.00, so ₹91.90 a share at risk; target 2R, ₹1,557.70; GTT stop
   limit ₹1,269.10; time stop 10 December 2026.
5. **`/swing-timemachine`**: 10,000 replays from the last 756 sessions
   (seed 19): target first 2.8 %, stop first 16.9 %, time stop 80.3 %. The
   same setup fired 141 times on Reliance in five years: 6 targets, 30
   stops, 105 time stops. Verdict: close to a coin flip. That is the point
   of looking first.
6. **`/swing-budget`**: 1 % of ₹5,00,000 is ₹5,000 at risk; 5,000 / 91.90 =
   54 shares, ₹74,190.60. Loss at the stop ₹4,962.60 plus about ₹176 of
   charges.
7. **`/swing-risk`**: PASS.
8. **`/swing-card`**:

   ```
   BUY RELIANCE (NSE) · CNC · 54 shares · LIMIT ₹1,373.90 · valid 2026-11-18
   GTT OCO  stop trigger ₹1,282.00 / limit ₹1,269.10
            target trigger ₹1,557.70 / limit ₹1,557.70
   Risk at stop ₹4,962.60 + charges ~₹176 · R:R 2.0 · time stop 2026-12-10
   Place the GTT after the buy fills: most brokers need the shares in your holdings first.
   ```

   You decide. If yes, you place it in your broker app, then tell Claude the
   fill (`card.py record`), and later the exit (`card.py close`).
9. **`/swing-alerts`**: every day after the close, until the trade is out.

## The tools

```bash
python3 swing-scanner/scan.py universe                       # NSE equity list
python3 swing-scanner/scan.py daily                          # after 15:50 IST
python3 swing-news/news.py --tickers TCS 'M&M' --hours 48
python3 swing-entry/entry.py check RELIANCE --setup breakout_20d --write
python3 swing-exit/exit.py plan --write                      # -> trader/plan.json
python3 swing-timemachine/timemachine.py run --write
python3 swing-budget/size.py --write                         # -> trader/orders.json
python3 swing-risk/check.py
python3 swing-card/card.py show
python3 swing-alerts/alerts.py check
python3 -m india.market clock                                # NSE open or closed (IST)
python3 -m india.market refresh-holidays                     # needs the nse package
```

Every tool takes `--now "YYYY-MM-DD HH:MM"` (IST) to pin the clock,
`--offline PATH` to read saved data, `--json`, and `--dir trader`.

```bash
python3 -m unittest discover -s tests -v
```

The tests run offline on fixtures cut from real data on 18 November 2026
(20 NSE stocks, NSE's lists and bhavcopy, Yahoo and Google News feeds) and
reproduce every number in the example above.

## Fine print

**This is not financial advice.** It is software that reads public data and
does arithmetic. It does not know your situation and cannot see the future.
SEBI's own studies found that most individual traders in equity derivatives
and in intraday trading lose money. You can lose money swing trading too.
Decide for yourself, and talk to a SEBI-registered adviser if you need advice.

**You place every order.** No skill here connects to a broker, holds a key or
places, modifies or cancels anything. Claude prints a card; you decide.

**A GTT is a plan, not a guarantee.** A stock that gaps below the GTT's limit
price leaves the stop order unfilled, and the loss can be far larger than
planned. Results days, regulatory news and market-wide falls cause gaps. The
alerts flag it; checking your holdings is on you.

**The Time Machine is a simulation, not a prediction.** It is built from the
stock's own last three years of daily bars. The future can do what those
years never did.

**The data is free and unofficial.** Yahoo's endpoints and NSE's website can
lag, change or refuse requests; the latest day's close from Yahoo may be the
last traded price, not NSE's official closing price. Check anything that
matters against your broker.

**Holidays need a yearly refresh.** `india/holidays.json` holds NSE's
trading holidays; when NSE publishes next year's list, run
`python3 -m india.market refresh-holidays`. Until then the tools warn and
treat only weekends as closed.

**Charges and tax are estimates.** Delivery charges (STT, stamp duty,
exchange and SEBI fees, GST, DP) follow `india/charges.py`; your contract
note is the truth. Gains held under a year are short-term capital gains.
Nothing here is tax advice.

## Files

```
india/              shared: IST clock, NSE holidays, symbols, ticks, rupees, charges, data, indicators, levels, nse_source
swing-scanner/      SKILL.md, scan.py
swing-news/         SKILL.md, news.py
swing-entry/        SKILL.md, entry.py
swing-exit/         SKILL.md, exit.py
swing-timemachine/  SKILL.md, timemachine.py
swing-budget/       SKILL.md, size.py, config.example.json
swing-risk/         SKILL.md, check.py
swing-card/         SKILL.md, card.py
swing-alerts/       SKILL.md, alerts.py
tests/              unittest suite + offline fixtures (capture_fixtures.py rebuilds them)
docs/               design and plan
```

MIT. Adapted by [Ibrahim Hassan](https://github.com/Ibrahimhass) from the
Day Trader skill by Jake Schincariol.
