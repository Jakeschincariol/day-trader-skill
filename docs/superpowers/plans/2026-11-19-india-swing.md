# India Swing Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the US day-trading pack in this fork with nine `swing-*` Claude skills for swing trading NSE/BSE equities, built on one shared `india/` module, ending in a trade card the user types into their own broker.

**Architecture:** `india/` holds everything market-specific (clock, holidays, symbols, ticks, rupees, charges, HTTP + cache + offline fixtures, indicators and setup rules, stop/target rules, the optional `nse` package wrapper). Each `swing-*/` folder is a SKILL.md plus one CLI script that imports `india` and reads/writes JSON files in the user's `trader/` folder, each step reading what the previous one wrote.

**Tech Stack:** Python 3.8+ standard library (`urllib`, `json`, `csv`, `gzip`, `random`, `argparse`, `unittest`); optional `nse==5.2.0` (PyPI, GPL-3.0) only inside `india/nse_source.py`.

**Spec:** `docs/superpowers/specs/2026-11-19-india-swing-design.md`

## Global Constraints

- Python 3.8+: no `zoneinfo`, no `list[...]`/`dict[...]` generics, no `match`, no `removeprefix`. IST = UTC+05:30 fixed offset, no DST.
- Core is standard library only. Only `india/nse_source.py` may import `nse`, inside a `try`; every tool must run with `nse` absent.
- No code path places, modifies or cancels a broker order. No broker API, no API keys.
- NSE regular session 09:15-15:30 IST, Mon-Fri minus holidays in `india/holidays.json`.
- Daily bar for date D is final only after 15:50 IST on D (`BAR_FINAL = 15:50`; 15:30 close + Yahoo delay).
- Prices printed in rupees with Indian grouping: `₹1,23,456.78`.
- HTTP User-Agent `day-trader-skill (+https://github.com/Ibrahimhass/day-trader-skill)`; Yahoo host order query2 then query1.
- Every tool accepts `--now "YYYY-MM-DD HH:MM"` (IST) and `--offline PATH`, plus `--json`.
- Working files live in `./trader/` (override `--dir`): `config.json, universe.txt, watchlist.json, entry.json, plan.json, timemachine.json, orders.json, positions.json, journal.json, alerts.json, prices.json, results.json, state/, cache/`.
- Each SKILL.md: frontmatter `name` = folder name, `description` > 200 chars, body > 60 lines, contains "not financial advice" and states that it never places an order.
- No em dashes (U+2014) outside `tests/fixtures/`.
- Defaults (from spec): risk 1% per trade, max position 20%, cash buffer 10%, min order ₹1,000, min R:R 1.5, max open positions 5, portfolio heat 5%, max hold 15 trading days, stop `swing-low`, target `2R`, entry style `limit`, GTT stop-limit slippage 1%, min price ₹50, min 20-day average traded value ₹5 crore, universe series EQ, price bands 2/5 excluded and BLOCKed, band 10 WARN, Time Machine 10,000 paths, seed 19, block length 5, 3 years simulation / 5 years history.
- Test command for every task: `python3 -m unittest discover -s tests -v`. Tests are offline.
- The original pack is at commit `3d0f4ef`; read old logic with `git show 3d0f4ef:trader-scanner/scan.py` (etc.) when porting (Wilder RSI, bull-flag rule, RSS parsing, bootstrap, fetch retry).

## Review Focus

1. **Symbols with `&` or `-`** (`M&M`, `BAJAJ-AUTO`): must reach Yahoo URL-encoded (`M%26M.NS`), produce safe cache filenames, and pass risk validation. Tests: Task 2 (`test_symbol_round_trip`), Task 3 (`test_cache_filename_safe`), Task 10 (`test_ampersand_symbol_passes`).
2. **Run during market hours**: today's forming daily bar must not count as a close before 15:50 IST. Tests: Task 3 (`test_drop_unfinished_bar`), Task 6 (`test_forming_bar_not_a_trigger`).
3. **`nse` not installed**: every tool runs, prints one line saying which features are off. Tests: Task 4 (`test_missing_package_is_soft`), Task 10 (`test_risk_runs_without_nse`), Task 13 (`test_news_runs_without_nse`).
4. **Year missing from `holidays.json`**: warn once, weekends-only calendar, no crash. Test: Task 1 (`test_missing_year_warns_once`).
5. **Short or gappy history** (new listing < 250 bars, suspended stock): setups needing more history are skipped, Time Machine refuses with a reason instead of crashing. Tests: Task 5 (`test_short_history_skips_52w`), Task 8 (`test_too_little_history_refuses`).

---

### Task 1: Clean slate and the market clock

Remove the US pack, set up the package, and build the IST clock and holiday calendar.

**Files:**
- Delete: all `trader-*/` folders, all `tests/test_*.py`, `tests/fixtures/*` (history stays in git)
- Create: `india/__init__.py`, `india/market.py`, `india/holidays.json`, `.gitignore`, `requirements-nse.txt`
- Modify: `tests/_load.py` (prefix module name `swing_` instead of `trader_`; add `ROOT` to `sys.path` so `import india` works)
- Test: `tests/test_india_market.py`

**Interfaces:**
- Produces (in `india.market`):
  - `IST: datetime.timezone` (UTC+05:30)
  - `OPEN = time(9, 15)`, `CLOSE = time(15, 30)`, `BAR_FINAL = time(15, 50)`
  - `now_ist(pinned: Optional[str] = None) -> datetime` (naive IST; parses `"YYYY-MM-DD HH:MM"`)
  - `load_holidays(path: Optional[str] = None) -> Dict[str, Dict[str, str]]` (year -> {iso date: name})
  - `is_trading_day(d: date) -> bool`
  - `holiday_name(d: date) -> Optional[str]`
  - `session(d: date) -> Optional[Tuple[time, time]]` (None when closed)
  - `market_status(now: datetime) -> Dict` keys `open: bool, reason: str, next_open: str (ISO datetime)`
  - `next_trading_day(d: date) -> date`, `prev_trading_day(d: date) -> date`
  - `add_trading_days(d: date, n: int) -> date`, `trading_days_between(a: date, b: date) -> int` (a exclusive, b inclusive)
  - `last_final_bar_date(now: datetime) -> date` (today if trading day and now >= BAR_FINAL, else previous trading day)
  - `refresh_holidays(source) -> int` (writes holidays.json from `source.trading_holidays()`; returns count; CLI `python3 -m india.market refresh-holidays`)
- `holidays.json` shape: `{"source": "...", "updated": "YYYY-MM-DD", "years": {"2026": {"2026-01-26": "Republic Day", ...}}}`. Seed it in this task with the 2026 NSE CM trading holidays; if the implementer cannot fetch them yet (Task 4 builds the refresher), seed only `2026-01-26` and `2026-08-15`... **no**: leave `years` empty and fill it in Task 4 Step 6 from the live NSE list. Tests use a fixture holiday file, not the shipped one.

- [ ] **Step 1: Delete the US pack and rewrite `tests/_load.py`**

