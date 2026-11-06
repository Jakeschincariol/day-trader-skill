# trader-data

Not a skill. A shared folder the other skills import (`kitefeed.py`), so copy it with the rest
(`cp -r trader-* ~/.claude/skills/` takes it along).

## Default: Yahoo Finance, free

Every tool reads NSE symbols from Yahoo as `SYMBOL.NS` (`RELIANCE` becomes `RELIANCE.NS`). Nothing to set up.
Yahoo is unofficial, can lag, and has no price for the 15:20 and 15:25 five-minute bars on most days.

## Optional: Zerodha Kite Connect

```bash
export TRADER_DATA_SOURCE=kite
export KITE_API_KEY=...            # from your Kite Connect app
export KITE_ACCESS_TOKEN=...       # from Zerodha's login flow; it expires every morning
```

What changes: single-symbol charts (entry, exit, timemachine, alerts, news price move, and the
scanner's stage-2 confirmation) are read from Kite's historical API and reshaped into Yahoo's JSON, so no other
tool changes. What does not: the scanner's whole-market stage 1 and daily scan stay on Yahoo, because Kite's
historical API takes one symbol a request at 3 requests a second.

- You run Zerodha's login yourself. The tools never see your password or TOTP, and never log in for you.
- Kite's historical data is a separate paid entitlement on Kite Connect. Without it Kite answers 403 and the
  tool says so (it does not fall back silently).
- **Not tested against the live Kite API.** It was written from Kite's v3 documentation and tested with
  sample candles (`tests/test_nse.py`, class `Kite`). Run `entry.py check RELIANCE` once with the variables
  set and compare it with Yahoo before you rely on it.
