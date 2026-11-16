# The Day Trader skill

11 Codex skills for day trading: scan thousands of charts, track breaking news, time every entry and exit, and replay every outcome before you risk a dollar.

Free, MIT, no signup, no API key. The tools are plain Python that read free
public data: Yahoo Finance charts, Nasdaq Trader's symbol lists, SEC EDGAR
and the House Clerk.

One scans thousands of charts for setups. Another tracks breaking news on
every stock you watch. One watches a setup bar by bar and tells you the moment
to get in, and another sets your stop and your target before you do. And the
craziest one is the Time Machine: before you risk a dollar, it replays the
rest of the session 10,000 times from the stock's own recent bars, plus every
past day the same setup fired, and tells you the honest odds.

And no trade goes through until you say yes. Nothing in this pack can place
an order on its own. Paper trading is the default.

> **Looking for the original Trader skill?** Copy an investor's 13F, the
> stock screener, tax lots and rebalancing live in
> [github.com/Jakeschincariol/trader-skill](https://github.com/Jakeschincariol/trader-skill).
> This repo is its day-trading sequel: the Trader skill v2.

## Install in Codex

Clone this fork and open it in Codex:

```bash
git clone https://github.com/m33ch/day-trader-skill-codex.git
cd day-trader-skill-codex
codex
```

The checked-in `.agents/skills/` directory links to the eleven skill folders
at the repository root. Codex follows those links, so the skills are available
in this checkout without copying or maintaining duplicate scripts.
Use a checkout that preserves Git symlinks (for example Linux, macOS, or WSL).

To use them across projects, copy the actual source folders into your personal
skill directory (review any existing folders with the same names first):

```bash
mkdir -p "$HOME/.agents/skills"
cp -R trader-* "$HOME/.agents/skills/"
```

For another project only, copy the same eleven `trader-*` folders into that
project's `.agents/skills/` instead. Copy the source folders, not the relative
symlinks from this checkout. This also works on systems without symlink support.
Codex detects skill changes automatically; restart it if the skills do not appear.

In Codex CLI or the IDE, type `$` to select a skill or use `/skills`. For example:

```text
$trader-scanner scan TSLA, NVDA and AMD for opening-range breakouts
$trader-risk check the proposed orders
```

Start Codex in your trading project's working directory. All relative `trader/`
files are read and written there. The skill instructions resolve each Python
script from its installed skill directory; they do not depend on a built-in
skill-directory environment variable. You can also run the scripts directly
from this checkout, as shown below.

See the [Codex skills documentation](https://developers.openai.com/codex/skills/).

The tools need Python 3.8 or newer. Nothing to pip install. The SEC tools
(news filings, the analyst) ask you to identify yourself: put your name and
email in `trader/config.json` (`"sec_user_agent": "Your Name you@example.com"`)
or in the `SEC_USER_AGENT` environment variable.

## The eleven

| command | job | what it does |
| --- | --- | --- |
| `$trader-scanner` | Chart Scanner | Scans thousands of charts for setups: opening-range breakouts, flags, oversold bounces. |
| `$trader-news` | News Monitor | Tracks breaking news on every stock you watch and flags what moves it. |
| `$trader-entry` | Entry Timer | Watches a setup bar by bar and tells you the moment to get in. |
| `$trader-exit` | Exit Planner | Sets your stop and your target before you enter, so you know when to get out. |
| `$trader-timemachine` | Time Machine | Replays every possible outcome of a trade before you risk a dollar: 10,000 simulated sessions plus every past time the setup fired. |
| `$trader-risk` | Risk Manager | Checks every trade against your limits and stops anything over them. |
| `$trader-budget` | Budget Manager | Sizes every position to your budget and your max loss per trade. |
| `$trader-broker` | Order Executor | Sends approved orders to your broker, paper trading by default, never without your yes. |
| `$trader-alerts` | Price Alerts | Rings when a price, a stop or the opening bell hits. |
| `$trader-analyst` | Earnings Analyst | Reads earnings reports and sums up what changed. |
| `$trader-pelosi` | Pelosi Tracker | Reads Congress's stock-trade disclosures the minute they are filed. |

## How to use it

Everything lands in a `trader/` folder in your project, and each skill reads
what the last one wrote:

```
scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> broker   (one trade)
alerts: stop, target, flat by the close                                       (while it is open)
news / analyst / pelosi                         (on request, or a user-configured scheduler)
```

Checks are single runs unless a bounded watch process is active. Recurring
checks need a scheduler explicitly configured by the user; no order submission
is allowed from scheduled or unattended tasks.

An example, the trade in the reel: Tesla, Monday October 19 2026, real data.

1. **`$trader-scanner`** at 10:15 AM ET: of the 231 charts in the reel's
   scan, 42 had closed above their 15-minute opening range. TSLA is one: range 354.47 to 362.18,
   the 10:10 candle closed at 364.18, 0.55 % over the top.
2. **`$trader-news`**: the morning's TSLA headlines, in New York time
   ("Tesla-SpaceX Merger Mania Strikes Wall Street Ahead of Earnings", 8:04,
   tagged earnings and deal). Tesla reports this week: a day trade is out
   before the close, so it is not exposed to the report.
3. **`$trader-entry`** watched TSLA bar by bar. At 10:12 it said waiting (the
   10:10 bar was still forming). At 10:15 it said triggered: the first
   5-minute close above the range, 364.18.
4. **`$trader-exit`** set the plan before the entry: stop at the range's
   midpoint, 358.32, so 5.86 a share at risk; target one times that risk,
   370.04; flat by 3:55 PM either way.
5. **`$trader-timemachine`** replayed the rest of the day 10,000 times, each
   5-minute candle drawn from TSLA's own candles at that time of day over the
   previous 59 sessions (seed 19, so anyone can repeat it): target first
   29.4 %, stop first 25.5 %, still open at the close 45.1 %. It also re-ran
   the same rule on those 59 real sessions: it fired 33 times, 13 hit the
   target, 15 the stop, 5 neither. Its verdict: close to a coin flip. That is
   the point of looking before you risk a dollar.
6. **`$trader-budget`** with a $5,000 account and a $50 max loss per trade:
   50 / 5.86 = 8 shares ($2,913.44). If the stop fills at 358.32, the loss is
   $46.88. It writes one bracket order: buy 8 TSLA, stop-loss 358.32,
   take-profit 370.04.
7. **`$trader-risk`** checks it against your limits: the max loss, the daily
   loss limit, trades per day, reward to risk, the entry window, position
   size and cash. PASS or BLOCK, with the reason.
8. **`$trader-broker`** shows you the ticket in plain words. You type yes for
   that exact order. Codex uses the configured Alpaca MCP server (paper
   account by default), with separate approval for the exact tool call.
   Without separate tool approval, it stops at the ticket.
9. **`$trader-alerts`** rings on the stop, the target and at 3:55 PM to
   flatten whatever is still open.

## The tools

All standard-library Python. The data tools read public endpoints and are
polite about it.

```bash
python3 trader-scanner/scan.py universe                                # ~5,900 US stocks, Nasdaq Trader
python3 trader-scanner/scan.py daily                                   # pre-market setups, whole universe
python3 trader-scanner/scan.py orb --at 10:15                          # opening-range breakouts so far
python3 trader-news/news.py --tickers TSLA --hours 12                  # headlines, 8-Ks, today's move
python3 trader-entry/entry.py check TSLA --setup orb                   # waiting / triggered / expired
python3 trader-entry/entry.py watch TSLA --every 30                    # bar by bar until it triggers
python3 trader-exit/exit.py plan --stop or-mid --target 1R --write     # -> trader/plan.json
python3 trader-timemachine/timemachine.py run --write                  # 10,000 replays + the history
python3 trader-budget/size.py --write                                  # -> trader/orders.json
python3 trader-risk/check.py                                           # PASS / BLOCK per order
python3 trader-broker/ticket.py show                                   # the tickets, READY or not
python3 trader-alerts/alerts.py add --from-plan                        # stop, target, flat by close
python3 trader-alerts/alerts.py check                                  # rings what hit, once
python3 trader-analyst/facts.py TSLA                                   # quarters, growth, EPS
python3 trader-pelosi/ptr.py index --member pelosi                     # her PTRs this year
```

```bash
python3 -m unittest discover -s tests -v
```

The tests run offline, on fixtures cut from real data: TSLA's 5-minute bars
for the 60 days to October 19 2026, the 10:15 AM opening-range scan, Yahoo's
TSLA headlines that morning, the House Clerk's 2026 index, real PTR text and
real XBRL facts. They reproduce every number in the example above.

## Fine print

**Not financial advice.** This is software that reads public data and does
arithmetic. It does not know your situation and it cannot see the future.
Most people who day trade lose money. You can lose money. Decide for
yourself, and talk to a licensed professional if you need advice.

**No trade goes through until you say yes.** Only `$trader-broker` can lead to
an order, and only after `$trader-risk` passes that exact order and you type
yes for it in the chat. Configure the broker MCP server with
`default_tools_approval_mode = "prompt"` in Codex and require separate
approval for the exact tool call. If the client cannot enforce that, prepare
the ticket for manual submission. No options, margin, short selling or leverage
unless you turn them on.

**Paper first.** `"paper": true` is the default in `config.example.json`, and
the MCP example explicitly selects the paper account. Merge
[trader-broker/config.example.toml](trader-broker/config.example.toml) into your
Codex config to connect Alpaca; do not overwrite your existing settings. Keys
are forwarded from the Codex process environment, never entered in chat.
Broker setup needs a current Codex client with MCP tool approval support;
see [the broker skill](trader-broker/SKILL.md) for setup and IBKR limitations.

**The Time Machine is a simulation, not a prediction.** It is built from the
stock's own last 60 days of 5-minute bars. The future can do things those 60
days never did: an earnings report, a halt, a headline. Treat its odds as a
reality check, never as a promise.

**A stop is a plan, not a guarantee.** In a fast market or across a gap, a
stop order can fill well past its price. The max loss shown is the loss at
the stop price.

**The data is free and unofficial.** Yahoo Finance's chart endpoint is not an
official API: it can lag, change or rate-limit you. The scanner and the entry
timer read 1-minute or 5-minute bars, not every tick. Check anything that
matters against your broker before you act on it.

**Day-trading rules.** FINRA removed the $25,000 pattern-day-trader minimum
on June 4, 2026 (Regulatory Notice 26-10), and brokers may phase the change
in until October 20, 2027, so yours may still apply the old rule. If it does,
set `"pdt_guard": true` and `$trader-risk` counts your day trades.

**Congress's trades are public, not inside information.** Members must disclose
trades over $1,000 within 45 days (the STOCK Act). The Pelosi skill reads those
public filings the minute they post.

**Taxes.** Day-trading gains are short-term gains, and frequent trading makes
wash sales likely. Nothing here is tax advice.

## Migration from Claude Code

This fork replaces Claude plugin installation with Codex skill discovery,
`$skill-name` invocation, explicit script path resolution, and a Codex TOML MCP
example. It removes the Claude marketplace manifests and desktop JSON config.
The eleven Python tools, shared `trader/` data formats, offline fixtures, and
risk/consent checks are preserved. No brokerage account is connected by
installing the skills.

## Files

```
trader-scanner/     SKILL.md, scan.py
trader-news/        SKILL.md, news.py
trader-entry/       SKILL.md, entry.py
trader-exit/        SKILL.md, exit.py
trader-timemachine/ SKILL.md, timemachine.py
trader-risk/        SKILL.md, check.py
trader-budget/      SKILL.md, size.py, config.example.json, targets.example.json
trader-broker/      SKILL.md, ticket.py, config.example.toml
trader-alerts/      SKILL.md, alerts.py, alerts.example.json
trader-analyst/     SKILL.md, facts.py, metrics.example.json
trader-pelosi/      SKILL.md, ptr.py
.agents/skills/     Codex discovery links to the eleven source folders
tests/              unittest suite + offline fixtures
```

MIT. Made by [Jake Schincariol](https://opusjake.ai).