```bash
git rm -r -q trader-* tests/test_*.py tests/fixtures
```
`.gitignore`: `__pycache__/`, `.venv/`, `trader/`. `requirements-nse.txt`: `nse==5.2.0`.

- [ ] **Step 2: Write the failing tests** (`tests/test_india_market.py`, using fixture `tests/fixtures/india/holidays.json` with `{"years": {"2026": {"2026-11-24": "Guru Nanak Jayanti", "2026-12-25": "Christmas"}}}`)

```python
def test_weekend_and_holiday_closed(self):
    self.assertFalse(m.is_trading_day(date(2026, 11, 21)))        # Saturday
    self.assertFalse(m.is_trading_day(date(2026, 11, 24)))        # fixture holiday
    self.assertEqual(m.holiday_name(date(2026, 11, 24)), "Guru Nanak Jayanti")
    self.assertTrue(m.is_trading_day(date(2026, 11, 23)))

def test_add_trading_days_skips_holidays(self):
    self.assertEqual(m.add_trading_days(date(2026, 11, 20), 2), date(2026, 11, 25))
    self.assertEqual(m.trading_days_between(date(2026, 11, 20), date(2026, 11, 25)), 2)

def test_market_status(self):
    s = m.market_status(datetime(2026, 11, 23, 9, 14))
    self.assertFalse(s["open"]); self.assertEqual(s["next_open"], "2026-11-23T09:15")
    self.assertTrue(m.market_status(datetime(2026, 11, 23, 9, 15))["open"])
    self.assertFalse(m.market_status(datetime(2026, 11, 23, 15, 30))["open"])
    self.assertEqual(m.market_status(datetime(2026, 11, 23, 16, 0))["next_open"], "2026-11-25T09:15")

def test_last_final_bar_date(self):
    self.assertEqual(m.last_final_bar_date(datetime(2026, 11, 23, 15, 49)), date(2026, 11, 20))
    self.assertEqual(m.last_final_bar_date(datetime(2026, 11, 23, 15, 50)), date(2026, 11, 23))

def test_missing_year_warns_once(self):
    with captured_stderr() as err:
        self.assertTrue(m.is_trading_day(date(2027, 1, 26)))       # no 2027 list: weekdays open
        m.is_trading_day(date(2027, 1, 27))
    self.assertEqual(err.getvalue().count("no NSE holiday list for 2027"), 1)

def test_now_ist_pinned(self):
    self.assertEqual(m.now_ist("2026-11-18 16:00"), datetime(2026, 11, 18, 16, 0))
```
The module reads the holiday file path from env `INDIA_HOLIDAYS` (tests set it) else `india/holidays.json`; `load_holidays` caches per path, and tests reset with `m._reset()`.

- [ ] **Step 3: Run tests, expect FAIL** (`ModuleNotFoundError: india`)

- [ ] **Step 4: Implement `india/market.py`** per the interface above. `now_ist(None)` = `datetime.utcnow() + 5h30m`. Warning text: `"warning: no NSE holiday list for %d in india/holidays.json; treating only weekends as closed (run: python3 -m india.market refresh-holidays)"`, printed once per year per process.

- [ ] **Step 5: Run tests, expect PASS**

- [ ] **Step 6: Commit** `git commit -m "Replace US pack with india.market: IST clock and NSE calendar"`

---

### Task 2: Symbols, ticks, rupees, charges

**Files:**
- Create: `india/symbols.py`, `india/ticks.py`, `india/money.py`, `india/charges.py`
- Test: `tests/test_india_basics.py`

**Interfaces:**
- `india.symbols`:
  - `Sym = NamedTuple("Sym", [("code", str), ("exchange", str)])` (exchange `"NSE"` or `"BSE"`)
  - `parse(text: str, default_exchange: str = "NSE") -> Sym` accepts `TCS`, `tcs`, `TCS.NS`, `NSE:TCS`, `RELIANCE.BO`, `BSE:RELIANCE`, `M&M`; raises `ValueError` with the reason otherwise
  - `VALID = re.compile(r"^[A-Z0-9&\-]{1,20}$")`
  - `to_yahoo(s: Sym) -> str` (`"M&M.NS"`, unencoded) and `yahoo_path_part(s: Sym) -> str` (`urllib.parse.quote(to_yahoo(s), safe=".")` -> `"M%26M.NS"`)
  - `display(s: Sym) -> str` (`"M&M"` for NSE, `"RELIANCE (BSE)"` for BSE)
  - `safe_filename(s: Sym) -> str` (`"M_and_M.NS"`, only `[A-Za-z0-9._-]`)
- `india.ticks`:
  - `DEFAULT_SCHEDULE = [(250, 1), (1000, 5), (5000, 10), (10000, 50), (20000, 100), (None, 500)]` (upper price bound exclusive, tick in paise)
  - `tick_paise(price: float, schedule=None) -> int`
  - `round_down(price: float, schedule=None) -> float`, `round_up(...)`, `round_nearest(...)` (all computed in integer paise, return float with 2 dp)
  - `is_valid(price: float, schedule=None) -> bool`
- `india.money`: `inr(x: float, decimals: int = 2) -> str` (`inr(123456.785)` -> `"₹1,23,456.79"`, `inr(-697.8)` -> `"-₹697.80"`, `inr(1500, 0)` -> `"₹1,500"`); `crore(x) -> str` (`crore(5e7)` -> `"₹5.00 cr"`), `lakh(x)`.
- `india.charges`:
  - `DEFAULTS = {"last_checked": "2026-11-19", "brokerage_per_order": 0.0, "stt_pct": 0.1, "exchange_txn_pct": 0.00297, "sebi_per_crore": 10.0, "stamp_buy_pct": 0.015, "gst_pct": 18.0, "dp_per_sell": 15.93}`
  - `delivery_round_trip(buy_value: float, sell_value: float, table: Optional[Dict] = None) -> Dict` keys `brokerage, stt, exchange, sebi, stamp, gst, dp, total` (each rounded to 2 dp; STT on buy and sell value; exchange and SEBI on both legs; stamp on buy; GST 18% on brokerage + exchange + SEBI; DP once on sell)

- [ ] **Step 1: Write failing tests**

