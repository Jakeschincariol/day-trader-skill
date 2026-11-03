# Trader Dashboard

A trading website you run on your own computer: every tracked stock and ETF
rated, the best moment to buy each one, trading news, and your Trading 212
portfolio linked in, read-only.

```bash
python3 dashboard/server.py
```

Then open **http://127.0.0.1:8212** in your browser. Python 3.8+ only, nothing
to install, no signup.

**Easiest start on Windows:** double-click `dashboard/start.bat` (or
`start-phone.bat` to also use it on your iPhone). On a Mac: `start-phone.command`.

## Use it on your iPhone

1. Start the dashboard in phone mode: `python3 dashboard/server.py --phone`
   (or double-click `start-phone.bat` / `start-phone.command`). If Windows asks
   whether Python may use the network, allow **Private networks**.
2. On the computer, click **Use on iPhone** at the bottom of any page. A QR code appears.
3. On the iPhone (same Wi-Fi), point the **Camera** at the code and tap the link.
4. In Safari: **Share → Add to Home Screen → Add**. TraderDash now opens full screen like an app.

The link carries a secret key (stored in `dashboard/.access.json`, git-ignored).
Without it the dashboard refuses every other device; with it, other websites
still can't reach it. To log every phone out: `--phone --new-key`. The computer
must stay on with the dashboard running. Away from home, install the free
**Tailscale** app on both the computer and the iPhone and use the computer's
Tailscale address instead.

## Long-term or swing

A switch in the header (and on the Portfolio page) picks the style. **Long-term**
is the default.

| | Long-term investing | Swing trading |
| --- | --- | --- |
| Rating | **Long-term score** 0-100: quality 25% (ROE, margins, free cash flow, profitable years), growth 20%, valuation 20% (PEG, FCF yield, analyst upside), balance sheet 15%, trend 15% (vs its index, 200-day, worst fall), dividend 5%. Bands: Core quality 75+, Good 60+, Fair 45+, Speculative. ETFs and non-US listings are scored on their track record | Trend/momentum/volume rating |
| When to buy | **Buy zone**: Accumulate+ (good business on sale: below the 200-day, P/E low in its range, or down 15%+ without a recent run-up), Accumulate, Stretched, Speculative | Breakout / pullback / extended / avoid |
| Stock page | Long-term card, 1/3/5/10-year buy-and-hold results and a 5-year monthly investing test vs the index (dividends reinvested), "Buy an amount" ticket | Entry, stop, targets, order ticket, 40-day signal backtest |
| Strong Buys tab | **Quality**: on sale now, core quality, best ETFs | Strong Buys and setups |
| Portfolio | Action per holding (Accumulate+, Accumulate, Hold, Trim, Review thesis), **Monthly plan** (splits your monthly amount towards targets, ready for a Trading 212 Pie), **Diversification** with ETF look-through and overlap (e.g. VUSA + CSPX, world fund + S&P 500), dividends received, yearly growth, worst fall and your portfolio vs the same money in a world index fund | Stops, risk check, trade journal |

ETF look-through weights live in `dashboard/etf_lookthrough.json` (approximate;
refresh them now and then). The first long-term scan of all stocks takes a few
minutes; results are cached for hours.

## Logos

Company and fund logos come from Financial Modeling Prep and Parqet, fetched by
the server once and cached in `dashboard/.logo-cache` (git-ignored). Indices,
currencies and unknown tickers get a generated monogram. Logos are trademarks of
their owners; the footer credits the sources.

## Pages

