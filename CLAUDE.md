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
- A **live** account always needs the user's typed yes for each order.
  `--auto` refuses unless `"paper": true`.
- Research can fan out to parallel agents. Orders are staged, risk-checked
  and placed by the main session one at a time, so the daily limits hold.