```python
def test_symbol_round_trip(self):
    s = symbols.parse("M&M")
    self.assertEqual(s, symbols.Sym("M&M", "NSE"))
    self.assertEqual(symbols.yahoo_path_part(s), "M%26M.NS")
    self.assertEqual(symbols.parse("NSE:BAJAJ-AUTO"), symbols.Sym("BAJAJ-AUTO", "NSE"))
    self.assertEqual(symbols.to_yahoo(symbols.parse("RELIANCE.BO")), "RELIANCE.BO")
    self.assertEqual(symbols.safe_filename(s), "M_and_M.NS")
    with self.assertRaises(ValueError): symbols.parse("TCS 2")
    with self.assertRaises(ValueError): symbols.parse("NIFTY24DECFUT.NFO")

def test_tick_rounding(self):
    self.assertEqual(ticks.round_down(249.987), 249.98)       # < 250: 0.01
    self.assertEqual(ticks.round_down(358.32), 358.30)        # 250-1000: 0.05
    self.assertEqual(ticks.round_up(358.32), 358.35)
    self.assertEqual(ticks.round_down(3296.17), 3296.10)      # 1000-5000: 0.10
    self.assertEqual(ticks.round_up(7001.0), 7001.50)         # 5000-10000: 0.50
    self.assertTrue(ticks.is_valid(3296.10)); self.assertFalse(ticks.is_valid(3296.15))

def test_inr_grouping(self):
    self.assertEqual(money.inr(123456.785), "₹1,23,456.79")
    self.assertEqual(money.inr(-697.8), "-₹697.80")
    self.assertEqual(money.inr(1500, 0), "₹1,500")
    self.assertEqual(money.crore(5e7), "₹5.00 cr")

def test_delivery_charges(self):
    c = charges.delivery_round_trip(100000.0, 110000.0)
    self.assertEqual(c["stt"], 210.0)
    self.assertEqual(c["stamp"], 15.0)
    self.assertEqual(c["dp"], 15.93)
    self.assertAlmostEqual(c["exchange"], 6.24, places=2)
    self.assertAlmostEqual(c["total"], c["brokerage"] + c["stt"] + c["exchange"] + c["sebi"] + c["stamp"] + c["gst"] + c["dp"], places=2)
```

- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement the four modules** per the interfaces. The tick schedule is overridable by passing `schedule` (later tools pass `config.get("tick_schedule")`). Add a module docstring in `ticks.py` saying the schedule follows NSE's 2025 revision and must be re-checked against the current NSE circular.
- [ ] **Step 4: Run, expect PASS**
- [ ] **Step 5: Commit** `git commit -m "india: symbols, NSE tick sizes, rupee format, delivery charges"`

---

### Task 3: Data layer and real fixtures

**Files:**
- Create: `india/data.py`, `india/config.py`, `tests/capture_fixtures.py` (network; never imported by tests)
- Create fixtures: `tests/fixtures/india/yahoo/{TCS.NS,M_and_M.NS,IDEA.NS,RELIANCE.NS}-5y.json.gz`, `tests/fixtures/india/spark-1y.json.gz` (20 NSE symbols incl. the four), `tests/fixtures/india/EQUITY_L-excerpt.csv`, `tests/fixtures/india/sec_list-excerpt.csv`, `tests/fixtures/india/bhav-18112026-excerpt.csv`, `tests/fixtures/india/holidays.json` (from Task 1)
- Test: `tests/test_india_data.py`

**Interfaces:**
- `Bar` = `Dict` with keys `d: "YYYY-MM-DD"` (IST date), `o, h, l, c: float`, `v: int`. Lists are oldest first.
- `india.data`:
  - `class Fetcher(cache_dir: Optional[str], offline: Optional[str] = None, pause: float = 0.3, ttl: int = 900)` with `get(url: str, cache_key: str) -> bytes`. Offline mode: `offline` is a file or folder; `cache_key` names the file inside a folder (`.gz` read transparently); never touches the network. Retries once on 429/5xx after `pause * 10` seconds; for Yahoo URLs falls back query2 -> query1.
  - `yahoo_daily(f: Fetcher, s: Sym, rng: str = "5y") -> List[Bar]` (v8 chart `interval=1d`; drops bars with null close; dates from timestamp + `gmtoffset`)
  - `yahoo_spark(f: Fetcher, syms: List[Sym], rng: str = "1y") -> Dict[str, List[Bar]]` (v7 spark, 20 per request, closes only so `o=h=l=c`, `v=0`; key `Sym.code`)
  - `drop_unfinished(bars: List[Bar], now: datetime) -> List[Bar]` (drops bars dated after `last_final_bar_date(now)`)
  - `nse_equity_list(f: Fetcher) -> List[Dict]` from `https://archives.nseindia.com/content/equities/EQUITY_L.csv` (keys `symbol, name, series, isin`, header whitespace stripped)
  - `nse_price_bands(f: Fetcher) -> Dict[str, str]` from `.../content/equities/sec_list.csv` (symbol -> `"2"|"5"|"10"|"20"|"-"`)
  - `nse_delivery(f: Fetcher, d: date) -> Dict[str, float]` from `https://archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv` (symbol -> DELIV_PER for series EQ; `{}` on 404)
- `india.config`: `load(trader_dir: str) -> Dict` (merges `trader/config.json` over `DEFAULTS` holding every default in Global Constraints, keys: `capital, cash, risk_per_trade_pct, max_position_pct, cash_buffer_pct, min_order, min_reward_risk, max_open_positions, max_heat_pct, max_hold_days, stop_method, target, entry_style, entry_limit_buffer_pct, gtt_slippage_pct, min_price, min_traded_value, include_be, block_bands, warn_bands, block_on_results, blocked, tick_schedule, charges`); `trader_path(trader_dir, name) -> str` (creates parent dirs).

- [ ] **Step 1: Write `tests/capture_fixtures.py`** (argparse `--date 2026-11-18`): downloads the files listed above with `india.data.Fetcher(cache_dir=None)`, trims CSVs to the header plus rows for the 20 fixture symbols, gzips JSON. The 20 symbols: `TCS, M&M, IDEA, RELIANCE, INFY, HDFCBANK, ICICIBANK, SBIN, ITC, LT, BAJAJ-AUTO, TATAMOTORS, SUZLON, YESBANK, IRFC, ZOMATO, ADANIENT, BHARTIARTL, SUNPHARMA, TITAN` (replace any that Yahoo no longer serves and note it in the script). Pin `--range 5y` for the four detailed stocks. Confirm at least one of them closed under ₹250 on the capture date (for the 0.01 tick) and print a warning otherwise.

- [ ] **Step 2: Write failing tests** (`test_india_data.py`, offline only)

```python
def test_yahoo_daily_offline(self):
    bars = data.yahoo_daily(self.f, symbols.parse("TCS"))
    self.assertGreater(len(bars), 1200)
    self.assertEqual(set(bars[-1]), {"d", "o", "h", "l", "c", "v"})
    self.assertTrue(all(a["d"] < b["d"] for a, b in zip(bars, bars[1:])))

def test_drop_unfinished_bar(self):
    bars = [{"d": "2026-11-17", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1},
            {"d": "2026-11-18", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]
    self.assertEqual(len(data.drop_unfinished(bars, datetime(2026, 11, 18, 14, 0))), 1)
    self.assertEqual(len(data.drop_unfinished(bars, datetime(2026, 11, 18, 16, 0))), 2)

def test_cache_filename_safe(self):
    self.assertNotIn("&", data.cache_key_for("chart", symbols.parse("M&M"), "5y"))

def test_equity_list_and_bands(self):
    eq = data.nse_equity_list(self.f)
    self.assertIn("TCS", {r["symbol"] for r in eq})
    self.assertIn(data.nse_price_bands(self.f).get("TCS"), ("2", "5", "10", "20", "-"))

def test_offline_never_hits_network(self):
    with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
        data.yahoo_daily(self.f, symbols.parse("M&M"))
```
Also `data.cache_key_for(kind: str, s: Sym, rng: str) -> str` (`"chart-M_and_M.NS-5y.json"`), the name offline folders use.

