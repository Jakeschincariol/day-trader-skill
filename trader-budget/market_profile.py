"""Shared optional market profiles for trader skills.

US remains the default for backward compatibility. Set {"market":"india", ...}
in trader/config.json to use NSE/BSE, IST and INR behavior.
"""
import datetime
import json
import os

US = {
    "market": "us", "timezone": "America/New_York", "currency": "USD",
    "open": "09:30", "close": "16:00", "calendar": "NYSE",
}
INDIA = {
    "market": "india", "timezone": "Asia/Kolkata", "currency": "INR",
    "exchange": "NSE", "open": "09:15", "close": "15:30",
    "calendar": "NSE", "suffix": ".NS", "no_entries_before": "09:45",
    "no_entries_after": "15:15", "flat_by": "15:25",
}

NSE_HOLIDAYS_2026 = {
    "2026-01-26": "Republic Day", "2026-03-03": "Holi",
    "2026-03-26": "Ram Navami", "2026-03-31": "Mahavir Jayanti",
    "2026-04-03": "Good Friday", "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day", "2026-08-15": "Independence Day",
    "2026-10-02": "Mahatma Gandhi Jayanti", "2026-11-26": "Guru Nanak Jayanti",
    "2026-12-25": "Christmas",
}
NSE_HOLIDAYS_2027 = {
    "2027-01-26": "Republic Day", "2027-03-22": "Holi",
    "2027-03-26": "Ram Navami", "2027-04-14": "Ambedkar Jayanti",
    "2027-04-02": "Good Friday", "2027-05-01": "Maharashtra Day",
    "2027-08-15": "Independence Day", "2027-10-02": "Mahatma Gandhi Jayanti",
    "2027-12-25": "Christmas",
}


def load(path="trader/config.json"):
    cfg = dict(US)
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            if isinstance(doc, dict):
                cfg.update(doc)
        except (OSError, ValueError):
            pass
    if str(cfg.get("market", "us")).lower() == "india":
        base = dict(INDIA)
        base.update(cfg)
        cfg = base
    return cfg


def is_india(cfg):
    return str((cfg or {}).get("market", "us")).lower() == "india"


def utc_to_local(utc, cfg):
    if getattr(utc, "tzinfo", None) is not None:
        utc = utc.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    if is_india(cfg):
        return utc + datetime.timedelta(hours=5, minutes=30)
    # US compatibility: callers using this profile keep the US DST logic.
    return utc


def local_to_utc(local, cfg):
    if is_india(cfg):
        return local - datetime.timedelta(hours=5, minutes=30)
    return local


def parse_clock(text, default):
    text = str(text or default)
    h, m = text.strip().split(":")
    return datetime.time(int(h), int(m))


def trading_day(day, cfg):
    if day.weekday() >= 5:
        return False, "weekend"
    if is_india(cfg):
        calendar = dict(NSE_HOLIDAYS_2026)
        calendar.update(NSE_HOLIDAYS_2027)
        name = calendar.get(day.isoformat())
        if name:
            return False, "NSE holiday: " + name
        return True, ""
    return True, ""


def session(day, cfg):
    ok, _ = trading_day(day, cfg)
    if not ok:
        return None
    return parse_clock(cfg.get("open"), "09:15" if is_india(cfg) else "09:30"), \
           parse_clock(cfg.get("close"), "15:30" if is_india(cfg) else "16:00")


def yahoo_symbol(symbol, cfg=None, exchange=None):
    """Canonical Yahoo symbol: preserve .NS/.BO, otherwise suffix Indian stocks."""
    symbol = str(symbol or "").strip().upper()
    if not symbol:
        return ""
    if is_india(cfg or {}):
        if symbol.endswith(".NS") or symbol.endswith(".BO"):
            return symbol
        exchange = (exchange or (cfg or {}).get("exchange") or "NSE").upper()
        return symbol + (".BO" if exchange == "BSE" or exchange == "BO" else ".NS")
    return symbol.replace(".", "-")


def currency_symbol(cfg):
    return "₹" if is_india(cfg) else "$"


def format_money(value, cfg):
    sign = currency_symbol(cfg)
    text = "{:,.2f}".format(float(value)).replace(".00", "")
    return sign + text


def bare_symbol(symbol):
    symbol = str(symbol or "").strip().upper()
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol.rsplit(".", 1)[0]
    return symbol
