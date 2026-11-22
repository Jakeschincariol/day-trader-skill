"""Continuous read-only MT5 market monitor; no trading methods are used."""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Tuple

from .readonly import MT5ConnectionError, ReadOnlyMT5Adapter


@dataclass(frozen=True)
class MonitorConfig:
    symbols: Tuple[str, ...]
    poll_interval_seconds: int


def load_config(path: str) -> MonitorConfig:
    """Load a strict READ_ONLY config; reject empty or malformed watchlists."""
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")
    if data.get("mode") != "READ_ONLY":
        raise ValueError("monitor mode must be READ_ONLY")
    raw_symbols = data.get("symbols")
    if not isinstance(raw_symbols, list) or not raw_symbols:
        raise ValueError("configure at least one exact broker symbol")
    if any(not isinstance(item, str) or not item.strip() for item in raw_symbols):
        raise ValueError("symbols must be non-empty strings")
    symbols = tuple(dict.fromkeys(item.strip() for item in raw_symbols))
    interval = data.get("poll_interval_seconds")
    if not isinstance(interval, int) or isinstance(interval, bool) or not 1 <= interval <= 300:
        raise ValueError("poll_interval_seconds must be an integer from 1 to 300")
    return MonitorConfig(symbols=symbols, poll_interval_seconds=interval)


def collect_cycle(adapter: Any, symbols: Tuple[str, ...]) -> dict:
    """Collect one health-checked snapshot. Any read failure aborts the cycle."""
    if not symbols:
        raise ValueError("watchlist is empty")
    health = adapter.health()
    if not getattr(health, "connected", False):
        raise MT5ConnectionError("MT5 terminal/account health is not connected")
    quotes = []
    for symbol in symbols:
        quote = adapter.quote(symbol)
        quotes.append(
            {
                "symbol": quote.symbol,
                "time_utc": quote.time_utc.isoformat(),
                "bid": quote.bid,
                "ask": quote.ask,
                "last": quote.last,
            }
        )
    return {"status": "READ_ONLY", "quotes": quotes}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only MT5 market monitor")
    parser.add_argument("--config", default="config.mt5.json")
    parser.add_argument("--once", action="store_true", help="collect one snapshot and exit")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("alpha_mt5.monitor")
    adapter = None
    try:
        config = load_config(args.config)
        try:
            import MetaTrader5 as mt5_api
        except ImportError as exc:
            raise RuntimeError("MetaTrader5 Python package is not installed in this Python environment") from exc
        adapter = ReadOnlyMT5Adapter(mt5_api)
        adapter.connect()
        logger.info("Starting READ_ONLY monitor for %d broker symbols", len(config.symbols))
        while True:
            try:
                snapshot = collect_cycle(adapter, config.symbols)
                logger.info(json.dumps(snapshot, allow_nan=False, separators=(",", ":")))
            except Exception as exc:
                logger.warning("Monitoring cycle blocked: %s", exc)
            if args.once:
                break
            time.sleep(config.poll_interval_seconds)
        return 0
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
        return 0
    except Exception as exc:
        logger.error("Monitor could not start: %s", exc)
        return 2
    finally:
        if adapter is not None:
            adapter.close()


if __name__ == "__main__":
    raise SystemExit(main())