- [ ] **Step 3: Run, expect FAIL**
- [ ] **Step 4: Implement `india/data.py` and `india/config.py`**; port retry/pause from `git show 3d0f4ef:trader-scanner/scan.py`.
- [ ] **Step 5: Run `python3 tests/capture_fixtures.py --date 2026-11-18`** (network) and confirm the fixture files exist and are under 3 MB total.
- [ ] **Step 6: Run tests, expect PASS**
- [ ] **Step 7: Commit** `git commit -m "india: data layer, config defaults, real NSE fixtures"`

---

### Task 4: Optional `nse` source and holiday refresh

**Files:**
- Create: `india/nse_source.py`, fixtures `tests/fixtures/india/nse/{holidays,board_meetings,actions,announcements}.json`
- Modify: `india/holidays.json` (filled from live data in Step 6)
- Test: `tests/test_india_nse.py`

**Interfaces:**
- `class NseSource(cache_dir: str, client_factory: Optional[Callable] = None, offline: Optional[str] = None)`
  - `available: bool` and `why_unavailable: str` (`"nse package not installed (pip install -r requirements-nse.txt)"`)
  - `trading_holidays() -> Dict[str, str]` (iso date -> name, `CM` segment)
  - `results_dates(symbols: List[str], start: date, end: date) -> Dict[str, List[str]]` (from `board_meetings(symbol=..., from_date, to_date)`, keeping meetings whose purpose mentions "Financial Results"; iso dates)
  - `corporate_actions(symbols: List[str], start: date, end: date) -> Dict[str, List[Dict]]` (keys `ex_date, purpose`)
  - `announcements(symbol: str, start: date, end: date) -> List[Dict]` (keys `time_ist, subject, text, url`)
- Each method: returns `{}`/`[]` when unavailable; caches JSON under `cache_dir/nse/` for 6 hours; wraps every call in `try` and returns empty plus records `last_error`.
- `client_factory()` default: `from nse import NSE; return NSE(download_folder=cache_dir)` (used as a context manager). Tests pass a fake.
- `soft_notice(src: NseSource) -> Optional[str]`: one line for tools to print when unavailable.