| Page | What you get |
| --- | --- |
| **Dashboard** | Indices strip (S&P 500, Nasdaq, Dow, Russell, VIX, gold, bitcoin, EUR/USD), market breadth, top Strong Buys, stocks in a buy zone right now, your watchlist, latest headlines |
| **Dashboard (live)** | Quality on sale, your watchlist and **Trending tickers** as live rows: logo, today's intraday chart (with yesterday's close dotted), price and change, refreshed every minute |
| **Markets → All stocks & ETFs** | Every US-listed stock and ETF (Nasdaq Trader directory, ~11,700, refreshed daily) plus about 175 major stocks and UCITS ETFs from Europe, the UK, Switzerland, the Nordics, Japan, Hong Kong, Korea, Taiwan, India, Australia and Canada (`dashboard/world.json`). Search by symbol or name, filter by type and region, each with its live day trend. Any other ticker on any exchange opens from the search box |
| **Compare** | 2 or 3 stocks or ETFs side by side (Compare button on any stock page, or the Compare tab). A verdict that *leans* ("Leans A for a long-term investor, 62 vs 51" or "too close to call: split it"), red flags (shrinking margins, profit falling while revenue rises, high debt, payout over 100%, earnings within days, price above analyst target), and sections with a winner dot per row: fit with my portfolio (what you already own incl. inside ETFs, after buying your amount, correlation, portfolio swings), quality, growth, valuation (also vs its own history), financial health, risk (volatility, beta, worst fall and time to recover, worst 12 months, Sharpe, up/down capture, COVID / 2022 / 2025 crash replays), track record (in your currency too), momentum, analysts, dividends, events, news. Plus "pick one or split?": equal split vs each alone, correlation between the picks, equal-risk amounts, and what a 2022-style crash would cost your amount. Charts: growth of 100, falls from peak, risk vs return, score radar. Weights follow the Long-term / Swing switch |
| **Market Map** | A heat map of every tracked stock or ETF grouped by sector: tile size = money traded per day, colour = today, 1 month, 3 months or signal score. Click a tile to open the stock |
| **Markets** | 100+ US stocks by sector and ETFs (US plus UCITS ETFs sold on Trading 212 such as VUSA, CSPX, VWRL, EQQQ). Sort by any column, filter by sector or rating, ★ to watch. Use the search box for any other ticker in the world |
| **Strong Buys / Quality** | Cards for every stock with a buy signal: why, entry, stop loss, target 1 (2R) and target 2 (3R) |
| **Stock page** | Charts for 1D (5-minute bars), 7D (hourly bars) and 3M to 2Y (daily, with 20/50/200-day averages, volume, RSI, your entry/stop/target lines, and a forecast cone plus the analysts' average target). 1D and 7D add tables of hourly levels and the last 7 days. "Best moment to buy" verdict with the reason, position size calculator, the checklist behind the rating, performance (1W, 1M, 3M, 6M, YTD, 1Y, 2Y, 5Y, Max) against the S&P 500, statistics (P/E TTM, forward P/E, PEG, price/sales, price/book, EV/EBITDA, margins, ROE, cash, debt, free cash flow), analyst price targets and buy/hold/sell counts, earnings trends (EPS per quarter with year-over-year growth and the next quarters' forecasts, revenue vs net income by quarter or year), and news |
| **✦ AI Radar** | Scans 45 AI-economy stocks (memory, chip equipment, AI chips, networking, power and data centers, quantum and space, AI software) for the price "fingerprint" NVIDIA, Micron, SanDisk, ASML, Western Digital, Palantir, AppLovin and Broadcom showed on the day their big runs began, then checks the earnings growth behind them. Animated radar, the legends' runs, theme heat map, and for each stock a score ring, a spider chart vs the legends and a "what if it repeated a legend's 12 months" chart |
| **Portfolio** | Trading 212 cash, value, open and realised P/L; gain or loss in % and money for today, 1 week, 1 month, this year, 1 year, 5 years and all time; a graph of money invested vs portfolio value over time; every position with its live rating and an exit check; allocation chart; add holdings by hand with their buy date |
| **News** | Headlines for your holdings and watchlist or the whole market, tagged #earnings, #analyst, #deal, #legal, #macro |

Every section has a **↻ refresh** button with the time it last updated. Refresh skips
the server's short-term cache (quotes 2 minutes, news 5, fundamentals 6 hours) and
fetches the newest data.

