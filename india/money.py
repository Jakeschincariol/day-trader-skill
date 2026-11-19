"""Rupee formatting with Indian digit grouping (lakhs, crores)."""

from decimal import Decimal, ROUND_HALF_UP


def _group(int_part: str) -> str:
    if len(int_part) <= 3:
        return int_part
    head, tail = int_part[:-3], int_part[-3:]
    pairs = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ",".join(pairs + [tail])


def inr(x: float, decimals: int = 2) -> str:
    q = Decimal(1) if decimals == 0 else Decimal(1).scaleb(-decimals)
    d = Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP)
    sign = "-" if d < 0 else ""
    text = "{:f}".format(abs(d))
    int_part, _, frac = text.partition(".")
    return "%s₹%s%s" % (sign, _group(int_part), ("." + frac) if decimals else "")


def crore(x: float) -> str:
    return inr(float(x) / 1e7) + " cr"


def lakh(x: float) -> str:
    return inr(float(x) / 1e5) + " lakh"
