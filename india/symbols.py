"""NSE / BSE symbols: parse what the user types, validate, map to Yahoo.

    TCS, tcs, TCS.NS, NSE:TCS   -> Sym("TCS", "NSE")
    RELIANCE.BO, BSE:RELIANCE   -> Sym("RELIANCE", "BSE")
    M&M, BAJAJ-AUTO             -> kept as is ('&' and '-' are part of NSE codes)
"""

import re
import urllib.parse
from typing import NamedTuple

VALID = re.compile(r"^[A-Z0-9&\-]{1,20}$")
SUFFIX = {".NS": "NSE", ".BO": "BSE"}
YAHOO = {"NSE": ".NS", "BSE": ".BO"}


class Sym(NamedTuple):
    code: str
    exchange: str


def parse(text: str, default_exchange: str = "NSE") -> Sym:
    raw = str(text or "").strip().upper()
    exchange = default_exchange.upper()
    if ":" in raw:
        exchange, raw = raw.split(":", 1)
        if exchange not in YAHOO:
            raise ValueError("%r: exchange must be NSE or BSE" % text)
    else:
        for suf, ex in SUFFIX.items():
            if raw.endswith(suf):
                raw, exchange = raw[:-len(suf)], ex
                break
    if exchange not in YAHOO:
        raise ValueError("%r: exchange must be NSE or BSE" % text)
    if not VALID.match(raw):
        raise ValueError("%r is not an NSE/BSE equity symbol (letters, digits, & and - only, "
                         "up to 20; no F&O contracts)" % text)
    return Sym(raw, exchange)


def to_yahoo(s: Sym) -> str:
    return s.code + YAHOO[s.exchange]


def yahoo_path_part(s: Sym) -> str:
    return urllib.parse.quote(to_yahoo(s), safe=".")


def display(s: Sym) -> str:
    return s.code if s.exchange == "NSE" else "%s (%s)" % (s.code, s.exchange)


def safe_filename(s: Sym) -> str:
    name = to_yahoo(s).replace("&", "_and_")
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)
