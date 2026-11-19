# India Swing Pack: design

Date: 2026-11-19
Status: draft for approval

## Intent

Turn this fork of `day-trader-skill` (a US day-trading pack) into a set of
Claude skills for **swing trading Indian equities (NSE first, BSE symbols
accepted)**: find setups on daily charts, check the news and results
calendar, time the entry, plan stop and target, replay the odds, size the
position in rupees, run a risk check, and print a **trade card** the user
types into their own broker.

The user places every order themselves. They want information and analysis,
not automation.

## Goals

- Every tool works on NSE symbols (`TCS`, `M&M`, `BAJAJ-AUTO`) in IST, on NSE
  trading days, in rupees.
- The pipeline is built for multi-day holds (delivery / CNC): daily bars,
  stops that live for weeks as a GTT, a time stop after N trading days.
- Each trade ends in a trade card: symbol, exchange, product CNC, quantity,
  entry (limit or SL-buy trigger), GTT OCO stop trigger + limit, GTT target,
  estimated charges, max loss at the stop.
- Same safety posture as the original: nothing places an order, the risk
  check can block a card, numbers are reproducible (seeded), tests run
  offline on fixtures cut from real NSE data.
- Python standard library only, Python 3.8+, no API keys.

## Non-goals

- Order placement, broker APIs, broker MCP connectors, API keys.
- Intraday trading (opening-range breakouts, 5-minute bars, flat by close).
- F&O, short selling, margin / MTF.
- Fundamental analysis (the SEC analyst is dropped; an NSE results reader may
  come later).
- US Congress trades (Pelosi tracker dropped).

## Anti-goals

- A card that looks precise but uses a wrong tick size, wrong session or
  wrong holiday, so the user types a price the exchange rejects.
- Odds presented as predictions.
- Any path from the pack to a real order.

## Constraints

- Free public data only. Verified on 2026-11-19:
  - Yahoo chart v8 serves `.NS` and `.BO` daily bars (5y+ history,
    `exchangeTimezoneName: Asia/Kolkata`, `currency: INR`); spark v7 batches
    many symbols.
  - `archives.nseindia.com/content/equities/EQUITY_L.csv`: every NSE-listed
    equity with series (~2,600 rows).
  - `archives.nseindia.com/content/equities/sec_list.csv`: price band per
    symbol (2/5/10/20, or "-").
  - `archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv`:
    daily bhavcopy with delivery quantity and delivery %.
  - Yahoo headline RSS works with `s=TCS.NS&region=IN`; Google News RSS works
    with `hl=en-IN&gl=IN`.
  - The `www.nseindia.com/api/*` JSON endpoints (corporate announcements,
    results calendar, holiday master) need a cookie session; not yet
    verified (see Open questions).
- IST is UTC+5:30 with no daylight saving: no timezone library needed.
- NSE regular session 09:15-15:30 IST, Mon-Fri, minus trading holidays.

## Approaches considered

- **A. Patch in place**: keep all 11 skills, swap the US market layer, bend
  intraday tools toward daily bars. Smallest diff, but the entry, exit, Time
  Machine and alerts are built around one session and the NYSE clock is
  copied into 8 files.
- **B. Rebuild as a swing pack on one shared India module** (chosen by the
  user): one `india` module for clock, holidays, symbols, tick size, rupees
  and charges; each skill reworked for daily bars.
- **C. Broker integration** (MCP or REST adapters): ruled out by the user,
  who places orders themselves.

## Design

### Layout

```
india/                  shared module, imported by every tool
  market.py             IST clock, sessions, holidays, trading-day math
  symbols.py            normalise / validate / to_yahoo (NSE & BSE)
  ticks.py              NSE tick size by price band, round down / up
  money.py              rupee formatting (₹1,23,456.78 Indian grouping)
  charges.py            delivery charges estimate (config-driven table)
  data.py               polite HTTP fetcher, cache, offline fixtures
  holidays.json         NSE trading holidays by year (editable)
swing-scanner/          SKILL.md, scan.py
swing-news/             SKILL.md, news.py
swing-entry/            SKILL.md, entry.py
swing-exit/             SKILL.md, exit.py
swing-timemachine/      SKILL.md, timemachine.py
swing-budget/           SKILL.md, size.py, config.example.json
swing-risk/             SKILL.md, check.py
swing-card/             SKILL.md, card.py   (replaces trader-broker)
swing-alerts/           SKILL.md, alerts.py
tests/                  unittest suite + offline NSE fixtures
```

