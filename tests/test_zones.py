"""trader-zones: supply and demand zones and the 5m/3m entry. Offline, on small synthetic bars
built by hand so every expected number can be checked on paper."""

import contextlib
import datetime
import io
import json
import math
import os
import tempfile
import unittest

from _load import load

z = load("trader-zones", "zones")
CFG = z.read_config(None)


def et(y, mo, d, h=0, mi=0):
    return z.eastern_to_ts(datetime.datetime(y, mo, d, h, mi))


def mk(t0, step, rows):
    return [{"t": t0 + step * i, "o": o, "h": h, "l": l, "c": c} for i, (o, h, l, c) in enumerate(rows)]


def noise(n, base=100.0, amp=0.6):
    """A calm wave around `base`: small bodies, small wicks, real swing highs and lows."""
    rows, prev = [], base
    for i in range(n):
        c = base + amp * math.sin(i * 0.8)
        rows.append((prev, max(prev, c) + 0.25, min(prev, c) - 0.25, c))
        prev = c
    return rows


T0 = et(2026, 10, 26, 7, 0)  # Mon Oct 26 2026, 7:00 AM New York

# --- a demand zone on 30-minute bars: calm, one long-wicked small candle, one big up candle ---
ZONE_CANDLE = (100.0, 100.8, 99.2, 100.05)
DISPLACEMENT = (100.1, 104.6, 100.0, 104.5)
AFTER_UP = [(104.5, 105.0, 104.4, 104.9), (104.9, 105.4, 104.8, 105.3), (105.3, 105.8, 105.2, 105.7)]


# find_zones skips its first 20 bars (ATR and swing warm-up), so the break must come after that
PRE = 22
ZSTART = et(2026, 10, 25, 20, 0)   # Sunday 8 PM New York: bar 22 (the zone candle) opens Monday 7:00 AM
SOLID = (100.0, 100.9, 99.95, 100.85)   # big body, tiny wicks: never a zone candle


def zone_rows(extra=()):
    return noise(PRE) + [ZONE_CANDLE, DISPLACEMENT] + AFTER_UP + list(extra)


def swing_rows(high):
    """The latest swing high before the zone candle is `high`; later highs are all lower."""
    rows = noise(PRE)
    rows[18] = (100.0, high, 99.8, 100.1)
    rows[19] = (99.7, 99.9, 99.4, 99.6)
    rows[20] = (99.6, 99.8, 99.3, 99.5)
    rows[21] = (99.5, 99.7, 99.2, 99.4)
    return rows + [ZONE_CANDLE, DISPLACEMENT] + AFTER_UP


# --- a full long entry on 5-minute and 3-minute bars (hand-built, see the comments) ---
M5_ROWS = noise(16) + [
    (99.6, 100.0, 98.6, 99.9),      # 16 the sweep: wick under the swing low, close back above it
    (99.9, 103.0, 99.8, 102.9),     # 17
    (100.6, 106.0, 100.5, 105.9),   # 18
    (105.9, 110.0, 102.0, 109.8),   # 19 leg high 110.0
    (109.8, 110.0, 107.0, 107.2),   # 20
    (107.2, 107.3, 103.0, 103.2),   # 21
    (101.5, 101.6, 101.0, 101.2),   # 22 first bar of the gap
    (101.3, 103.1, 101.2, 103.0),   # 23
    (102.9, 103.5, 102.4, 103.2),   # 24 gap 101.6 to 102.4, midpoint 102.0
    (103.2, 103.3, 102.3, 102.5),   # 25 price trades back into the gap
    (102.5, 104.0, 102.4, 103.9),
    (103.9, 105.0, 103.8, 104.9),
]
M3_ROWS = [(100.4 + 0.1 * (i % 3), 100.9, 100.1, 100.5) for i in range(27)] + [
    (100.2, 100.6, 98.8, 100.4),    # 27
    (100.4, 103.0, 100.3, 102.9),   # 28
    (102.9, 106.0, 102.8, 105.9),   # 29
    (105.9, 110.0, 105.8, 109.8),   # 30 the high of the leg
    (109.8, 109.9, 107.0, 107.2),   # 31
    (107.2, 107.3, 104.0, 104.2),   # 32
    (104.2, 104.3, 102.0, 102.2),   # 33
    (102.2, 103.9, 102.0, 103.8),   # 34
    (103.8, 104.6, 103.5, 104.4),   # 35 the lower high, 104.6
    (104.4, 104.5, 103.0, 103.2),   # 36
    (103.2, 103.4, 102.2, 102.4),   # 37
    (102.4, 102.8, 101.8, 102.0),   # 38
    (102.0, 102.5, 101.4, 101.6),   # 39
    (101.6, 102.4, 101.0, 102.2),   # 40
    (102.2, 102.6, 101.9, 102.4),   # 41
    (102.4, 104.0, 102.3, 103.9),   # 42
    (103.9, 105.2, 103.8, 105.0),   # 43 closes above 104.6: the CHoCH
    (105.0, 105.5, 104.5, 105.3),
    (105.3, 105.6, 104.8, 105.1),
]


