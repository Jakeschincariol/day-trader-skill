"""trader/config.json with the pack's defaults underneath, and small helpers
for the trader/ working folder."""

import hashlib
import json
import os
from typing import Dict

from india import charges

DEFAULTS = {
    "capital": 500000,
    "cash": None,                    # None: capital minus the cost of open positions
    "risk_per_trade_pct": 1.0,
    "max_position_pct": 20.0,
    "cash_buffer_pct": 10.0,
    "min_order": 1000,
    "min_reward_risk": 1.5,
    "max_open_positions": 5,
    "max_heat_pct": 5.0,
    "max_hold_days": 15,
    "stop_method": "swing-low",
    "target": "2R",
    "entry_style": "limit",
    "entry_limit_buffer_pct": 0.5,
    "gtt_slippage_pct": 1.0,
    "min_price": 50,
    "min_traded_value": 5e7,         # Rs 5 crore, 20-day average of close x volume
    "include_be": False,
    "block_bands": ["2", "5"],
    "warn_bands": ["10"],
    "block_on_results": False,
    "blocked": [],
    "tick_schedule": None,           # None: india.ticks.DEFAULT_SCHEDULE
    "charges": dict(charges.DEFAULTS),
}


def load(trader_dir: str) -> Dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    path = os.path.join(trader_dir, "config.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            user = json.load(fh)
        for k, v in user.items():
            if k == "charges" and isinstance(v, dict):
                cfg["charges"].update(v)
            else:
                cfg[k] = v
    return cfg


def trader_path(trader_dir: str, name: str) -> str:
    path = os.path.join(trader_dir, name)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return path


def read_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str, doc) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def fingerprint(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()