Removed: `trader-pelosi/`, `trader-analyst/`, `trader-broker/`, all
`trader-*` folders once their replacement lands. Working files stay in a
`trader/` folder in the user's project (as in the original).

Each tool finds `india/` relative to its own file (`sys.path` insert of the
repo root), so copying the folders into `~/.claude/skills/` must copy
`india/` too; README and plugin manifest updated to say so.

### Shared module (`india/`)

- **market.py**: `now_ist()`, `is_trading_day(d)`, `session(d)` ->
  (09:15, 15:30) or closed with reason, `next_trading_day`,
  `trading_days_between`, `add_trading_days(d, n)`, special sessions (e.g.
  Muhurat) listed but not treated as regular days. `--now "YYYY-MM-DD HH:MM"`
  pins the clock in every tool.
- **holidays.json**: `{ "2026": {"2026-01-26": "Republic Day", ...}, "2027":
  {...} }`, filled from NSE's published circular. A tool asked about a year
  with no list warns once and treats only weekends as closed.
- **symbols.py**: accepts `TCS`, `TCS.NS`, `NSE:TCS`, `RELIANCE.BO`,
  `BSE:RELIANCE`; canonical form `TCS` + exchange. Valid NSE symbol:
  `^[A-Z0-9&\-]{1,20}$`. `to_yahoo()` URL-encodes (`M&M` -> `M%26M.NS`) and
  never replaces `.` or `-`. Default exchange NSE.
- **ticks.py**: NSE equity tick size schedule by price (as revised in 2025:
  < ₹250 -> 0.01, 250-1,000 -> 0.05, 1,000-5,000 -> 0.10, 5,000-10,000 ->
  0.50, 10,000-20,000 -> 1.00, > 20,000 -> 5.00; to be verified against the
  NSE circular when built, and overridable in config). Stops round down, buy
  triggers round up, to a valid tick.
- **money.py**: `₹1,23,456.78`, lakhs/crores in prose where helpful.
- **charges.py**: delivery round-trip estimate from a table in config:
  brokerage (default ₹0, user sets theirs), STT 0.1% buy and sell, exchange
  transaction charge, SEBI fee, stamp duty 0.015% on buy, GST 18% on
  brokerage + exchange + SEBI, DP charge per scrip on sell. Defaults shipped
  with a "last checked" date; the card always says "estimate".
- **data.py**: one fetcher (User-Agent `day-trader-skill`, retries, small
  delay, Yahoo host fallback query2 -> query1), on-disk cache under
  `trader/cache/`, `--offline PATH` support used by the tests.

### Skills

**swing-scanner** (`scan.py universe | daily`)
- Universe: `EQUITY_L.csv`, series `EQ` (and `BE` with `--include-be`),
  written to `trader/universe.txt`.
- Daily scan on Yahoo daily bars via spark batches: keep the original's five
  setups (20-day closing-high breakout, bull flag, reclaimed the 20-day
  average, oversold, oversold bounce) and add 52-week-high breakout and
  pullback to a rising 50-day average.
- Filters (config): min price ₹50, min 20-day average traded value ₹5 crore,
  exclude price band 2% / 5% (from `sec_list.csv`) by default, optional
  delivery % from bhavcopy shown as a column.
- Writes `trader/watchlist.json` (symbol, setup, level, close, stats).

**swing-news** (`news.py`)
- Per symbol: Yahoo headline RSS (`.NS`, `region=IN`) and Google News RSS
  (`"<company name>" share`, `en-IN`), deduped, newest first, in IST, tagged
  (results, dividend/split/bonus, deal, order win, management, regulatory /
  SEBI, block deal, rating, macro), only new since the last check.
- Shows each stock's move vs the previous close.
- NSE corporate announcements and results dates: optional source, see Open
  questions.

**swing-entry** (`entry.py check | watchlist`)
- Trigger = a **daily close** above the setup level (with optional volume
  >= N x 20-day average). Intraday pokes do not count.
