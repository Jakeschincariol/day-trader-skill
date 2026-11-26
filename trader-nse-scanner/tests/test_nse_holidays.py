
import unittest
from datetime import date

from nse_holidays import (
    get_holiday_reason,
    is_weekend,
    is_market_holiday,
    next_trading_day,
)


class TestNSEHolidays(unittest.TestCase):

    def test_nse_holiday_detected(self):
        result = get_holiday_reason(date(2026, 11, 24))
        self.assertEqual(
            result, "Prakash Gurpurb Sri Guru Nanak Dev"
        )

    def test_normal_trading_day(self):
        self.assertIsNone(
            get_holiday_reason(date(2026, 11, 25))
        )

    def test_weekend_detected(self):
        self.assertTrue(is_weekend(date(2026, 11, 28)))

    def test_weekend_is_market_holiday(self):
        self.assertTrue(
            is_market_holiday(date(2026, 11, 28))
        )

    def test_nse_holiday_is_market_holiday(self):
        self.assertTrue(
            is_market_holiday(date(2026, 11, 24))
        )

    def test_normal_day_is_not_market_holiday(self):
        self.assertFalse(
            is_market_holiday(date(2026, 11, 25))
        )

    def test_next_trading_day_after_holiday(self):
        self.assertEqual(
            next_trading_day(date(2026, 11, 24)),
            date(2026, 11, 25)
        )

    def test_next_trading_day_skips_weekend(self):
        self.assertEqual(
            next_trading_day(date(2026, 11, 27)),
            date(2026, 11, 30)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
