
from datetime import datetime, date, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def to_ist(value=None):
    if value is None:
        return datetime.now(IST)

    if value.tzinfo is None:
        return value.replace(tzinfo=IST)

    return value.astimezone(IST)


def is_trading_day(day, holidays=None):
    holidays = set(holidays or [])

    if isinstance(day, datetime):
        day = day.date()

    if day.weekday() >= 5:
        return False

    return day.isoformat() not in holidays


def session_bounds(day):
    if isinstance(day, datetime):
        day = day.date()

    start = datetime.combine(day, MARKET_OPEN, tzinfo=IST)
    end = datetime.combine(day, MARKET_CLOSE, tzinfo=IST)

    return start, end


def is_regular_session(value=None, holidays=None):
    current = to_ist(value)

    if not is_trading_day(current.date(), holidays):
        return False

    return MARKET_OPEN <= current.time() < MARKET_CLOSE


def market_status(value=None, holidays=None):
    current = to_ist(value)

    if not is_trading_day(current.date(), holidays):
        return "MARKET CLOSED - WEEKEND OR HOLIDAY"

    if current.time() < MARKET_OPEN:
        return "PRE-MARKET"

    if current.time() >= MARKET_CLOSE:
        return "MARKET CLOSED"

    return "MARKET OPEN"


if __name__ == "__main__":
    now = datetime.now(IST)

    print("NSE MARKET CLOCK")
    print("----------------")
    print("Current IST:", now.strftime("%Y-%m-%d %H:%M:%S"))
    print("Market status:", market_status(now))
    print("Market hours: 09:15 - 15:30 IST")