- Default run after the close (after 15:30 IST; Yahoo is delayed, so the
  tool says when the daily bar is final). `--pre-close` evaluates the
  forming bar at ~15:15 for users who want to enter in the closing minutes,
  and labels it provisional.
- States: waiting (distance to level), triggered (date, close), stale
  (triggered more than N days ago and price ran > X% past the level),
  failed (closed back under).
- Writes `trader/entry.json` with the suggested next-day order: a buy limit
  at the trigger close + buffer, or an SL-buy trigger above the trigger
  bar's high (`--entry-style limit|sl-buy`, default limit).

**swing-exit** (`exit.py plan | show`)
- Stop methods: `swing-low` (lowest low of the last N bars, default),
  `setup-low` (breakout bar / flag low), `atr:K` (entry - K x ATR14 daily,
  default K=2), `pct:X`, `price:X`. Rounded down to tick. Refuses a stop at
  or above entry, or tighter than 0.5 x ATR14 (noise), with the reason.
- Target: `2R` default, `1R`, `3R`, `price:X`. Rounded to tick.
- Time stop: `--max-hold N` trading days (default 15); the plan states the
  calendar date of the last day.
- GTT values: stop trigger and a stop limit set `gtt_slippage_pct` below it
  (default 1%) so a gap-down still fills in normal conditions; the plan says
  plainly that a gap below the limit leaves the order unfilled.
- Writes `trader/plan.json`.

**swing-timemachine** (`timemachine.py run | chart`)
- Monte Carlo: 10,000 paths of `max_hold` daily bars, each bar drawn
  (block bootstrap, block length 5 by default) from the stock's own last 3
  years of daily bars as ratios to the previous close (open, high, low,
  close), so gaps are included. Seeded (default 19).
- Fill rules per bar: if open <= stop, fill at open (gap through the stop);
  else if low <= stop and high >= target in the same bar, count the stop
  (conservative); else stop or target as touched. At the time stop, exit at
  that day's close.
- History: every past day in the last 5 years the same setup rule fired on
  this stock, run with the same stop/target/time-stop rules. Lists each
  trade.
- Output: target first / stop first / time stop %, average R, R
  distribution, median days held, worst gap-through loss, one plain verdict.
  Also flags if a results date falls inside the hold (when known).
- Writes `trader/timemachine.json`; `chart` prints an ASCII fan of paths.

**swing-budget** (`size.py`)
- Config in ₹: `capital`, `risk_per_trade_pct` (default 1%),
  `max_position_pct` (20%), `cash_buffer_pct` (10%), `min_order` (₹1,000).
- Quantity = floor(risk ₹ / (entry - stop)), then capped by position size,
  cash after buffer and open positions' cost. Says which limit decided.
- Adds the charges estimate and the max loss at the stop including
  charges; also the loss at the GTT stop limit (gap scenario).
- Writes `trader/orders.json` (one proposed entry + its GTT OCO).

**swing-risk** (`check.py`)
- PASS / WARN / BLOCK per proposal, reasons in plain words:
  stop required; loss at stop <= max per trade; reward:risk >= min (default
  1.5); open positions < max (default 5); **portfolio heat** (sum of open
  risk to stops + this trade) <= max (default 5% of capital); position cap;
  cash buffer; blocked list; price band 2% / 5% -> BLOCK by default (hard to
  exit), 10% -> WARN; quantity <= 1% of 20-day average volume (liquidity);
  results date inside the hold -> WARN (BLOCK with `"block_on_results":
  true`); no F&O, no short, no margin / MTF, CNC only.
- Records verdicts in `trader/state/risk.json` so the card shows only what
  passed.

**swing-card** (`card.py show | record | close | log`)
- `show`: one card per PASSed proposal, in plain text, ready to type into
  any broker:
  ```
  BUY TCS (NSE) · CNC · 6 shares · LIMIT ₹3,412.40
  GTT OCO  stop trigger ₹3,296.10 / limit ₹3,263.10
           target trigger ₹3,645.00 / limit ₹3,645.00
  Risk at stop ₹697.80 + charges ~₹27 · R:R 2.0 · time stop 2026-12-10
  ```
  Plus a reminder to place the GTT after the buy fills (most brokers
  require holdings before a sell GTT).
