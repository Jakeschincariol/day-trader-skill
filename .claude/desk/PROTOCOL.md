# The trading desk: protocol for every desk agent

The desk is one **main agent** (the Claude session the user talks to) and
eleven **desk agents**, one per skill. Desk agents work continuously during a
session and report through files. The main agent reads every report, shows the
user a dashboard (`python3 .claude/desk/desk.py`), decides, and is the only
one that touches orders.

## Hard rules (every desk agent)

1. **Never place, cancel or replace an order.** Never call
   `place_stock_order`, `cancel_order_by_id`, `replace_order_by_id`,
   `close_position`, `close_all_positions`, `cancel_all_orders` or any option or
   crypto order tool. Read-only Alpaca tools (`get_*`) are fine. If something
   needs an order, put it in your report as a recommendation; the main agent
   decides.
2. **Write only your own report file and your own scratch folder:**
   `trader/desk/<your-agent-name>.json` and `trader/desk/<your-agent-name>/`.
   Never write `trader/orders.json`, `trader/plan.json`, `trader/portfolio.json`,
   `trader/watchlist.json`, `trader/config.json` or anything in `trader/state/`.
   Use the scripts' `--out`, `--write PATH`, `--no-write` and `--json` options to
   keep them away from the main agent's files.
3. **Never print, ask for or store API keys.** Never send the user's name or
   email to an outside service (use a generic user agent such as
   `day-trader-skill desk research@example.com` for SEC requests).
4. **Read `MACHINE_LEARNING.md` (Standing rules) once at start** and apply the
   ones that touch your job.
5. Work from `C:\Users\Saleem\MyFiles\github\day-trader-skill` (or the repo
   root you are in) with `python3`. Times are New York time: get them from
   Python `zoneinfo` (`America/New_York`) or `python3 trader-alerts/alerts.py
   clock`, never from `TZ=` in Git Bash.

## The loop

**Do not hand back after one cycle.** A desk agent's whole value is that it
keeps running: one cycle, sleep, the next cycle, until the stop time. Handing
back early leaves the main agent blind (desk-broker did this on 2026-11-13).

```
until the stop time (default 15:55 New York) or trader/desk/STOP exists:
    do one cycle of your job
    write trader/desk/<name>.json (atomically: write .tmp, then rename)
    sleep your cadence:  python3 -c "import time; time.sleep(SECONDS)"
then write a final report with "status": "done" and hand back a 5-line summary
```

Keep each cycle cheap: pipe long output through `head`, keep raw data in your
scratch folder, and never paste big JSON into your own context. If a cycle
fails, write `"status": "error"` with the reason and keep looping.

## The report file

```json
{
  "agent": "desk-news",
  "skill": "trader-news",
  "updated": "2026-11-13T12:40:05-05:00",
  "cycle": 7,
  "cadence_seconds": 600,
  "status": "ok | watch | alert | error | done",
  "headline": "one line the main agent can read at a glance",
  "items": [ {"symbol": "LVS", "...": "agent-specific fields"} ],
  "recommendations": [ {"action": "cut LVS", "why": "closed under 40.12 breakout", "urgency": "now"} ]
}
```

`status`: `ok` nothing to do; `watch` something is close; `alert` the main
agent should act now (a failed breakout on a held stock, a halt, a filing, a
cutoff); `error` the cycle failed. `updated` is ISO time with the New York
offset. `recommendations` is optional and is only advice.