- [ ] **Step 1: Write failing tests** with a `FakeNSE` returning the fixture JSON (fixture shapes copied from the package's `src/samples/*.json` on GitHub for `holidays`, `board_meetings`, `actions`, `announcements`).

```python
def test_missing_package_is_soft(self):
    with mock.patch.dict(sys.modules, {"nse": None}):
        src = nse_source.NseSource(self.tmp)
    self.assertFalse(src.available)
    self.assertEqual(src.results_dates(["TCS"], date(2026, 11, 1), date(2026, 12, 31)), {})
    self.assertIn("pip install", nse_source.soft_notice(src))

def test_results_dates_filters_purpose(self):
    src = nse_source.NseSource(self.tmp, client_factory=lambda: FakeNSE())
    out = src.results_dates(["TCS"], date(2026, 1, 1), date(2026, 12, 31))
    self.assertTrue(all(len(d) == 10 for d in out.get("TCS", [])))

def test_client_error_returns_empty(self):
    src = nse_source.NseSource(self.tmp, client_factory=lambda: BrokenNSE())
    self.assertEqual(src.trading_holidays(), {})
    self.assertTrue(src.last_error)

def test_refresh_holidays_writes_file(self):
    n = market.refresh_holidays(nse_source.NseSource(self.tmp, client_factory=lambda: FakeNSE()), path=self.tmp_holidays)
    self.assertGreater(n, 5)
```
(`refresh_holidays` gains a `path` kwarg here.)

- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement `india/nse_source.py`** and wire `market.refresh_holidays`.
- [ ] **Step 4: Run, expect PASS**
- [ ] **Step 5: Commit** `git commit -m "india: optional nse package source and holiday refresh"`
- [ ] **Step 6: Fill the real holiday list**: `python3 -m venv .venv && .venv/bin/pip install -r requirements-nse.txt && .venv/bin/python -m india.market refresh-holidays`. Check `india/holidays.json` has 2026 dates (and 2027 if NSE has published). Commit `git commit -m "Seed NSE trading holidays from NSE"`. If NSE refuses the request, stop and report to the user; do not hand-type dates.

---

### Task 5: Indicators, setups and swing-scanner

**Files:**
- Create: `india/indicators.py`, `swing-scanner/SKILL.md`, `swing-scanner/scan.py`
- Test: `tests/test_indicators.py`, `tests/test_scanner.py`

**Interfaces:**
- `india.indicators`:
  - `sma(values: List[float], n: int) -> List[Optional[float]]`, `rsi_wilder(closes, n=14) -> List[Optional[float]]` (port from `3d0f4ef`), `atr(bars, n=14) -> List[Optional[float]]` (Wilder), `avg_traded_value(bars, n=20, i=-1) -> Optional[float]` (mean of c*v)
  - `SETUPS = ("breakout_20d", "breakout_52w", "bull_flag", "reclaim_ma20", "pullback_ma50", "oversold", "oversold_bounce")`
  - `setups_at(bars: List[Bar], i: int) -> Dict[str, Optional[float]]`: setups that fire on bar `i`, each mapped to its trigger level (None for `oversold`, which is watch-only). Rules:
    - `breakout_20d`: `c[i] > max(c[i-20:i])`; level `max(c[i-20:i])`; needs 21 bars
    - `breakout_52w`: `c[i] > max(h[i-250:i])`; level that max; needs 251 bars
    - `bull_flag`: `c[i-5] / c[i-15] - 1 > 0.10` and `max(c[i-4:i+1]) / min(c[i-4:i+1]) - 1 <= 0.05`; level `max(h[i-4:i+1])`
    - `reclaim_ma20`: `c[i-1] < sma20[i-1]` and `c[i] > sma20[i]`; level `h[i]`
    - `pullback_ma50`: `sma50[i] > sma50[i-10]`, `l[i] <= sma50[i] * 1.02`, `c[i] > sma50[i]`; level `h[i]`
    - `oversold`: `rsi14[i] < 30`; level None
    - `oversold_bounce`: `rsi14[i-1] < 30` and `c[i] > c[i-1]`; level `h[i]`
- `swing-scanner/scan.py` CLI: `universe [--include-be]` -> `trader/universe.txt` (one code per line, series EQ, plus BE with the flag); `daily [--symbols A,B] [--limit N] [--min-price] [--min-traded-value] [--bands-ok 10,20,-]` -> `trader/watchlist.json`.
  - Daily scan: stage 1 spark closes (1y) for the universe applying min price and closes-only setups (`breakout_20d`, `breakout_52w` on closes, `reclaim_ma20`, `oversold`, `oversold_bounce`, `bull_flag` on closes); stage 2 v8 daily (1y) for candidates (max `--max-confirm 200`, ranked by last c*v) to confirm with OHLC rules, traded value and price band (`2`,`5` excluded by default). Delivery % from `nse_delivery` for the last final date as a column (blank if unavailable).
  - `watchlist.json`: `{"generated": iso, "as_of": "YYYY-MM-DD", "hits": [{"symbol", "exchange", "setup", "level", "close", "traded_value", "band", "delivery_pct"}], "notes": [...]}`.
- Importing `india` from a skill script: `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` at the top of every script.

- [ ] **Step 1: Write failing tests**

```python
def test_rsi_matches_known_series(self):   # 14-period Wilder on a fixed 30-close list; expected values computed once by hand/spreadsheet and pasted
    ...
def test_breakout_20d_level(self):
    bars = flat_bars(20, c=100) + [bar(c=101, h=102)]
    self.assertEqual(ind.setups_at(bars, 20)["breakout_20d"], 100)
def test_short_history_skips_52w(self):
    bars = flat_bars(100, c=100) + [bar(c=150, h=151)]
    self.assertNotIn("breakout_52w", ind.setups_at(bars, 100))
def test_scan_daily_offline(self):        # spark + chart fixtures, --now "2026-11-18 16:00"
    out = run_scan(["daily", "--offline", FIX, "--now", "2026-11-18 16:00", "--json"])
    self.assertEqual(out["as_of"], "2026-11-18")
    for h in out["hits"]:
        self.assertIn(h["setup"], ind.SETUPS); self.assertNotIn(h["band"], ("2", "5"))
def test_universe_series_filter(self):
    syms = run_scan(["universe", "--offline", FIX, "--json"])["symbols"]
    self.assertIn("TCS", syms)
def test_scan_mid_session_uses_yesterday(self):
    out = run_scan(["daily", "--offline", FIX, "--now", "2026-11-18 11:00", "--json"])
    self.assertEqual(out["as_of"], "2026-11-17")
```
Pin the hit list for the fixture date in `test_scan_daily_offline` after the first green run (assert the exact `[(symbol, setup)]` list) so the README walkthrough can quote it.

- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement `india/indicators.py` and `swing-scanner/scan.py`**
- [ ] **Step 4: Write `swing-scanner/SKILL.md`** (frontmatter per Global Constraints; commands; what it reads/writes; "a scan is a list of charts that match a rule, not a list of stocks to buy"; next step `/swing-news`).
- [ ] **Step 5: Run, expect PASS**
- [ ] **Step 6: Commit** `git commit -m "swing-scanner: NSE universe and daily swing setups"`

---

### Task 6: swing-entry

**Files:** Create `swing-entry/SKILL.md`, `swing-entry/entry.py`; Test `tests/test_entry.py`

**Interfaces:**
- Consumes: `india.indicators.setups_at`, `india.data.yahoo_daily`, `drop_unfinished`, `india.ticks`, `india.config`, `india.market`
- CLI: `entry.py check SYMBOL [--setup NAME | --level PRICE] [--min-volume-x X] [--pre-close] [--entry-style limit|sl-buy] [--write]`; `entry.py watchlist [--write]` (checks every hit in `trader/watchlist.json`).
- `evaluate(bars: List[Bar], level: float, since: str, now: datetime, cfg: Dict, pre_close: bool = False) -> Dict` keys:
  - `state`: `"waiting" | "triggered" | "stale" | "failed"`
  - `trigger_date`, `trigger_close`, `trigger_high`, `distance_pct`, `provisional: bool`, `reason: str`
  - `order`: for triggered only: `{"style": "limit", "price": round_up(trigger_close * (1 + entry_limit_buffer_pct/100))}` (default buffer 0.5) or `{"style": "sl-buy", "trigger": round_up(trigger_high) + one tick, "price": round_up(trigger * 1.005)}`; `"valid_for": next_trading_day(trigger_date)`
  - Rules: first bar after `since` with `c > level` (and `v >= min_volume_x * avg20 volume` if set) is the trigger; `stale` if more than 2 trading days since the trigger or last close > level * 1.03; `failed` if a later close is back under level.
- `entry.json`: `{"symbol", "exchange", "setup", "level", "state", "trigger_date", "trigger_close", "trigger_high", "order", "as_of", "provisional"}`.
- `--pre-close` keeps today's forming bar (only between 15:00 and 15:30 IST) and sets `provisional: true`.

- [ ] **Step 1: Write failing tests**

```python
def test_triggered_on_close_not_wick(self):
    bars = base + [bar("2026-11-17", h=105, c=99), bar("2026-11-18", h=104, c=101)]
    r = entry.evaluate(bars, level=100, since="2026-11-16", now=AFTER_CLOSE, cfg=CFG)
    self.assertEqual((r["state"], r["trigger_date"]), ("triggered", "2026-11-18"))
def test_forming_bar_not_a_trigger(self):
    r = entry.evaluate(bars_with_today_above, level=100, since=..., now=datetime(2026, 11, 18, 14, 0), cfg=CFG)
    self.assertEqual(r["state"], "waiting")
def test_pre_close_is_provisional(self): ...   # now 15:15, pre_close=True -> triggered, provisional True
def test_stale_after_run_up(self): ...          # last close 104 vs level 100 -> stale
def test_failed_back_under(self): ...
def test_limit_price_on_tick(self):
    self.assertTrue(ticks.is_valid(r["order"]["price"]))
def test_check_offline_writes_entry_json(self): ...   # TCS fixture, --level from fixture data, --write -> trader/entry.json
```
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Implement `entry.py`**; **Step 4:** write SKILL.md (daily close rule, run after 15:50 IST, `--pre-close` caveat, next `/swing-exit`)
- [ ] **Step 5: Run, expect PASS**; **Step 6: Commit** `git commit -m "swing-entry: daily-close triggers with next-day order"`

---

### Task 7: Stop/target rules and swing-exit

**Files:** Create `india/levels.py`, `swing-exit/SKILL.md`, `swing-exit/exit.py`; Test `tests/test_exit.py`

**Interfaces:**
- `india.levels`:
  - `compute_stop(bars: List[Bar], i: int, entry: float, method: str, schedule=None) -> Tuple[float, str]` (price, how-it-was-computed text). Methods: `swing-low[:N]` (min low of bars `i-N+1..i`, N default 10), `setup-low` (low of bar `i`), `atr:K` (`entry - K * atr14[i]`), `pct:X`, `price:X`. Always `ticks.round_down`. Raises `PlanError` if stop >= entry or `entry - stop < 0.5 * atr14[i]`.
  - `compute_target(entry: float, stop: float, spec: str, schedule=None) -> float` (`"1R"|"2R"|"3R"|"price:X"`, `ticks.round_nearest`; `PlanError` if <= entry)
  - `gtt_stop_limit(stop: float, slippage_pct: float, schedule=None) -> float` (`round_down(stop * (1 - pct/100))`)
  - `class PlanError(ValueError)`
- `exit.py plan [--entry PRICE] [--stop METHOD] [--target SPEC] [--max-hold N] [--write]` reads `trader/entry.json` (entry price = `order.price` unless `--entry`), `show`.
- `plan.json`: `{"symbol", "exchange", "setup", "entry", "entry_date" (= order.valid_for), "stop", "stop_how", "gtt_stop_limit", "target", "risk_per_share", "reward_risk", "max_hold_days", "time_stop_date", "atr14", "as_of"}`.

- [ ] **Step 1: Write failing tests**: `test_swing_low_rounded_down_to_tick`, `test_atr_stop`, `test_refuses_stop_above_entry`, `test_refuses_noise_tight_stop` (risk 0.3 x ATR -> PlanError naming "0.5 x ATR"), `test_target_2r` (`entry 3412.40, stop 3296.10 -> 3645.00`), `test_gtt_limit` (`3296.10, 1% -> 3263.10`), `test_time_stop_skips_holiday` (uses fixture holidays: entry 2026-11-20, 2 days -> 2026-11-25), `test_plan_offline_writes_plan_json`.
- [ ] **Step 2: Run, expect FAIL**; **Step 3:** implement; **Step 4:** SKILL.md (stop is a plan not a guarantee; GTT gap note; next `/swing-timemachine`)
- [ ] **Step 5: Run, expect PASS**; **Step 6: Commit** `git commit -m "swing-exit: swing stops, R targets, GTT values, time stop"`

---

### Task 8: swing-timemachine

**Files:** Create `swing-timemachine/SKILL.md`, `swing-timemachine/timemachine.py`; Test `tests/test_timemachine.py`

**Interfaces:**
- Consumes: `plan.json` (Task 7), `india.levels.compute_stop/compute_target`, `india.indicators.setups_at`, `india.data.yahoo_daily`.
- `simulate(bars: List[Bar], entry: float, stop: float, target: float, days: int, n: int = 10000, seed: int = 19, block: int = 5, lookback: int = 756) -> Dict` keys `target_pct, stop_pct, time_pct, gap_through_pct, avg_r, median_days, r_hist (Dict[str, int] buckets "-2..-1.5" ... ), worst_r, paths_sample (20 closing paths)`.
  - Ratios from the last `lookback` bars: `(o/pc, h/pc, l/pc, c/pc)` with `pc` = previous close. Each path: start `prev_close = entry`; draw a random start index, take `block` consecutive ratio rows, repeat until `days` rows; apply each row to `prev_close`.
  - Per simulated day, in order: if `open <= stop`: exit at open (gap-through, counts as stop and gap); elif `open >= target`: exit at open (counts as target); elif `low <= stop`: exit at stop (if `high >= target` too, still stop); elif `high >= target`: exit at target; at day `days` with no exit: exit at close (time stop). R = (exit - entry) / (entry - stop).
  - Uses `random.Random(seed)` only.
- `history(bars, setup, stop_method, target_spec, days, years: int = 5) -> Dict` keys `fired, target, stop, time, avg_r, trades: List[{date, entry, stop, target, exit, r, days, outcome}]`: for every bar `i` in the last `years*250` where `setup` in `setups_at(bars, i)`, entry = next bar's open, stop via `compute_stop(bars, i, entry, stop_method)` (skip the event if it raises `PlanError`), target via `compute_target`, then walk the real following bars with the same per-day rules. Skip fires whose `i+1+days` runs past the data.
- `run` CLI: `timemachine.py run [--n 10000] [--seed 19] [--write] [--json]` (reads plan.json); `chart` (ASCII fan of `paths_sample` from `trader/timemachine.json`). Verdict string thresholds: `avg_r` over simulation and history both > 0.2 -> "edge in its own history"; both between -0.2 and 0.2 -> "close to a coin flip"; else "history is against it". If `nse` source gives a results date between `entry_date` and `time_stop_date`, print `"Results due YYYY-MM-DD, inside this hold: these odds do not include a results move."`.
- Refuses (exit code 2, message) if fewer than `lookback // 2` bars: `"only N daily bars for SYMBOL; the Time Machine needs at least 378"`.

- [ ] **Step 1: Write failing tests**

```python
def test_gap_through_fills_at_open(self):
    r = tm.walk_day(entry=100, stop=95, target=110, o=90, h=92, l=89, c=91)
    self.assertEqual(r, ("stop", 90.0, True))
def test_same_bar_both_counts_stop(self):
    self.assertEqual(tm.walk_day(100, 95, 110, o=100, h=111, l=94, c=105)[0], "stop")
def test_seeded_repeatable(self):
    a = tm.simulate(self.tcs, 3412.40, 3296.10, 3645.00, 15, n=2000)
    b = tm.simulate(self.tcs, 3412.40, 3296.10, 3645.00, 15, n=2000)
    self.assertEqual(a, b)
    self.assertAlmostEqual(a["target_pct"] + a["stop_pct"] + a["time_pct"], 100.0, places=6)
def test_too_little_history_refuses(self): ...      # 200 bars -> SystemExit code 2 with "needs at least 378"
def test_history_counts_add_up(self):
    h = tm.history(self.tcs, "breakout_20d", "swing-low", "2R", 15)
    self.assertEqual(h["fired"], h["target"] + h["stop"] + h["time"])
def test_run_offline_pinned_numbers(self): ...       # plan fixture on TCS, n=10000 seed 19; after first green run, pin target/stop/time pct to 1 dp for the README
```
`walk_day(entry, stop, target, o, h, l, c) -> Optional[Tuple[str, float, bool]]` (outcome, exit price, gapped) is the shared per-day rule used by both `simulate` and `history`.

- [ ] **Step 2: Run, expect FAIL**; **Step 3:** implement (port bootstrap/fan-chart ideas from `git show 3d0f4ef:trader-timemachine/timemachine.py`)
- [ ] **Step 4:** SKILL.md (simulation not prediction; gaps included; results moves not; next `/swing-budget`)
- [ ] **Step 5: Run, expect PASS**; **Step 6: Commit** `git commit -m "swing-timemachine: multi-day bootstrap with gaps, plus setup history"`

---

### Task 9: swing-budget

**Files:** Create `swing-budget/SKILL.md`, `swing-budget/size.py`, `swing-budget/config.example.json`; Test `tests/test_budget.py`

**Interfaces:**
- Consumes: `plan.json`, `positions.json` (shape defined in Task 11; treat missing as no positions), `india.config`, `india.charges`.
- `size(plan: Dict, cfg: Dict, positions: List[Dict]) -> Dict` keys `qty, decided_by ("risk"|"position cap"|"cash"|"min order"), cost, risk_at_stop, risk_at_gtt_limit, charges (Dict from delivery_round_trip at the stop exit), max_loss_incl_charges, reward_risk`. Refuses (`SizeError`) when qty < 1 or cost < `min_order`, saying why.
  - `risk_rupees = capital * risk_per_trade_pct / 100`; `qty_risk = floor(risk_rupees / (entry - stop))`; `qty_cap = floor(capital * max_position_pct/100 / entry)`; cash = `cfg["cash"]` if set else `capital - sum(open position cost)`; `qty_cash = floor((cash - capital * cash_buffer_pct/100) / entry)`; `qty = min(...)`.
- `size.py [--write] [--json]` -> `orders.json`: `{"as_of", "proposals": [{"id": "<symbol>-<entry_date>", "symbol", "exchange", "product": "CNC", "side": "BUY", "qty", "entry_style", "entry_price", "entry_trigger" (sl-buy only), "valid_for", "gtt": {"type": "OCO", "stop_trigger", "stop_limit", "target_trigger", "target_limit"}, "risk_at_stop", "charges_est", "reward_risk", "time_stop_date", "setup"}]}`.
- `config.example.json`: every key of `india.config.DEFAULTS` with `"capital": 500000`.

- [ ] **Step 1: Write failing tests**: `test_risk_decides` (capital 500000, 1%, entry 3412.40, stop 3296.10 -> qty 42, decided_by "risk"), `test_position_cap_decides`, `test_cash_after_open_positions`, `test_refuses_when_one_share_breaks_risk`, `test_charges_included`, `test_orders_json_shape` (all GTT prices valid ticks).
- [ ] **Step 2: Run, expect FAIL**; **Step 3:** implement; **Step 4:** SKILL.md (next `/swing-risk`)
- [ ] **Step 5: Run, expect PASS**; **Step 6: Commit** `git commit -m "swing-budget: rupee sizing with charges and GTT OCO proposal"`

---

### Task 10: swing-risk

**Files:** Create `swing-risk/SKILL.md`, `swing-risk/check.py`; Test `tests/test_risk.py`

**Interfaces:**
- Consumes: `orders.json` (Task 9), `positions.json`, `config`, `india.data.nse_price_bands` (fallback) and `NseSource.results_dates`, `trader/results.json` (manual: `{"TCS": ["2027-01-09"]}`), `india.symbols`, `india.ticks`.
- `check(proposal: Dict, cfg: Dict, positions: List[Dict], bands: Dict[str, str], results: Dict[str, List[str]], avg_volume: Optional[float]) -> Dict` keys `verdict ("PASS"|"WARN"|"BLOCK"), reasons: List[str], fingerprint: str` (sha1 of the proposal JSON with sorted keys).
  - BLOCK: no GTT stop; product not CNC or side not BUY; invalid symbol; any price not on tick; risk_at_stop > capital * risk_per_trade_pct/100 * 1.05; reward_risk < min_reward_risk; open positions >= max_open_positions; heat (sum over positions of `qty * (entry - stop)` where stop below entry, plus this) > capital * max_heat_pct/100; cost > position cap; cash below buffer; symbol in `blocked`; band in `block_bands`; results date inside `[valid_for, time_stop_date]` when `block_on_results`.
  - WARN (verdict WARN if no BLOCK): band in `warn_bands`; results date inside the hold; qty > 1% of 20-day average volume; band or results data unavailable (say which).
- `check.py [--json] [--no-write]` writes `trader/state/risk.json`: `{"date", "verdicts": [{"id", "fingerprint", "verdict", "reasons"}]}`.

- [ ] **Step 1: Write failing tests**: `test_pass_clean_proposal`, `test_block_band_5`, `test_warn_band_10`, `test_block_heat` (4 open positions each risking 1.2% -> heat 4.8% + 1% > 5%), `test_block_max_open_positions`, `test_results_inside_hold_warns_and_blocks_when_configured`, `test_block_off_tick_price`, `test_ampersand_symbol_passes` (`M&M` proposal -> not blocked for symbol), `test_risk_runs_without_nse` (NseSource unavailable -> WARN reason mentions results data unavailable, no crash), `test_fingerprint_changes_with_qty`.
- [ ] **Step 2: Run, expect FAIL**; **Step 3:** implement; **Step 4:** SKILL.md (BLOCK is final; next `/swing-card`)
- [ ] **Step 5: Run, expect PASS**; **Step 6: Commit** `git commit -m "swing-risk: portfolio heat, price bands, results-in-hold, tick checks"`

---

### Task 11: swing-card

**Files:** Create `swing-card/SKILL.md`, `swing-card/card.py`; Test `tests/test_card.py`

**Interfaces:**
- Consumes: `orders.json`, `state/risk.json` (only proposals whose current fingerprint has PASS or WARN verdict today are shown; WARN shows its reasons above the card).
- `render(proposal: Dict, verdict: Dict) -> str`, exact layout:
  ```
  BUY TCS (NSE) · CNC · 42 shares · LIMIT ₹3,412.40 · valid 2026-11-19
  GTT OCO  stop trigger ₹3,296.10 / limit ₹3,263.10
           target trigger ₹3,645.00 / limit ₹3,645.00
  Risk at stop ₹4,884.60 + charges ~₹<x> · R:R 2.0 · time stop 2026-12-10
  Place the GTT after the buy fills: most brokers need the shares in your holdings first.
  ```
  (SL-buy style prints `SL-BUY trigger ₹X / limit ₹Y` in place of `LIMIT ₹X`.)
- `positions.json`: `{"positions": [{"id", "symbol", "exchange", "qty", "entry", "entry_date", "stop", "gtt_stop_limit", "target", "time_stop_date", "setup"}]}`; `journal.json`: `{"trades": [{... position fields, "exit", "exit_date", "exit_reason", "r", "pnl", "charges"}]}`.
- CLI: `card.py show [--json]`; `record --id ID --qty Q --price P [--date D]` (moves a proposal into positions with the actual fill; stop/target unchanged); `close --symbol S --price P [--date D] [--reason stop|target|time|manual]` (R and P&L incl. estimated charges into journal); `log` (trades, win rate, avg R, total P&L).

- [ ] **Step 1: Write failing tests**: `test_card_layout_exact` (string equality with the layout above for a fixture proposal), `test_blocked_proposal_not_shown`, `test_stale_fingerprint_not_shown`, `test_record_then_close_computes_r` (entry 3412.40 stop 3296.10 exit 3645.00 -> r 2.0), `test_no_network_or_broker_imports` (assert `card.py` source contains no `urllib`, `http`, `requests`, `nse`).
- [ ] **Step 2: Run, expect FAIL**; **Step 3:** implement; **Step 4:** SKILL.md (Claude shows the card; the user places the order in their own broker app; nothing here talks to a broker; how to record a fill)
- [ ] **Step 5: Run, expect PASS**; **Step 6: Commit** `git commit -m "swing-card: trade card, fill recording and journal"`

---

### Task 12: swing-alerts

**Files:** Create `swing-alerts/SKILL.md`, `swing-alerts/alerts.py`; Test `tests/test_alerts.py`

**Interfaces:**
- Consumes: `positions.json`, `india.data.yahoo_daily`, `NseSource.results_dates/corporate_actions`, `nse_price_bands`, `india.market`.
- `daily_alerts(position: Dict, bar: Bar, prev_close: float, today: date, results: List[str], actions: List[Dict], band_now: Optional[str], band_before: Optional[str]) -> List[Dict]` each `{"id", "symbol", "kind", "message"}`; kinds: `stop_touched` (`l <= stop`), `gap_through` (`o < stop`), `below_gtt_limit` (`l < gtt_stop_limit`: GTT may not have filled), `target_touched`, `time_stop` (today >= time_stop_date), `results_tomorrow`, `ex_date_tomorrow` (bonus/split/dividend), `band_changed`. `id` = `symbol:kind:date`.
- CLI: `alerts.py check [--json]` (after-close; prints each alert once, state in `trader/state/alerts.json`; exit 0 if something rang, 1 if not); `clock` (market status in IST + today's holiday name); `quote SYMBOLS... [--holdings] [--write]` -> `trader/prices.json` `{"as_of", "prices": {"TCS": {"last", "prev_close", "currency"}}}`.

- [ ] **Step 1: Write failing tests**: `test_gap_through_and_gtt_limit`, `test_time_stop_rings_once` (second `check` on same state prints nothing), `test_results_tomorrow`, `test_ex_date_tomorrow`, `test_clock_holiday` (fixture holiday 2026-11-24 -> closed, reason names it), `test_check_before_bar_final_uses_previous_day` (now 14:00 -> evaluates previous final bar and says so).
- [ ] **Step 2: Run, expect FAIL**; **Step 3:** implement; **Step 4:** SKILL.md (an alert is information, never an order; suggest scheduling `check` daily after 15:50 IST via `/schedule` or cron)
- [ ] **Step 5: Run, expect PASS**; **Step 6: Commit** `git commit -m "swing-alerts: after-close checks on stops, targets, time stops, events"`

---

### Task 13: swing-news

**Files:** Create `swing-news/SKILL.md`, `swing-news/news.py`; fixtures `tests/fixtures/india/rss/{yahoo-TCS.NS,google-TCS}.xml` (captured by adding a `--rss` option to `tests/capture_fixtures.py`); Test `tests/test_news.py`

**Interfaces:**
- Consumes: `watchlist.json`, `plan.json`, `positions.json` (ticker set when `--tickers` absent), `india.data.Fetcher`, `NseSource.announcements/corporate_actions/results_dates`, company names from `nse_equity_list`.
- Feeds: Yahoo `https://feeds.finance.yahoo.com/rss/2.0/headline?s=<to_yahoo>&region=IN&lang=en-IN`; Google News `https://news.google.com/rss/search?q=%22<company name>%22+share&hl=en-IN&gl=IN&ceid=IN:en`.
- `TAGS = ("results", "dividend", "split/bonus", "deal", "order win", "management", "regulatory", "block deal", "rating", "macro")` with keyword lists (`results`: "q1|q2|q3|q4|quarterly|results|profit|revenue|earnings"; `regulatory`: "sebi|rbi|penalty|probe|ban"; `order win`: "order|contract|bags|wins"; etc.).
- `collect(...) -> List[Dict]` items `{"symbol", "time_ist", "source" ("yahoo"|"google"|"nse"), "title", "url", "tags"}`, deduped by normalised title, newest first, filtered to `--hours` (default 24), only unseen (state `trader/state/news.json`, keyed by sha1 of url+title).
- Output also shows each symbol's move vs previous close (from `yahoo_daily` last two final bars) and, when NSE data is available, upcoming results/ex-dates in the next 15 trading days.
- CLI: `news.py [--tickers A B] [--hours 24] [--no-nse] [--json] [--all]` (`--all` ignores seen state).

- [ ] **Step 1: Write failing tests**: `test_parses_both_feeds`, `test_dedupes_same_headline_across_sources`, `test_tags_results_and_regulatory`, `test_times_in_ist`, `test_seen_items_not_repeated`, `test_news_runs_without_nse` (prints the soft notice once, still shows RSS items).
- [ ] **Step 2: Run, expect FAIL**; **Step 3:** implement (port RSS parsing from `git show 3d0f4ef:trader-news/news.py`)
- [ ] **Step 4:** SKILL.md (next `/swing-entry`)
- [ ] **Step 5: Run, expect PASS**; **Step 6: Commit** `git commit -m "swing-news: Indian RSS, NSE announcements, results and ex-dates"`

---

### Task 14: README, packaging and repo test

**Files:**
- Rewrite: `README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
- Create: `tests/test_repo.py`

**Interfaces:**
- `SKILLS = ["swing-scanner", "swing-news", "swing-entry", "swing-exit", "swing-timemachine", "swing-budget", "swing-risk", "swing-card", "swing-alerts"]`
- `ABOUT = "9 Claude skills for swing trading Indian stocks: scan NSE charts, track news and results, plan entry, stop and target, replay the odds, size in rupees, and print a trade card you place yourself."`
- Plugin `name`: `"india-swing-skill"`, `skills: "./"`, author Ibrahim Hassan with `url` `https://github.com/Ibrahimhass`, credit line to the original in `description`? No: keep `description` = `ABOUT`; credit goes in README.

- [ ] **Step 1: Write failing `tests/test_repo.py`** (adapt `git show 3d0f4ef:tests/test_repo.py`): nine skill folders; root entries exactly `.claude-plugin, .gitignore, LICENSE, README.md, docs, india, requirements-nse.txt, tests` + SKILLS; frontmatter checks; every SKILL.md contains "not financial advice" and "never places"; manifests match `ABOUT` and names; README starts `# India Swing skill`, contains `ABOUT`, every `/swing-*`, `## Fine print`, `pip install -r requirements-nse.txt`, and copy-install instructions that copy `india/` too (`cp -r india swing-* ~/.claude/skills/`); no em dashes outside fixtures; Python 3.8 check over `india/*.py` and every skill script; no file under `india/` or `swing-*` except `india/nse_source.py` contains `import nse` or `from nse`; `config.example.json` keys equal `india.config.DEFAULTS` keys.
- [ ] **Step 2: Run, expect FAIL**
- [ ] **Step 3: Write README**: what it is; install (plugin, copy incl. `india/`, optional `nse`); the nine skills table; flow `scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> card`, `alerts` daily after close; walkthrough using the pinned fixture numbers from Tasks 5 and 8 (real NSE stock, real dates); the tools command list; fine print: not financial advice, you place every order, SEBI's study that most individual traders in equity derivatives and intraday lose money, GTT gap risk (a gap below the stop limit leaves the order unfilled), unofficial data, charges and tax (STCG/LTCG) are estimates, refresh holidays each year; credit the original pack by Jake Schincariol (MIT) with a link.
- [ ] **Step 4: Update manifests**; **Step 5: Run full suite, expect PASS**
- [ ] **Step 6: Commit** `git commit -m "README and plugin manifests for the India swing pack"`