- `record`: the user tells Claude what filled (qty, price, date); writes
  `trader/positions.json` and the journal. `close` records an exit and the
  realised R. `log` prints the journal with running stats.
- Nothing in this skill talks to a broker.

**swing-alerts** (`alerts.py add --from-plan | check | clock | quote`)
- Daily, after the close: for each open position, did the bar touch the
  stop or target, did it gap through, is today the time stop, is a results
  date tomorrow, did the price band change. Each alert rings once.
- `clock`: NSE open / closed / next session in IST, today's holiday name.
- `quote --write`: delayed quotes to `trader/prices.json` for sizing and
  risk.

### Data files (`trader/`)

`config.json`, `universe.txt`, `watchlist.json`, `entry.json`,
`plan.json`, `timemachine.json`, `orders.json`, `positions.json`,
`journal.json`, `alerts.json`, `prices.json`, `state/`, `cache/`.
Each is read by the next step, as in the original.

### Tests

- Offline unittest suite, one file per skill plus `test_india.py`.
- Fixtures cut from real data: 5 years of daily bars for two or three NSE
  stocks (one under ₹250 to exercise the 0.01 tick, one with `&` in the
  symbol), an `EQUITY_L.csv` and `sec_list.csv` excerpt, a bhavcopy
  excerpt, Yahoo and Google News RSS samples.
- A README walkthrough with real numbers that the tests reproduce, as the
  original does.

### README and packaging

Rewrite README for the India swing pack (install, the nine skills, the
walkthrough, fine print: not advice, SEBI's finding that most retail F&O and
intraday traders lose money, GTT gap risk, unofficial data, LTCG/STCG and
charges are estimates). Update `.claude-plugin/` manifests. Keep MIT and
credit the original author.

## Builder's calls (made by Claude, open to correction)

- Skill prefix `swing-` instead of `trader-`, to avoid clashing with the
  original pack if both are installed.
- Default max hold 15 trading days; risk 1% per trade; max 5 open
  positions; portfolio heat 5%; min R:R 1.5.
- Universe limited to series EQ by default; 2% / 5% price-band stocks
  excluded from scans and blocked in risk.
- Default stop `swing-low`, target 2R, entry style limit.
- Time Machine uses 3 years of bars for the simulation and 5 years for the
  history.
- Charges defaults assume ₹0 delivery brokerage; the user sets their own.
- Build order: `india/` + tests, then scanner, exit, entry, timemachine,
  budget, risk, card, alerts, news, README.

## NSE API access (decided by the user)

The user chose the `nse` package (PyPI `nse`, BennyThadikaran/NseIndiaApi,
GPL-3.0, pinned `nse==5.2.0`; needs `httpx` and `pyrate-limiter`) for the
data only NSE's site API has. It handles NSE's cookie session and rate limit.

- **Optional dependency.** All tools run on the standard library alone
  (Yahoo + `archives.nseindia.com` static files). With `nse` installed they
  add the features below; without it they say what is missing and carry on.
  The "Python standard library only" goal applies to the core; the
  `requirements-nse.txt` file lists the pin.
- **Isolated in `india/nse_source.py`.** Only this file imports `nse`; every
  call is wrapped, cached under `trader/cache/nse/`, and has an offline
  fixture for tests. The rest of the pack never imports `nse`. Not vendored
  (the repo stays MIT; the GPL package is installed by the user).
- **Uses:**
  - `holidays(type="trading")` -> refreshes `india/holidays.json` (`CM`
    segment) via `python3 -m india.market refresh-holidays`; the JSON file
    stays the source tools read, so they work offline.
  - `board_meetings()` / `financial_results()` -> results dates per symbol
    (risk check, alerts, Time Machine warning).
  - `announcements()` and `actions()` -> swing-news (filings, dividends,
    splits, bonuses, record dates).
  - `priceband_report()` / `delivery_bhavcopy()` -> price bands and
    delivery % (falling back to the static archive files).
  - `block_deals()` / `bulk_deals()` -> optional news items.
- Daily price history stays on Yahoo (one batched source for thousands of
  symbols); `fetch_equity_historical_data()` is a fallback for a single
  symbol when Yahoo fails.