## Link Trading 212

1. In the Trading 212 app: **Settings → API (Beta) → Generate API key**.
2. Give it **read** permissions only (account data, portfolio). Leave order
   execution off. This site never places orders anyway.
3. Copy the key and secret (the secret is shown once).
4. In the dashboard open **Portfolio → Link Trading 212**, paste both, pick
   **Live** or **Practice**, and connect.

The key goes only to the server on your computer, which calls Trading 212
directly. Tick "Remember" and it is saved to `dashboard/.t212.json` (only your
user can read it, and git ignores it). Or set it in the environment instead:

```bash
T212_API_KEY=... T212_API_SECRET=... T212_ENV=live python3 dashboard/server.py
```

The API works for Trading 212 **Invest** and **Stocks ISA** accounts (not CFD).

## Trading tools

| Tool | Where | What it does |
| --- | --- | --- |
| **Order ticket** | Stock page, Strong Buys cards | Shares sized to your risk % in your account currency (FX and pence converted), capped at your max position size and halved on an amber market. Shows cost, max loss, both targets, warnings (free cash, earnings, weak market, limit above price) and the exact steps for Trading 212. Copy it in one tap. Never sent anywhere |
| **Market mood** | Dashboard, header chip | Green / amber / red from the S&P 500 and Nasdaq 100 vs their 50/200-day averages and the VIX. Red puts new "Buy" verdicts on hold; amber halves suggested size |
| **Earnings warning** | Every signal, position and ticket | Next report date (Nasdaq.com, US stocks). Within 7 days a buy becomes "Wait: earnings" |
| **Signal backtest** | Stock page | Replays the same buy rules over 5 years on that stock: % that hit 2R, win rate, average R per trade, hold time, running total |
| **Risk check** | Portfolio | Money lost if every stop hits (vs your max open risk), positions with no stop order in Trading 212, largest position, biggest sector, cash |
| **Stop column** | Portfolio | Your Trading 212 stop order, or a suggested trailing stop (highest close of 22 days minus 3 ATR) flagged "none set" |
| **Trade journal** | Portfolio | Closed trades from your Trading 212 history (first-in first-out): win rate, average win and loss, per-trade average, profit factor, hold time, by month |
| **Price alerts** | Bell icon, stock page, ticket | Alert above/below a price; checked every minute while the dashboard is open, with a browser notification |

Risk settings (Portfolio page): risk per trade %, max position %, max open risk %,
account size and currency when Trading 212 isn't linked. Give your Trading 212
API key the **orders: read** permission so the stop check can see your stop orders.

## How the rating works

Each stock earns points for: price above its 20, 50 and 200-day averages; the
50-day above the 200-day; RSI in the healthy 45 to 68 zone; MACD above its
signal and rising; up over 3 months; beating the S&P 500 over 3 months; and
an up day on above-average volume. The score is 0 to 100:

| Score | Rating |
| --- | --- |
| 78+ | Strong Buy |
| 60 to 77 | Buy |
| 40 to 59 | Hold |
| 22 to 39 | Sell |
| under 22 | Strong Sell |

A check that can't be computed yet (a recent listing has no 200-day average)
is left out rather than counted as failed. Relative strength is measured
against the stock's home index (S&P 500, FTSE 100, DAX, CAC 40, AEX...).
Each stock page lists every check it passed and failed, so nothing is hidden.

## Best moment to buy

| Verdict | Meaning |
| --- | --- |
| **Buy now: breakout** | Above the 20-day high on 1.3x+ normal volume (scaled to the time of day), score 55+, not stretched |
| **Buy zone: pullback** | An uptrend pulled back to its 20-day average: buying near support keeps the stop close |
| **Wait: extended** | Ran too far above the 20-day average or RSI above 72. Suggests a limit price, always below the market |
| **Wait: earnings** | A buy setup, but earnings are due within 7 days |
| **Watch: market weak** | A buy setup, but the market light is red |
| **Watch** | Trend fine, price between levels. Shows the pullback and breakout prices to wait for |
| **Avoid** | Downtrend (below the 50-day, which is below the 200-day) |

