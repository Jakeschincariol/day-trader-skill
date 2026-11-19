import unittest

import _load  # noqa: F401
from india import charges, money, symbols, ticks


class Symbols(unittest.TestCase):
    def test_symbol_round_trip(self):
        s = symbols.parse("M&M")
        self.assertEqual(s, symbols.Sym("M&M", "NSE"))
        self.assertEqual(symbols.yahoo_path_part(s), "M%26M.NS")
        self.assertEqual(symbols.parse("NSE:BAJAJ-AUTO"), symbols.Sym("BAJAJ-AUTO", "NSE"))
        self.assertEqual(symbols.to_yahoo(symbols.parse("RELIANCE.BO")), "RELIANCE.BO")
        self.assertEqual(symbols.safe_filename(s), "M_and_M.NS")
        with self.assertRaises(ValueError):
            symbols.parse("TCS 2")
        with self.assertRaises(ValueError):
            symbols.parse("NIFTY24DECFUT.NFO")

    def test_forms_and_case(self):
        for text in ("tcs", "TCS.NS", "NSE:TCS", " tcs "):
            self.assertEqual(symbols.parse(text), symbols.Sym("TCS", "NSE"), text)
        self.assertEqual(symbols.parse("BSE:RELIANCE"), symbols.Sym("RELIANCE", "BSE"))
        self.assertEqual(symbols.parse("INFY", default_exchange="BSE").exchange, "BSE")
        self.assertEqual(symbols.display(symbols.parse("RELIANCE.BO")), "RELIANCE (BSE)")
        self.assertEqual(symbols.display(symbols.parse("M&M")), "M&M")


class Ticks(unittest.TestCase):
    def test_tick_rounding(self):
        self.assertEqual(ticks.round_down(249.987), 249.98)       # < 250: 0.01
        self.assertEqual(ticks.round_down(358.32), 358.30)        # 250-1000: 0.05
        self.assertEqual(ticks.round_up(358.32), 358.35)
        self.assertEqual(ticks.round_down(3296.17), 3296.10)      # 1000-5000: 0.10
        self.assertEqual(ticks.round_up(7001.2), 7001.50)         # 5000-10000: 0.50
        self.assertTrue(ticks.is_valid(3296.10))
        self.assertFalse(ticks.is_valid(3296.15))

    def test_float_noise_and_nearest(self):
        self.assertEqual(ticks.round_down(0.1 + 0.2 + 300), 300.30)   # 300.30000000000001
        self.assertEqual(ticks.round_up(300.30), 300.30)
        self.assertEqual(ticks.round_nearest(3645.04), 3645.00)
        self.assertEqual(ticks.round_nearest(3645.06), 3645.10)
        self.assertEqual(ticks.tick_paise(25000), 500)

    def test_custom_schedule(self):
        flat = [(None, 5)]
        self.assertEqual(ticks.round_down(100.04, flat), 100.00)


class Money(unittest.TestCase):
    def test_inr_grouping(self):
        self.assertEqual(money.inr(123456.785), "₹1,23,456.79")
        self.assertEqual(money.inr(-697.8), "-₹697.80")
        self.assertEqual(money.inr(1500, 0), "₹1,500")
        self.assertEqual(money.inr(12345678.9), "₹1,23,45,678.90")
        self.assertEqual(money.inr(999), "₹999.00")
        self.assertEqual(money.crore(5e7), "₹5.00 cr")
        self.assertEqual(money.crore(27698100000), "₹2,769.81 cr")
        self.assertEqual(money.lakh(250000), "₹2.50 lakh")


class Charges(unittest.TestCase):
    def test_delivery_charges(self):
        c = charges.delivery_round_trip(100000.0, 110000.0)
        self.assertEqual(c["stt"], 210.0)
        self.assertEqual(c["stamp"], 15.0)
        self.assertEqual(c["dp"], 15.93)
        self.assertAlmostEqual(c["exchange"], 6.24, places=2)
        self.assertAlmostEqual(c["total"], c["brokerage"] + c["stt"] + c["exchange"] + c["sebi"]
                               + c["stamp"] + c["gst"] + c["dp"], places=2)

    def test_brokerage_override(self):
        c = charges.delivery_round_trip(10000.0, 10000.0, {"brokerage_per_order": 20.0})
        self.assertEqual(c["brokerage"], 40.0)
        self.assertEqual(c["stt"], 20.0)       # unspecified keys keep defaults


if __name__ == "__main__":
    unittest.main()
