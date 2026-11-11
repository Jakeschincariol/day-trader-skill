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
| Portfolio | Action per holding (Accumulate+, Accumulate, Hold, Trim, Review thesis), **Monthly plan** (splits your monthly amount towards targets, ready for a Trading 212 Pie), **Diversification** with ETF look-through and overlap (e.g. VUSA + CSPX, world fund + S&P 500), dividends received, yearly growth, worst fall and your portfolio vs the same money in a world index fund. **10-year plan**: simulates 4,000 possible markets for your current value plus a monthly deposit, with sliders for years and world-ETF share, bad/middle/great cases, odds of ending below what you put in, and a comparison of mixes (scenarios, not a forecast) | Stops, risk check, trade journal |

ETF look-through weights live in `dashboard/etf_lookthrough.json` (approximate;
refresh them now and then). The first long-term scan of all stocks takes a few
minutes; results are cached for hours.

## Data connections (Portfolio page)

- **Financial Modeling Prep** (optional key): company figures (return on equity, margins, debt, free cash flow, P/E, yearly results) and results dates for **non-US** stocks such as SK hynix, Advantest and ASM International, so they get a full long-term score instead of "price only", plus earnings warnings. Get a free key at financialmodelingprep.com, paste it under **Data connections** and press **Test the key** to see what your plan covers (non-US data may need a paid plan). About 4 calls per stock; answers are saved for 7 days in `dashboard/.fmp-cache.json`; the key stays in `dashboard/.fmp.json` (or the `FMP_API_KEY` environment variable). US stocks keep using Nasdaq.com (free, no key).
- **FinanceDatabase** (free, MIT licence, by Jeroen Bouma): about 95,000 active companies worldwide with sector, industry, country and size, downloaded automatically (18 MB, refreshed monthly, `dashboard/.fdb-equities.bz2`). Used for: sector and country of every holding (Diversification shows **Countries**), spotting chip companies anywhere as part of the AI build-out theme, and a much wider **Challenger** search (large and mega companies in the same industry worldwide, and mega companies in every other sector).
- **Tailscale** (free app): install it on the PC and on the iPhone with the same account, start with `start-phone.bat`, and **Use on iPhone** shows a second QR code that works away from home (4G, any Wi-Fi); only your own devices can reach it.

## Compare: Challenger

At the end of Compare, the **Challenger** looks for one stock or ETF that beats **every** stock you compared: a higher long-term score, a better 5-year return per unit of downside risk, and a worst fall no more than 5 points deeper than your mildest pick. It shows two: one from the **same group** (theme or sector of your picks) and one from **outside the AI theme** (to spread risk). If nothing beats them all it says so and names the closest. **Swap** replaces your weakest pick with the challenger. It searches the stocks and ETFs the dashboard tracks; the first search takes 1-3 minutes.

## Radar: every sector

The Radar (formerly AI Radar) now scans about 120 stocks in every sector: AI and tech, healthcare and biotech, oil and gas, clean energy and nuclear, defense, banks and fintech, consumer and retail, industrials, mining, software. Its pattern also learns from winners outside AI (Eli Lilly, Vistra, Axon, Celsius, Robinhood). Filter with **All sectors / Not AI / AI & tech** or by theme. The first full scan takes about 4 minutes.

## Expert review (November 2026)

Four reviewers (long-term investing, trading and risk, visual design, mobile use) checked the dashboard. Changes made:

- **One bet, not many**: chip, chip-equipment, memory, optics and AI-power stocks count together as the **AI build-out** theme. Diversification shows its share and warns above 40%; holdings in a full theme say *Theme full: send new money elsewhere*.
- **Monthly plan rebalances**: with no targets set it uses a starting model (AI build-out names share at most 40%, a world ETF such as VWCE is the core when you hold nothing else) instead of copying today's mix, and stops tilting extra money into holdings when most of them are "on sale" at once.
- **Price-only scores are labelled**: listings with no company figures (e.g. SK hynix, Advantest, ASM International) show *price only* and can't get *Good time to add*.
- **Honest entry check**: counts separate past episodes, hides the 12-month figure when there are too few, softens the advice when the stock's own record after similar drops was poor, and says when to stop adding.
- **Fixes**: positions already below their stop are flagged in the risk panel; the stock *Max* return compares from the same start date as the S&P 500; weak stocks say *Avoid*; swing backtests include 0.4% costs and buy-and-hold; Copy works on the iPhone; sparkline colours follow the day's change; one €1,200 monthly default.
- **Clearer pages**: portfolio value first on the Dashboard; positions first on Portfolio; on stock pages (long-term mode) a verdict strip under the price, a full-width calm chart (price and 200-day average; tick *Trader view* for candles, volume and RSI), and Statistics / Earnings folded; plainer labels (*Good time to add*, *Keep buying as planned*, *Pricey: buy small*, *Gain so far*); compact market banner on the iPhone.

## Right moment to buy? (long-term entry check)

On every stock page in Long-term mode, above the Long-term view. It answers "should I buy it all now, in parts, or wait?":

