# CLAUDE.md

## Trading sessions: learn from mistakes

- Before any trading session, read `MACHINE_LEARNING.md` and apply its
  **Standing rules**.
- After a session (or when a mistake happens), add to `MACHINE_LEARNING.md`:
  what went wrong, the rule it teaches (added to Standing rules), and the
  trades with their results. Write a rule only when it changes what you do
  next time.
- When done, commit and push to GitHub. The user has given standing
  permission to push without asking. Push the current branch.
- Never commit `trader/`. It holds personal account state (portfolio, orders,
  broker log) and the repo is public. Never commit API keys.

## Order approval

- On the **paper** account the user gave standing approval (2026-11-12):
  `"auto_approve": true` in `trader/config.json`, then
  `ticket.py approve --index N --auto`. Claude may enter and exit as it sees
  fit. Every order still needs a recent trader-risk PASS.
- **Autotrade switch:** `python3 trader-broker/ticket.py auto on|off|status`.
  `on` (paper only) also removes the Allow card for the order tools, so Claude
  opens, adjusts and closes paper trades with no approval at all. Check
  `auto status` at the start of a session and say which mode is active. Only
  the user turns it on or off.
- A **live** account always needs the user's typed yes for each order.
  `--auto` refuses unless `"paper": true`.
- Research can fan out to parallel agents. Orders are staged, risk-checked
  and placed by the main session one at a time, so the daily limits hold.

## The trading desk (one agent per skill, one main agent watching)

- At the start of a trading session, launch the eleven desk agents in
  `.claude/agents/` (`desk-scanner`, `desk-entry`, `desk-exit`, `desk-budget`,
  `desk-risk`, `desk-broker`, `desk-alerts`, `desk-news`, `desk-analyst`,
  `desk-pelosi`, `desk-timemachine`). Each one loops through the session
  and writes `trader/desk/<agent>.json` per `.claude/desk/PROTOCOL.md`.
- The main session is the observer and the only executor. Every few minutes
  it runs `python3 .claude/desk/desk.py`, shows the user the dashboard, acts
  on `alert`s, and places orders itself (budget, then risk, then
  `ticket.py approve --auto`, then the broker), one at a time.
- Desk agents never place, cancel or replace orders. Their tool lists hold
  only read-only Alpaca tools. Their recommendations are advice.
- To stop them early: create `trader/desk/STOP`.
