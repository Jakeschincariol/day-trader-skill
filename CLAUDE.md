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

## Order safety (unchanged)

The rules in `trader-broker/SKILL.md` are not relaxed by anything above: every
order still needs a recent trader-risk PASS, the user's explicit yes for that
one order, and Allow once.
