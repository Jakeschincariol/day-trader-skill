
import json
import os
from pathlib import Path

DEFAULT_FILE = Path(__file__).with_name("nse_signal_history.json")


def claim_signal(symbol, signal_date, path=DEFAULT_FILE):
    """Record a signal once per symbol per date.

    Returns True for a new signal and False for a duplicate.
    """
    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("Symbol cannot be empty")

    date_key = str(signal_date)

    history_path = Path(path)

    if history_path.exists():
        with history_path.open("r", encoding="utf-8") as file:
            history = json.load(file)
    else:
        history = {}

    if not isinstance(history, dict):
        raise ValueError("Invalid signal history format")

    symbols = history.get(date_key, [])

    if not isinstance(symbols, list):
        raise ValueError("Invalid signal history entry")

    if symbol in symbols:
        return False

    symbols.append(symbol)
    history[date_key] = symbols

    temp_path = history_path.with_suffix(history_path.suffix + ".tmp")

    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(history, file, indent=2)
        os.replace(temp_path, history_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return True

