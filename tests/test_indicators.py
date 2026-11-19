import unittest
from datetime import date, timedelta

import _load  # noqa: F401
from india import indicators as ind


def bar(d="2026-01-01", o=None, h=None, l=None, c=100.0, v=1000):
    o = c if o is None else o
    return {"d": d, "o": o, "h": max(o, c) if h is None else h, "l": min(o, c) if l is None else l, "c": c, "v": v}


def flat_bars(n, c=100.0):
    return [bar(c=c) for _ in range(n)]


def dated(bars, start=date(2026, 1, 5), holiday_every=0):
    """Give bars consecutive weekday dates, skipping every Nth weekday as a holiday."""
    d, k = start, 0
    for b in bars:
        while True:
            if d.weekday() < 5:
                k += 1
                if not (holiday_every and k % holiday_every == 0):
                    break
            d += timedelta(days=1)
        b["d"] = d.isoformat()
        d += timedelta(days=1)
    return bars


class Indicators(unittest.TestCase):
    def test_sma(self):
        self.assertEqual(ind.sma([1.0, 2.0, 3.0, 4.0], 2), [None, 1.5, 2.5, 3.5])

    def test_rsi_edges(self):
        self.assertEqual(ind.rsi_wilder([float(x) for x in range(1, 31)])[-1], 100.0)   # only gains
        self.assertIsNone(ind.rsi_wilder([1.0] * 10)[-1])                                # under 15 closes
        alt = [100.0 + (1 if k % 2 else -1) for k in range(60)]
        self.assertAlmostEqual(ind.rsi_wilder(alt)[-1], 50.0, delta=3)

    def test_rsi_matches_the_original_pack(self):
        closes = [100, 102, 101, 99, 98, 97, 99, 103, 104, 102, 101, 100, 98, 96, 95, 97, 99, 98, 101, 104]
        closes = [float(c) for c in closes]
        # value from the original pack's rsi() (git show 3d0f4ef:trader-scanner/scan.py) on the same list
        self.assertAlmostEqual(ind.rsi_wilder(closes)[-1], 58.90102, places=4)

    def test_atr(self):
        bars = [bar(o=100, h=102, l=98, c=100) for _ in range(20)]
        self.assertAlmostEqual(ind.atr(bars, 14)[-1], 4.0)
        self.assertIsNone(ind.atr(bars[:10], 14)[-1])

    def test_avg_traded_value(self):
        bars = [bar(c=100, v=1000) for _ in range(25)]
        self.assertEqual(ind.avg_traded_value(bars, 20), 100000.0)
        self.assertIsNone(ind.avg_traded_value(bars[:5], 20))

    def test_breakout_20d_level(self):
        bars = flat_bars(20, c=100) + [bar(c=101, h=102)]
        self.assertEqual(ind.setups_at(bars, 20)["breakout_20d"], 100)

    def test_short_history_skips_52w(self):
        bars = dated(flat_bars(100, c=100) + [bar(c=150, h=151)])
        got = ind.setups_at(bars, 100)
        self.assertNotIn("breakout_52w", got)
        self.assertIn("breakout_20d", got)

    def test_breakout_52w_on_one_year_of_bars(self):
        # Yahoo's 1y range is ~248 sessions: a calendar year, not 251 bars
        bars = dated(flat_bars(247, c=100) + [bar(c=105, h=106)], start=date(2025, 11, 18), holiday_every=17)
        self.assertEqual(len(bars), 248)
        self.assertGreaterEqual((date.fromisoformat(bars[-1]["d"]) - date(2025, 11, 18)).days, 360)
        self.assertEqual(ind.setups_at(bars, 247)["breakout_52w"], 100)

    def test_52w_window_is_one_calendar_year(self):
        bars = dated([bar(c=100, h=200)] + flat_bars(300, c=100) + [bar(c=150, h=151)], start=date(2025, 6, 2))
        self.assertEqual(ind.setups_at(bars, len(bars) - 1)["breakout_52w"], 100)   # the 200 high is > 1 year old

    def test_bull_flag(self):
        rise = [bar(c=100 + 2 * k) for k in range(16)]          # 100 .. 130
        flag = [bar(c=c, h=c + 1) for c in (129, 130, 128, 129, 130)]
        bars = flat_bars(10) + rise + flag
        self.assertEqual(ind.setups_at(bars, len(bars) - 1)["bull_flag"], 131)

    def test_reclaim_ma20(self):
        bars = flat_bars(20, c=100) + [bar(c=95), bar(c=101, h=103)]
        self.assertEqual(ind.setups_at(bars, len(bars) - 1)["reclaim_ma20"], 103)

    def test_oversold_and_bounce(self):
        down = [bar(c=200 - 5 * k) for k in range(20)]
        got = ind.setups_at(down, 19)
        self.assertIn("oversold", got)
        self.assertIsNone(got["oversold"])
        up = down + [bar(c=110, h=112)]
        self.assertEqual(ind.setups_at(up, 20)["oversold_bounce"], 112)

    def test_pullback_ma50(self):
        rising = [bar(c=100 + k * 0.5) for k in range(60)]      # sma50 rising, last close 129.5
        sma50 = sum(b["c"] for b in rising[-50:]) / 50
        dip = bar(o=sma50 + 1, h=sma50 + 2, l=sma50 * 1.01, c=sma50 + 1)
        bars = rising + [dip]
        self.assertEqual(ind.setups_at(bars, len(bars) - 1)["pullback_ma50"], dip["h"])

    def test_setups_are_named(self):
        bars = flat_bars(20, c=100) + [bar(c=101, h=102)]
        self.assertTrue(set(ind.setups_at(bars, 20)) <= set(ind.SETUPS))


if __name__ == "__main__":
    unittest.main()