def entry_data(t0=T0):
    m5, m3 = mk(t0, 300, M5_ROWS), mk(t0, 180, M3_ROWS)
    zone = {"kind": "demand", "t": m5[10]["t"], "high": 99.8, "low": 99.0, "touched_t": m5[16]["t"],
            "status": "touched", "di": 5, "tf": "30m"}
    targets = [p[2] for p in z.pivots(m5, 2)[0]]
    return m5, m3, zone, targets


def chart_json(bars):
    return json.dumps({"chart": {"result": [{
        "timestamp": [b["t"] for b in bars],
        "indicators": {"quote": [{"open": [b["o"] for b in bars], "high": [b["h"] for b in bars],
                                  "low": [b["l"] for b in bars], "close": [b["c"] for b in bars]}]}}],
        "error": None}})


class Markets(unittest.TestCase):
    def test_the_five_markets_include_mgc(self):
        self.assertEqual(sorted(z.MARKETS), ["EURUSD", "GBPUSD", "MGC", "NQ", "XAUUSD"])
        self.assertEqual(z.MARKETS["MGC"]["yahoo"], "MGC=F")
        self.assertEqual(z.MARKETS["NQ"]["yahoo"], "NQ=F")
        self.assertEqual(z.MARKETS["GBPUSD"]["yahoo"], "GBPUSD=X")

    def test_aliases_and_case(self):
        self.assertEqual(z.resolve("nas100"), "NQ")
        self.assertEqual(z.resolve("US100"), "NQ")
        self.assertEqual(z.resolve("GBP/USD"), "GBPUSD")
        self.assertEqual(z.resolve("gold"), "XAUUSD")
        self.assertEqual(z.resolve("mgc"), "MGC")

    def test_unknown_market_is_an_error_not_a_guess(self):
        with self.assertRaises(z.ZoneError):
            z.resolve("TSLA")

    def test_markets_command_lists_all_five(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(z.main(["markets"]), 0)
        for name in ("XAUUSD", "GBPUSD", "EURUSD", "NQ", "MGC"):
            self.assertIn(name, out.getvalue())
        self.assertIn("COMEX gold futures", out.getvalue())  # says gold is futures, not spot


class Time(unittest.TestCase):
    def test_new_york_daylight_saving_edges(self):
        d = datetime.datetime
        self.assertEqual(z.eastern_offset(d(2026, 7, 1, 12)), -4)
        self.assertEqual(z.eastern_offset(d(2026, 12, 1, 12)), -5)
        self.assertEqual(z.eastern_offset(d(2026, 3, 8, 6, 59)), -5)   # the minute before spring forward
        self.assertEqual(z.eastern_offset(d(2026, 3, 8, 7, 0)), -4)
        self.assertEqual(z.eastern_offset(d(2026, 11, 1, 5, 59)), -4)  # the minute before fall back
        self.assertEqual(z.eastern_offset(d(2026, 11, 1, 6, 0)), -5)

    def test_now_in_new_york_time_round_trips(self):
        ts = z.parse_now("2026-10-26 08:15")
        self.assertEqual(z.fmt_et(ts), "Mon 10-26 08:15")
        self.assertEqual(z.utc_of(ts), datetime.datetime(2026, 10, 26, 12, 15))  # EDT is UTC-4
        with self.assertRaises(z.ZoneError):
            z.parse_now("26/10/2026 8am")

    def test_session_windows(self):
        for h, mi, want in ((2, 30, True), (4, 59, True), (5, 0, False), (7, 0, True), (9, 59, True),
                            (10, 0, False), (12, 0, False), (19, 0, True), (23, 30, True), (0, 0, False)):
            self.assertEqual(z.in_session(et(2026, 10, 26, h, mi), CFG), want, "%d:%02d" % (h, mi))


class Bars(unittest.TestCase):
    def test_resample_one_minute_to_three(self):
        base = T0 - T0 % 180
        m1 = mk(base, 60, [(1, 2, 0.5, 1.5), (1.5, 3, 1, 2), (2, 2.5, 1.8, 2.2), (2.2, 2.4, 2.0, 2.1)])
        m3 = z.resample(m1, 180)
        self.assertEqual(len(m3), 2)
        self.assertEqual((m3[0]["o"], m3[0]["h"], m3[0]["l"], m3[0]["c"]), (1, 3, 0.5, 2.2))
        self.assertEqual(m3[1]["t"], base + 180)

    def test_a_bar_counts_only_once_it_has_closed(self):
        bars = mk(T0, 300, [(1, 2, 0, 1)] * 3)
        self.assertEqual(len(z.closed_only(bars, 300, T0 + 599)), 1)
        self.assertEqual(len(z.closed_only(bars, 300, T0 + 600)), 2)

    def test_swings_are_known_only_after_they_confirm(self):
        rows = [(1, 1, 0.5, 1)] * 3 + [(1, 5, 0.5, 1)] + [(1, 1, 0.5, 1)] * 4
        ph, _ = z.pivots(mk(T0, 60, rows), 2)
        self.assertEqual(ph[0][1], 3)   # the swing is bar 3
        self.assertEqual(ph[0][0], 5)   # and is only known at bar 5
        known = z.last_known(ph, len(rows))
        self.assertIsNone(known[4])
        self.assertEqual(known[5], 5)

    def test_parse_chart_skips_null_closes_and_sorts(self):
        text = json.dumps({"chart": {"result": [{"timestamp": [120, 60, 180], "indicators": {"quote": [{
            "open": [1, 1, 1], "high": [2, 2, 2], "low": [0, 0, 0], "close": [1.5, None, 1.6]}]}}]}})
        bars = z.parse_chart(text, "NQ")
        self.assertEqual([b["t"] for b in bars], [120, 180])

    def test_ote_band_is_62_to_79_percent_back_from_the_high(self):
        lo, hi = z.ote_band(100.0, 110.0)
        self.assertAlmostEqual(lo, 102.1)
        self.assertAlmostEqual(hi, 103.8)

    def test_flip_swaps_highs_and_lows(self):
        f = z.flip_bars([{"t": 1, "o": 10, "h": 12, "l": 9, "c": 11}])[0]
        self.assertEqual((f["o"], f["h"], f["l"], f["c"]), (-10, -9, -12, -11))


class FindZones(unittest.TestCase):
    def find(self, rows):
        return z.find_zones(mk(ZSTART, 1800, rows), CFG)

    def test_a_long_wicked_small_candle_before_a_strong_break_is_a_demand_zone(self):
        zones = self.find(zone_rows())
        self.assertEqual(len(zones), 1)
        got = zones[0]
        self.assertEqual(got["kind"], "demand")
        self.assertEqual((got["low"], got["high"]), (99.2, 100.8))  # the one candle, high to low
        self.assertEqual(got["status"], "fresh")
        self.assertEqual(got["t"], ZSTART + 1800 * PRE)
        self.assertEqual(z.fmt_et(got["t"]), "Mon 10-26 07:00")

    def test_the_zone_is_touched_once_price_trades_back_into_it(self):
        got = self.find(zone_rows(extra=[(105.7, 105.8, 100.5, 101.0)]))[0]
        self.assertEqual(got["status"], "touched")
        self.assertEqual(got["touched_t"], ZSTART + 1800 * (PRE + 5))

    def test_a_dip_that_stays_above_the_zone_leaves_it_fresh(self):
        got = self.find(zone_rows(extra=[(105.7, 105.8, 101.0, 101.5)]))[0]
        self.assertEqual(got["status"], "fresh")

    def test_a_supply_zone_is_the_mirror_image(self):
        got = z.find_zones(z.flip_bars(mk(ZSTART, 1800, zone_rows())), CFG)
        self.assertEqual([g["kind"] for g in got], ["supply"])
        self.assertEqual((got[0]["low"], got[0]["high"]), (-100.8, -99.2))

    def test_the_latest_qualifying_candle_in_the_lookback_is_the_zone(self):
        got = self.find(noise(PRE - 3) + [ZONE_CANDLE, SOLID, SOLID, DISPLACEMENT] + AFTER_UP)
        self.assertEqual([(g["low"], g["high"]) for g in got], [(99.2, 100.8)])

    def test_a_candidate_six_bars_back_is_outside_the_lookback(self):
        self.assertEqual(len(self.find(noise(PRE - 6) + [ZONE_CANDLE] + [SOLID] * 5 + [DISPLACEMENT] + AFTER_UP)), 0)

    def test_big_bodied_candles_before_the_break_are_not_a_zone(self):
        self.assertEqual(len(self.find(noise(PRE - 5) + [SOLID] * 5 + [DISPLACEMENT] + AFTER_UP)), 0)

    def test_a_weak_move_away_is_not_a_zone(self):
        # a displacement body that clears 1.5 x ATR but only travels 1.85 from the zone, under 2 x ATR
        weak = (100.8, 102.65, 100.75, 102.6)
        self.assertEqual(len(self.find(noise(PRE) + [ZONE_CANDLE, weak] + AFTER_UP[:1])), 0)

    def test_a_break_must_close_beyond_the_latest_swing_high(self):
        self.assertEqual(len(self.find(swing_rows(104.4))), 1)   # 104.4 is under the 104.5 close: a break
        self.assertEqual(len(self.find(swing_rows(106.0))), 0)   # 106.0 is above it: no break

    def test_nothing_is_read_before_the_warm_up(self):
        # the same zone shape but with the break inside the first 20 bars: skipped, on purpose
        early = noise(16) + [ZONE_CANDLE, DISPLACEMENT] + AFTER_UP
        self.assertEqual(len(self.find(early)), 0)


class LimitZones(unittest.TestCase):
    NOW = et(2026, 10, 26, 12, 0)

    def zone(self, day, h, mi, di):
        return {"kind": "demand", "t": et(2026, 10, day, h, mi), "di": di, "high": 1.0, "low": 0.0}

    def test_last_two_days_only(self):
        zs = [self.zone(24, 8, 0, 1), self.zone(25, 8, 0, 2), self.zone(26, 8, 0, 3)]
        got = z.limit_zones(zs, self.NOW, CFG)
        self.assertEqual([g["di"] for g in got], [2, 3])

    def test_at_most_three_a_day_the_latest_three(self):
        zs = [self.zone(26, 7, 0, 1), self.zone(26, 7, 30, 2), self.zone(26, 8, 0, 3), self.zone(26, 8, 30, 4)]
        got = z.limit_zones(zs, self.NOW, CFG)
        self.assertEqual([g["di"] for g in got], [2, 3, 4])

    def test_zone_candles_outside_asia_london_new_york_are_dropped(self):
        zs = [self.zone(26, 11, 0, 1), self.zone(26, 8, 0, 2), self.zone(26, 3, 0, 3)]
        got = z.limit_zones(zs, self.NOW, CFG)
        self.assertEqual(sorted(g["di"] for g in got), [2, 3])  # 11:00 is in no window

    def test_sessions_can_be_switched_off(self):
        cfg = dict(CFG, zones_in_sessions=False)
        got = z.limit_zones([self.zone(26, 11, 0, 1)], self.NOW, cfg)
        self.assertEqual(len(got), 1)


class Entry(unittest.TestCase):
    def test_a_full_long_entry(self):
        m5, m3, zone, targets = entry_data()
        res, best = z.long_setups(zone, m5, m3, targets, dict(CFG, min_rr=0.5))
        self.assertEqual(best, 6)
        self.assertEqual(len(res), 1)
        r = res[0]
        self.assertEqual(r["trigger"], "FVG")
        self.assertEqual(r["sweep_low"], 98.6)
        self.assertEqual(r["sweep_t"], m5[16]["t"])
        self.assertEqual(r["gap"], (101.6, 102.4))
        self.assertAlmostEqual(r["ote"][0], 100.994)
        self.assertAlmostEqual(r["ote"][1], 102.932)
        self.assertTrue(r["ote"][0] <= sum(r["gap"]) / 2 <= r["ote"][1])
        self.assertEqual(r["entry"], 105.0)                       # the close of the CHoCH bar
        self.assertEqual(r["entry_t"], m3[43]["t"] + 180)         # known when that bar closed
        self.assertLess(r["stop"], 98.6)                          # under the sweep low
        self.assertEqual(r["target"], 110.0)                      # the swing high of the leg
        self.assertAlmostEqual(r["rr"], (110.0 - 105.0) / (105.0 - r["stop"]))

    def test_a_small_reward_to_risk_drops_the_entry_and_says_why(self):
        m5, m3, zone, targets = entry_data()
        res, best = z.long_setups(zone, m5, m3, targets, CFG)  # min_rr 2
        self.assertEqual(res, [])
        self.assertEqual(best, 5)
        self.assertIn("reward to risk", z.STAGES[best])

    def test_no_entry_when_the_choch_comes_outside_the_sessions(self):
        m5, m3, zone, targets = entry_data(et(2026, 10, 26, 12, 0))
        res, best = z.long_setups(zone, m5, m3, targets, dict(CFG, min_rr=0.5))
        self.assertEqual(res, [])
        self.assertEqual(best, 5)

    def test_no_sweep_no_entry(self):
        m5, m3, zone, targets = entry_data()
        m5[16] = dict(m5[16], l=99.5)  # the wick no longer goes under the swing low
        res, best = z.long_setups(zone, m5, m3, targets, dict(CFG, min_rr=0.5))
        self.assertEqual(res, [])
        self.assertLess(best, 3)

    def test_a_close_below_the_swing_low_is_a_breakdown_not_a_sweep(self):
        m5, m3, zone, targets = entry_data()
        m5[16] = dict(m5[16], c=99.0)  # same wick to 98.6, but it closes under the 99.15 swing low
        res, best = z.long_setups(zone, m5, m3, targets, dict(CFG, min_rr=0.5))
        self.assertEqual(res, [])
        self.assertEqual(best, 1)  # touched the zone, never swept it

    def test_a_zone_price_never_touched_gives_nothing(self):
        m5, m3, zone, targets = entry_data()
        res, best = z.long_setups(dict(zone, touched_t=None), m5, m3, targets, dict(CFG, min_rr=0.5))
        self.assertEqual((res, best), ([], 0))

    def test_the_sweep_low_breaking_first_cancels_the_choch(self):
        m5, m3, zone, targets = entry_data()
        m3[42] = dict(m3[42], l=98.0)  # a 3-minute low under the sweep low before the CHoCH
        res, _ = z.long_setups(zone, m5, m3, targets, dict(CFG, min_rr=0.5))
        self.assertEqual(res, [])

    def test_a_supply_zone_gives_the_short_side(self):
        m5, m3, zone, targets = entry_data()
        long_res, _ = z.long_setups(zone, m5, m3, targets, dict(CFG, min_rr=0.5))
        supply = dict(zone, kind="supply", low=-zone["high"], high=-zone["low"])
        res, best = z.setups_for(supply, z.flip_bars(m5), z.flip_bars(m3), [], dict(CFG, min_rr=0.5))
        self.assertEqual(best, 6)
        self.assertEqual(len(res), 1)
        r = res[0]
        self.assertEqual(r["side"], "short")
        self.assertEqual(r["entry"], -long_res[0]["entry"])
        self.assertGreater(r["stop"], r["entry"])      # a short's stop is above the entry
        self.assertLess(r["target"], r["entry"])       # and its target below
        self.assertEqual(r["gap"], (-102.4, -101.6))


class Command(unittest.TestCase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = z.main(argv)
        return code, out.getvalue(), err.getvalue()

    def folder(self, sym="MGC"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        bars = mk(ZSTART, 1800, zone_rows())
        with open(os.path.join(tmp.name, "%s_30m.json" % sym), "w") as fh:
            fh.write(chart_json(bars))
        return tmp.name

    def test_zones_reads_a_saved_chart_and_prints_the_zone(self):
        code, out, _ = self.run_cli(["zones", "MGC", "--tf", "30m", "--offline", self.folder(),
                                     "--now", "2026-10-26 12:00", "--config", "none.json"])
        self.assertEqual(code, 0)
        self.assertIn("MGC (MGC=F)", out)
        self.assertIn("DEMAND 30m", out)
        self.assertIn("99.20 to 100.80", out)
        self.assertIn("fresh", out)

    def test_the_days_window_drops_an_old_zone(self):
        code, out, _ = self.run_cli(["zones", "MGC", "--tf", "30m", "--offline", self.folder(),
                                     "--now", "2026-10-26 12:00", "--config", "none.json", "--days", "1"])
        self.assertEqual(code, 0)
        # moving "now" two days on leaves the zone outside the one-day window
        code, out, _ = self.run_cli(["zones", "MGC", "--tf", "30m", "--offline", self.folder(),
                                     "--now", "2026-10-28 12:00", "--config", "none.json", "--days", "1"])
        self.assertEqual(code, 1)
        self.assertIn("No zones", out)

    def test_json_and_write(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dest = os.path.join(tmp.name, "out", "zones.json")
        code, out, _ = self.run_cli(["zones", "MGC", "--tf", "30m", "--offline", self.folder(),
                                     "--now", "2026-10-26 12:00", "--config", "none.json", "--write", "--out", dest])
        self.assertEqual(code, 0)
        with open(dest) as fh:
            doc = json.load(fh)
        self.assertEqual(doc["symbol"], "MGC")
        self.assertEqual(doc["zones"][0]["kind"], "demand")

    def test_missing_offline_file_is_a_plain_error(self):
        code, _, err = self.run_cli(["zones", "GBPUSD", "--tf", "30m", "--offline", self.folder("MGC"),
                                     "--now", "2026-10-26 12:00", "--config", "none.json"])
        self.assertEqual(code, 2)
        self.assertIn("no offline file", err)

    def test_unknown_market_exits_2(self):
        code, _, err = self.run_cli(["zones", "TSLA"])
        self.assertEqual(code, 2)
        self.assertIn("unknown market", err)

    def test_config_overrides_one_setting_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w") as fh:
                json.dump({"zones": {"min_rr": 3, "sessions": {"ny": [8, 9]}}}, fh)
            cfg = z.read_config(path)
        self.assertEqual(cfg["min_rr"], 3)
        self.assertEqual(cfg["sessions"]["ny"], [8, 9])
        self.assertEqual(cfg["sessions"]["london"], [2, 5])
        self.assertEqual(cfg["max_per_day"], 3)

    def test_bad_config_json_is_a_plain_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w") as fh:
                fh.write("{not json")
            with self.assertRaises(z.ZoneError):
                z.read_config(path)

    def test_the_tool_never_places_an_order(self):
        with open(os.path.join(os.path.dirname(z.__file__), "zones.py"), encoding="utf-8") as fh:
            src = fh.read().lower()
        for word in ("alpaca", "api_key", "secret", "place_order", "submit_order", "os.environ"):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