Stops sit 2 ATR (average daily range) below entry or under the 10-day low,
never more than 3 ATR or 15% away. Targets are 2x and 3x the risk. Position
size = (account × risk %) ÷ (entry − stop).

## Forecast, P/E and earnings

- **Forecast cone**: the last 6 months' price trend (halved and capped at about
  ±10% a year, since trends fade)
  projected 3 months ahead, with ranges from recent volatility: the darker band
  holds about 68% of outcomes, the lighter one 95%. It is a statistical range,
  not a prediction.
- **P/E, statistics, earnings, analyst targets**: Nasdaq.com's free data (estimates
  from Zacks), US-listed stocks only. P/E (TTM) = price / EPS of the last 4
  reported quarters. Forward P/E uses the analysts' EPS forecast for the next 4
  quarters. Free data doesn't include past EPS estimates, so earnings show
  reported EPS with year-over-year growth instead of "beat/miss".

## AI Radar

1. **Launch fingerprint.** For each legend: the first day of a confirmed uptrend
   (price above a rising 50-day average that is above the 200-day) before its best
   12 months. On that day it measures 9 traits: 3, 6 and 12-month returns, strength
   vs the S&P 500, distance from the 52-week high and the 200-day average, the
   50-day slope, the volume trend and volatility. The fingerprint is the median
   across the legends.
2. **Pattern match (0 to 100)**: how close a stock's traits are today.
3. **Growth (0 to 100)**: revenue and EPS growth, acceleration, forecast EPS growth,
   operating margin and analyst upside (needs at least 3 of these; otherwise
   counted as 35).
4. **Radar score** = 55% pattern + 45% growth.

The first scan takes about 2 minutes, then it is cached for 30 minutes. The
legends were chosen because they won, and the method has not been tested on
look-alikes that failed: use it as a research shortlist, not a buy list. These
stocks can fall 50% or more.

## Portfolio history

Built from your Trading 212 order history (loaded a few pages a minute, as the
API allows) and the buy dates of manual holdings, valued each day at the
closing price and converted to your account currency. "Money invested" is the
cost of the shares you hold. Period gains leave out money you add or withdraw,
so a deposit never shows up as profit.

## Libraries

Bundled in `dashboard/static/vendor` (no internet needed, nothing to install):

| Library | Used for | Licence |
| --- | --- | --- |
| [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts) 4.2.3 | price charts (zoom, scroll, crosshair) | Apache 2.0, TradingView credit on the chart |
| [Apache ECharts](https://github.com/apache/echarts) 5.5.1 | market map, allocation donut | Apache 2.0 |
| [Lucide](https://github.com/lucide-icons/lucide) 0.460.0 | icons | ISC |
| [CountUp.js](https://github.com/inorganik/countUp.js) 2.8.0 | numbers that count up | MIT |
| [Inter](https://github.com/rsms/inter), [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) | fonts | SIL Open Font License |

Full licence texts: `dashboard/static/vendor/THIRD_PARTY_LICENSES.txt`. If a
library file is missing, the dashboard falls back to its built-in charts.

## Notes

- Market data comes from Yahoo Finance's public endpoints: free, unofficial,
  can be delayed or briefly unavailable.
- Ratings are rules applied to price data, not a forecast and not financial
  advice. Always check the chart and the news before you trade.
- The server listens on 127.0.0.1 and refuses requests from other websites, so
  nothing on the internet can read your portfolio through it. To open it from
  your phone on the same Wi-Fi, run `python3 dashboard/server.py --host 0.0.0.0`
  and browse to your computer's IP; anyone on that network could then see your
  portfolio, so only do this on a network you trust.
