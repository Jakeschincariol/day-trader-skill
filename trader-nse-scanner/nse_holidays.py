
from datetime import date, timedelta


NSE_HOLIDAYS_2026 = {
    "2026-01-15": "Municipal Corporation Election - Maharashtra",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas",
}


def get_holiday_reason(check_date):
    """
    Return the NSE holiday reason or None.
    check_date must be a datetime.date object.
    """
    return NSE_HOLIDAYS_2026.get(check_date.isoformat())


def is_weekend(check_date):
    return check_date.weekday() >= 5


def is_market_holiday(check_date):
    return is_weekend(check_date) or get_holiday_reason(check_date) is not None


def next_trading_day(check_date):
    """
    Find the next weekday that is not in the 2026 holiday calendar.
    """
    next_date = check_date + timedelta(days=1)

    while is_market_holiday(next_date):
        next_date += timedelta(days=1)

    return next_date
