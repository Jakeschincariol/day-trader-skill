# Trader Dashboard

A trading website you run on your own computer: every tracked stock and ETF
rated, the best moment to buy each one, trading news, and your Trading 212
portfolio linked in, read-only.

```bash
python3 dashboard/server.py
```

Then open **http://127.0.0.1:8212** in your browser. Python 3.8+ only, nothing
to install, no signup.

## Pages

| Page | What you get |
| --- | --- |
| **Dashboard** | Indices strip (S&P 500, Nasdaq, Dow, Russell, VIX, gold, bitcoin, EUR/USD), market breadth, top Strong Buys, stocks in a buy zone right now, your watchlist, latest headlines |
| **Markets** | 100+ US stocks by sector and ETFs (US plus UCITS ETFs sold on Trading 212 such as VUSA, CSPX, VWRL, EQQQ). Sort by any column, filter by sector or rating, ★ to watch. Use the search box for any other ticker in the world |
| **Strong Buys** | Cards for every stock with a buy signal: why, entry, stop loss, target 1 (2R) and target 2 (3R) |
| **Stock page** | Candlestick chart (3M to 2Y) with 20/50/200-day averages, volume, RSI, and your entry/stop/target lines; "Best moment to buy" verdict with the reason; position size calculator; the checklist behind the rating; key stats; news for that ticker |
| **Portfolio** | Trading 212 cash, value, open and realised P/L, every position with its live rating and an exit check ("Rating turned Sell", "Below trailing stop", "Overbought: consider taking profit"); allocation chart; add holdings by hand |
| **News** | Headlines for your holdings and watchlist or the whole market, tagged #earnings, #analyst, #deal, #legal, #macro |

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

Each stock page lists every check it passed and failed, so nothing is hidden.

## Best moment to buy

| Verdict | Meaning |
| --- | --- |
| **Buy now: breakout** | Closed above the 20-day high on 1.3x+ normal volume |
| **Buy zone: pullback** | An uptrend pulled back to its 20-day average: buying near support keeps the stop close |
| **Wait: extended** | Ran too far above the 20-day average or RSI above 72. Suggests a limit price to wait for |
| **Watch** | Trend fine, price between levels. Shows the pullback and breakout prices to wait for |
| **Avoid** | Downtrend (below the 50-day, which is below the 200-day) |

Stops sit 2 ATR (average daily range) below entry or under the 10-day low,
never more than 3 ATR or 15% away. Targets are 2x and 3x the risk. Position
size = (account × risk %) ÷ (entry − stop).

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
