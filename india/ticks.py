"""NSE equity tick sizes.

DEFAULT_SCHEDULE follows NSE's 2025 revision of tick sizes by price band
(under Rs 250: 0.01; 250-1,000: 0.05; 1,000-5,000: 0.10; 5,000-10,000:
0.50; 10,000-20,000: 1.00; above: 5.00). Re-check it against the current
NSE circular; a different schedule can be passed in (config "tick_schedule").

All arithmetic is in integer paise, so 0.1 + 0.2 noise never moves a price.
"""

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

# (upper bound in rupees, exclusive; None = no bound), tick in paise
DEFAULT_SCHEDULE = [(250, 1), (1000, 5), (5000, 10), (10000, 50), (20000, 100), (None, 500)]


def _paise(price) -> Decimal:
    return Decimal(str(price)) * 100


def tick_paise(price: float, schedule=None) -> int:
    for bound, tick in (schedule or DEFAULT_SCHEDULE):
        if bound is None or float(price) < bound:
            return int(tick)
    return int((schedule or DEFAULT_SCHEDULE)[-1][1])


def _round(price, schedule, mode) -> float:
    t = Decimal(tick_paise(price, schedule))
    p = _paise(price)
    units = (p / t).quantize(Decimal(1), rounding=mode)
    return float(units * t / 100)


def round_down(price: float, schedule=None) -> float:
    return _round(price, schedule, ROUND_FLOOR)


def round_up(price: float, schedule=None) -> float:
    return _round(price, schedule, ROUND_CEILING)


def round_nearest(price: float, schedule=None) -> float:
    return _round(price, schedule, ROUND_HALF_UP)


def is_valid(price: float, schedule=None) -> bool:
    p = _paise(price)
    return p == p.to_integral_value() and p % tick_paise(price, schedule) == 0
