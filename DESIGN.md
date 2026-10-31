# Design system

## Surface

The local dashboard is an operator desk for a single trader working through saved analysis. Its visual reference is a ruled exchange blotter: a quiet paper-gray work surface, measured tables, and a dark navigation rail. The UI does not imitate a live market feed or a broker terminal.

## Palette

- Ground: `#e9edeb`, with a low-contrast drafting grid.
- Raised surface: `#ffffff`; secondary surface: `#f5f7f5`.
- Ink: `#172522`; secondary text: `#41504b`; muted text: `#64736d`.
- Rail: `#202c29`, with pale text and restrained green details.
- Action: `#0c6459` / `#06483f`.
- Caution: `#80530a` on `#f4e8c9`.
- Error: `#943d32` on `#f4e1dd`.

Color indicates action, state, or caution. It does not encode predicted performance.

## Typography

Use the system UI stack (`Segoe UI`, `Helvetica Neue`, Arial) for interface text. Use Consolas or Courier New only for command output and measured codes. Numeric values use tabular figures where appropriate. Labels are compact and tracked; task names and section headings use a clear weight and size hierarchy.

## Composition

On desktop, a fixed-width left rail anchors the workspace. The main surface orders information from current workspace status to the trade workflow, watchlist, tool dock, and run activity. Tables use ruled rows and variable column widths rather than repeated cards. The task dock is a tinted control surface for ticker-specific analysis and local tool actions.

On smaller screens, the rail becomes a compact masthead, summary fields become two columns, and the task dock moves above the watchlist. Workflow details simplify while controls remain available. Tables and task output can wrap or scroll without hiding their actions.

## Interaction and states

Saved state is read from known files under `trader/`. Missing files have explicit empty states; malformed files expose a read error. The New York clock is labeled as a clock, not as market-open status. Every task has queued, running, completed, and failed states, with the tool's output shown in a bounded text region. Keyboard focus is visible. Reduced-motion preferences are respected.

Only allowlisted Python commands can run. The server binds to loopback, and the dashboard exposes no broker order submission or approval control.
