# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One trader operating the existing day-trading tools locally during a trading session.

## Product Purpose

Provide a local dashboard for viewing saved outputs and running the repository's existing day-trading analysis tools. Success means the trader can see the current workspace state, run supported analysis tasks, and inspect their results without leaving the dashboard.

## Positioning

The dashboard is a local operator surface over the existing standard-library Python skills. It does not replace their analysis rules or connect to a brokerage.

## Operating Context

The trader uses the dashboard from a browser on the same computer that runs the Python tools. The tools read public market, news, SEC, and congressional disclosure data and store their outputs under `trader/`.

## Capabilities and Constraints

- The dashboard may run only explicitly supported analysis and inspection commands.
- Broker order placement and other broker mutations remain manual and outside the dashboard.
- The dashboard binds to loopback and does not provide multi-user hosting.
- Market data may be delayed or unofficial. Results are not financial advice or predictions.
- Paper trading remains the default in the existing configuration.
- No API keys, passwords, or brokerage credentials are requested or stored by the dashboard.

## Evidence on Hand

- `README.md` documents the eleven existing skills and their workflow.
- Each `trader-*/` directory contains the Python tool and its `SKILL.md` operating guidance.
- `tests/fixtures/` contains offline test data.

## Product Principles

- Keep the existing tools as the source of truth.
- Make stale, missing, or failed data explicit.
- Preserve the user's explicit approval boundary for broker actions.
- Keep the dashboard local and dependency-free.
