import contextlib
import io
import unittest
from datetime import date, datetime

import _load  # noqa: F401  (sets sys.path and INDIA_HOLIDAYS)
from india import market as m


@contextlib.contextmanager
def captured_stderr():
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        yield buf


class Market(unittest.TestCase):
    def setUp(self):
        m._reset()

    def test_weekend_and_holiday_closed(self):
        self.assertFalse(m.is_trading_day(date(2026, 11, 21)))        # Saturday
        self.assertFalse(m.is_trading_day(date(2026, 11, 24)))        # fixture holiday
        self.assertEqual(m.holiday_name(date(2026, 11, 24)), "Guru Nanak Jayanti")
        self.assertTrue(m.is_trading_day(date(2026, 11, 23)))

    def test_add_trading_days_skips_holidays(self):
        self.assertEqual(m.add_trading_days(date(2026, 11, 20), 2), date(2026, 11, 25))
        self.assertEqual(m.trading_days_between(date(2026, 11, 20), date(2026, 11, 25)), 2)

    def test_prev_and_next_trading_day(self):
        self.assertEqual(m.next_trading_day(date(2026, 11, 23)), date(2026, 11, 25))
        self.assertEqual(m.prev_trading_day(date(2026, 11, 25)), date(2026, 11, 23))

    def test_session(self):
        self.assertEqual(m.session(date(2026, 11, 23)), (m.OPEN, m.CLOSE))
        self.assertIsNone(m.session(date(2026, 11, 24)))

    def test_market_status(self):
        s = m.market_status(datetime(2026, 11, 23, 9, 14))
        self.assertFalse(s["open"])
        self.assertEqual(s["next_open"], "2026-11-23T09:15")
        self.assertTrue(m.market_status(datetime(2026, 11, 23, 9, 15))["open"])
        self.assertFalse(m.market_status(datetime(2026, 11, 23, 15, 30))["open"])
        self.assertEqual(m.market_status(datetime(2026, 11, 23, 16, 0))["next_open"], "2026-11-25T09:15")
        self.assertIn("Guru Nanak Jayanti", m.market_status(datetime(2026, 11, 24, 10, 0))["reason"])

    def test_last_final_bar_date(self):
        self.assertEqual(m.last_final_bar_date(datetime(2026, 11, 23, 15, 49)), date(2026, 11, 20))
        self.assertEqual(m.last_final_bar_date(datetime(2026, 11, 23, 15, 50)), date(2026, 11, 23))
        self.assertEqual(m.last_final_bar_date(datetime(2026, 11, 24, 18, 0)), date(2026, 11, 23))

    def test_missing_year_warns_once(self):
        with captured_stderr() as err:
            self.assertTrue(m.is_trading_day(date(2027, 1, 26)))       # no 2027 list: weekdays open
            m.is_trading_day(date(2027, 1, 27))
        self.assertEqual(err.getvalue().count("no NSE holiday list for 2027"), 1)

    def test_now_ist_pinned(self):
        self.assertEqual(m.now_ist("2026-11-18 16:00"), datetime(2026, 11, 18, 16, 0))

    def test_now_ist_live_is_ist(self):
        import datetime as dt
        utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        delta = m.now_ist() - utc
        self.assertAlmostEqual(delta.total_seconds(), 5.5 * 3600, delta=5)


if __name__ == "__main__":
    unittest.main()
