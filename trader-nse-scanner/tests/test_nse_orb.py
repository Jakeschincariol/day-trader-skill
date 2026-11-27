
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from nse_orb import analyse

IST = ZoneInfo("Asia/Kolkata")


def candle(hour, minute, open_price, high, low, close, volume=1000):
    return {
        "time": datetime(
            2026, 11, 23, hour, minute, tzinfo=IST
        ),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


class TestNSEORB(unittest.TestCase):

    def setUp(self):
        self.now = datetime(
            2026, 11, 23, 10, 0, tzinfo=IST
        )

        self.opening = [
            candle(9, 15, 100, 105, 98, 103),
            candle(9, 20, 103, 106, 100, 104),
            candle(9, 25, 104, 105, 99, 102),
        ]

    def breakout_bars(self):
        return self.opening + [
            candle(9, 30, 102, 105, 101, 104),
            candle(9, 35, 104, 105, 102, 103),
            candle(9, 40, 103, 105, 102, 104),
            candle(9, 45, 104, 105, 102, 103),
            candle(9, 50, 103, 105, 102, 104),
            candle(9, 55, 104, 108, 103, 107, 2000),
        ]

    def test_valid_breakout(self):
        result = analyse(
            "TEST.NS", self.breakout_bars(), self.now
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(
            result["status"], "PAPER BUY CANDIDATE"
        )

    def test_signal_date(self):
        result = analyse(
            "TEST.NS", self.breakout_bars(), self.now
        )

        self.assertEqual(
            result["signal_date"], "2026-11-23"
        )

    def test_signal_date_uses_breakout_candle_date(self):
        result = analyse(
            "TEST.NS", self.breakout_bars(), self.now
        )

        self.assertEqual(
            result["signal_date"],
            self.breakout_bars()[-1]["time"].date().isoformat()
        )

    def test_no_breakout(self):
        bars = self.opening + [
            candle(9, 30, 102, 105, 101, 104),
            candle(9, 35, 104, 105, 102, 103),
            candle(9, 40, 103, 105, 102, 104),
            candle(9, 45, 104, 105, 102, 103),
            candle(9, 50, 103, 105, 102, 104),
            candle(9, 55, 104, 106, 103, 104, 2000),
        ]

        result = analyse("TEST.NS", bars, self.now)

        self.assertIsInstance(result, dict)
        self.assertEqual(
            result["status"], "NO CONFIRMED BREAKOUT"
        )

    def test_missing_opening_candle(self):
        bars = self.opening[1:] + self.breakout_bars()[3:]

        result = analyse("TEST.NS", bars, self.now)

        self.assertEqual(
            result,
            "Opening range incomplete or missing candles"
        )

    def test_duplicate_candle(self):
        bars = self.breakout_bars()
        bars.append(bars[-1].copy())

        result = analyse("TEST.NS", bars, self.now)

        self.assertEqual(
            result, "Duplicate candle timestamp"
        )

    def test_invalid_ohlc(self):
        bars = self.breakout_bars()
        bars[0]["high"] = 90

        result = analyse("TEST.NS", bars, self.now)

        self.assertEqual(
            result, "Invalid OHLC relationship"
        )

    def test_missing_middle_candle(self):
        bars = [
            self.opening[0],
            self.opening[2],
        ] + self.breakout_bars()[3:]

        result = analyse("TEST.NS", bars, self.now)

        self.assertEqual(
            result,
            "Opening range incomplete or missing candles"
        )

    def test_negative_volume(self):
        bars = self.breakout_bars()
        bars[-1]["volume"] = -100

        result = analyse("TEST.NS", bars, self.now)

        self.assertEqual(
            result, "Invalid price or volume"
        )

    def test_weak_breakout_volume(self):
        bars = self.breakout_bars()
        bars[-1]["volume"] = 1200

        result = analyse("TEST.NS", bars, self.now)

        self.assertIsInstance(result, dict)
        self.assertEqual(
            result["status"], "NO CONFIRMED BREAKOUT"
        )

    def test_insufficient_volume_history(self):
        bars = self.opening + [
            candle(9, 30, 102, 108, 101, 107, 2000),
        ]

        result = analyse("TEST.NS", bars, self.now)

        self.assertIsInstance(result, dict)
        self.assertEqual(
            result["status"], "NO CONFIRMED BREAKOUT"
        )

    def test_incomplete_breakout_candle_is_ignored(self):
        bars = self.breakout_bars()

        later_now = datetime(
            2026, 11, 23, 9, 57, tzinfo=IST
        )

        result = analyse("TEST.NS", bars, later_now)

        self.assertIsInstance(result, dict)
        self.assertEqual(
            result["status"], "NO CONFIRMED BREAKOUT"
        )

    def test_completed_breakout_candle_is_included(self):
        bars = self.breakout_bars()

        result = analyse("TEST.NS", bars, self.now)

        self.assertIsInstance(result, dict)
        self.assertEqual(
            result["status"], "PAPER BUY CANDIDATE"
        )

    def test_future_candle_rejected(self):
        bars = self.opening + [
            candle(10, 5, 102, 105, 101, 104),
        ]

        result = analyse("TEST.NS", bars, self.now)

        self.assertEqual(
            result, "Future candle timestamp"
        )

    def test_invalid_5_minute_timestamp_rejected(self):
        bars = self.breakout_bars()
        bars[-1]["time"] = datetime(
            2026, 11, 23, 9, 56, tzinfo=IST
        )

        result = analyse("TEST.NS", bars, self.now)

        self.assertEqual(
            result, "Invalid 5-minute candle timestamp"
        )

    def test_timezone_equivalent_duplicate_rejected(self):
        bars = self.breakout_bars()
        duplicate = bars[-1].copy()
        duplicate["time"] = duplicate["time"].astimezone(
            ZoneInfo("UTC")
        )
        bars.append(duplicate)

        result = analyse("TEST.NS", bars, self.now)

        self.assertEqual(
            result, "Duplicate candle timestamp"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