- **Trend state today**: *Still falling* (below a falling 50-day average and making new 1-month lows), *Steadying after a drop*, *Pullback in an uptrend*, *Rising trend* or *No clear trend*, combined with the long-term buy zone, upcoming results and the market mood into one verdict.
- **Buy in parts**: a third now and the rest at two lower prices when it is still falling; half and half when steadying; most now in a pullback; all now in a rising trend. The lower prices are how far the stock typically fell further within 3 months after past days in the same state (10 years of daily prices). Set them as limit orders or price alerts. The **Buy an amount** dialog splits the amount you type the same way.
- **What usually happens after buying**: the typical (and 1-in-5) further dip within 3 months after days like today and after any day, and how often it was higher 12 months later. A dip right after buying is normal.
- **If you already own it at a loss**: whether adding at the lower prices makes sense (good long-term score) or not (weak score: don't average down just to get even).

## Use Revolut

Revolut has no API for personal investing accounts, so the dashboard reads your statement file:

1. In the Revolut app open **Invest** → **…** (More) → **Documents** → **Brokerage account** → **Account statement** (menu names can differ a little between app versions).
2. Choose **Excel** (not PDF) and the period **All time**, then get the file onto your computer (email, OneDrive, AirDrop), or pick it from Files on the iPhone.
3. On **Portfolio**, under **Use Revolut?**, choose the file and your account currency.

Holdings are rebuilt from the trades (average cost, sells, stock splits, dividends, fees), priced live, and shown with your Trading 212 positions everywhere: dashboard, plan, diversification, correlation, Compare and the history chart. The file stays on your computer in `dashboard/.revolut.json` (git-ignored). Import a new statement after you trade. Any broker's CSV or Excel file with **Symbol** and **Quantity** columns (plus an average price) also works.

## Briefing, news impact, calendar and correlation (no AI key)

- **Your briefing** (Dashboard): the market, your holdings' day, big moves, important headlines that name your stocks, earnings this week and the next big US/EU economic events, built with fixed rules from live data.
- **News impact badges**: every headline is tagged Bullish or Bearish and High or Medium impact from keyword rules. Filter by "Important only", "Bullish" or "Bearish". Click a ticker chip to open its stock page.
- **Calendar** (News → Calendar): earnings dates of your US-listed stocks and this week's and next week's medium and high impact economic events (Forex Factory feed), with what each one usually moves.
- **How your holdings move together** (Portfolio): a correlation heatmap of weekly returns over two years, the pairs that move most alike and the best diversifiers.
- **Shortcuts**: Ctrl+K or / jumps to search; watchlist and trending prices flash green or red when they change.

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
| **Compare → Pick for me** | Advice designed by the trading expert. **One pick**: "best risk-adjusted odds" (never "most profitable") from an expected-return estimate (growth, free-cash-flow yield, analyst upside, dividend; past returns shrunk for funds), return for downside risk, long-term score, worst fall, valuation and portfolio fit, with penalties for red flags, near earnings and stretched prices, vetoes (speculative, weak score, 3+ red flags, heavy debt, short history) and High / Medium / Low confidence ("no clear winner" when close). **Or a pair**: a calmer core (lowest swings, a broad ETF if there is one) + a higher-growth satellite (25%+ more volatile, acceptable quality, not too correlated), split Cautious 80/20, Balanced 65/35 or Bold 50/50, with the satellite capped so a 2022-style fall in it costs at most 5 / 8 / 12% of the amount; shows the mix's 5-year return, worst fall, worst and typical 12 months and a 2022 replay in euros, and "invest at most €X" to keep one company under 10%. Swing mode ranks setups instead. **Save this pick** records it so you can see later how it really did |
| **Market Map** | A heat map of every tracked stock or ETF grouped by sector: tile size = money traded per day, colour = today, 1 month, 3 months or signal score. Click a tile to open the stock |
| **Markets** | 100+ US stocks by sector and ETFs (US plus UCITS ETFs sold on Trading 212 such as VUSA, CSPX, VWRL, EQQQ). Sort by any column, filter by sector or rating, ★ to watch. Use the search box for any other ticker in the world |
| **Strong Buys / Quality** | Cards for every stock with a buy signal: why, entry, stop loss, target 1 (2R) and target 2 (3R) |
| **Stock page** | Charts for 1D (5-minute bars), 7D (hourly bars) and 3M to 2Y (daily, with 20/50/200-day averages, volume, RSI, your entry/stop/target lines, and a forecast cone plus the analysts' average target). 1D and 7D add tables of hourly levels and the last 7 days. "Best moment to buy" verdict with the reason, position size calculator, the checklist behind the rating, performance (1W, 1M, 3M, 6M, YTD, 1Y, 2Y, 5Y, Max) against the S&P 500, statistics (P/E TTM, forward P/E, PEG, price/sales, price/book, EV/EBITDA, margins, ROE, cash, debt, free cash flow), analyst price targets and buy/hold/sell counts, earnings trends (EPS per quarter with year-over-year growth and the next quarters' forecasts, revenue vs net income by quarter or year), and news |
| **Runners** | Day-trading scanner for small caps up 10%+ today (or 20, 30, 50%) on heavy volume, from Yahoo's gainers lists: listed US stocks only (no OTC), $0.50 or more. Each card shows the move, volume vs normal, shares outstanding, VWAP, fresh news, a 0-100 runner score and a setup: **Breakout** (near the high of day), **Pullback** (above VWAP), **Pre-market**, **Next session**, **Under VWAP** or **Faded** (already gave back 25%+, no entry). The plan comes from today's 5-minute bars: buy above the high of day / latest candle / pre-market high / VWAP, stop at the lowest price of the last 30 minutes, sell half at 2R and the rest at 3R, shares for your risk %. Track any ticker, and stocks you hold are added automatically. One tap sets price alerts at all four levels. Rules, not predictions: most runners fade |
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
