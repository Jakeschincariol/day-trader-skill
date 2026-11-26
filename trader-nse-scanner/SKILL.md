---
name: trader-nse-scanner
description: >-
  NSE India five-minute Opening Range Breakout paper scanner.
  Analyses NSE-listed symbols using Yahoo Finance intraday candles,
  validates market sessions and NSE holidays, checks breakout and
  volume conditions, and records each paper signal once per symbol
  per trading date. Use when the user asks to scan NSE stocks,
  Indian market ORB setups, or NSE intraday breakout candidates.
argument-hint: "[--symbols RELIANCE.NS,TCS.NS]"
---

# NSE Scanner

This skill scans Indian NSE stocks for five-minute Opening Range Breakout (ORB) paper-trading candidates.

It is separate from `trader-scanner`, which handles the US market.

## Run

From this skill directory:

```bash
python nse_orb.py --help
python nse_orb.py
python nse_orb.py --symbols RELIANCE.NS,TCS.NS
```

## Market rules

- Exchange: National Stock Exchange of India (NSE)
- Timezone: Asia/Kolkata (IST)
- Regular session: 09:15–15:30 IST
- Opening range: first three completed five-minute candles
- Market holidays and weekends are checked by the holiday module.

## Scanner modules

| File | Purpose |
|---|---|
| `nse_orb.py` | Main ORB scanner |
| `nse_holidays.py` | NSE holiday calendar |
| `nse_market.py` | IST market-session utilities |
| `nse