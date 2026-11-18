"""Estimated charges for a delivery (CNC) round trip on NSE.

The defaults were checked on DEFAULTS["last_checked"] and are an estimate:
brokers differ (set "brokerage_per_order" and "dp_per_sell" in
trader/config.json under "charges") and the exchange and government change
rates from time to time.
"""

from typing import Dict, Optional

DEFAULTS = {
    "last_checked": "2026-11-19",
    "brokerage_per_order": 0.0,
    "stt_pct": 0.1,            # securities transaction tax, delivery, buy and sell
    "exchange_txn_pct": 0.00297,
    "sebi_per_crore": 10.0,
    "stamp_buy_pct": 0.015,
    "gst_pct": 18.0,           # on brokerage + exchange + SEBI fees
    "dp_per_sell": 15.93,      # depository charge per scrip sold
}


def delivery_round_trip(buy_value: float, sell_value: float, table: Optional[Dict] = None) -> Dict:
    t = dict(DEFAULTS)
    t.update(table or {})
    turnover = float(buy_value) + float(sell_value)
    brokerage = 2 * float(t["brokerage_per_order"])
    stt = turnover * t["stt_pct"] / 100
    exchange = turnover * t["exchange_txn_pct"] / 100
    sebi = turnover * t["sebi_per_crore"] / 1e7
    stamp = float(buy_value) * t["stamp_buy_pct"] / 100
    gst = (brokerage + exchange + sebi) * t["gst_pct"] / 100
    dp = float(t["dp_per_sell"])
    out = {"brokerage": brokerage, "stt": stt, "exchange": exchange, "sebi": sebi,
           "stamp": stamp, "gst": gst, "dp": dp}
    out = {k: round(v, 2) for k, v in out.items()}
    out["total"] = round(sum(out.values()), 2)
    return out
