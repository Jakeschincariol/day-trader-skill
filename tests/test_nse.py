import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
import urllib.error

from _load import FIX, load

nse = load("trader-scanner", "nse")


class NSEData(unittest.TestCase):
    def setUp(self):
        self.fix = os.path.join(FIX, "trader-india")

    def test_symbol_name_supports_nse_and_bse_suffixes(self):
        self.assertEqual(nse.symbol_name("RELIANCE.NS"), "RELIANCE")
        self.assertEqual(nse.symbol_name("TCS.BO"), "TCS")

    def test_offline_quote_is_inr(self):
        path = os.path.join(self.fix, "nse-quote-RELIANCE.json")
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        result = nse.quote("RELIANCE.NS", offline_doc=doc)
        self.assertEqual(result["symbol"], "RELIANCE")
        self.assertEqual(result["exchange"], "NSE")
        self.assertEqual(result["currency"], "INR")
        self.assertEqual(result["last"], 2850.25)
        self.assertEqual(result["day_high"], 2875.5)

    def test_option_chain_tracks_call_put_oi_and_pcr(self):
        path = os.path.join(self.fix, "nse-option-RELIANCE.json")
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        result = nse.oi_summary("RELIANCE.NS", expiry="26-NOV-2026", offline_doc=doc)
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["call_oi"], 270000)
        self.assertEqual(result["put_oi"], 380000)
        self.assertEqual(result["put_call_oi"], 1.4074)
        self.assertEqual(result["rows"][0]["call"]["oi"], 120000)
        self.assertEqual(result["rows"][0]["put"]["change_oi"], 12000)

    def test_option_chain_rejects_unknown_expiry(self):
        path = os.path.join(self.fix, "nse-option-RELIANCE.json")
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        with self.assertRaises(nse.NSEError):
            nse.option_chain("RELIANCE.NS", expiry="99-JAN-2099", offline_doc=doc)

    def test_quote_cli_json(self):
        path = os.path.join(self.fix, "nse-quote-RELIANCE.json")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = nse.main(["quote", "RELIANCE.NS", "--offline", path, "--json"])
        self.assertEqual(code, 0, err.getvalue())
        data = json.loads(out.getvalue())
        self.assertEqual(data["currency"], "INR")

    def test_oi_cli_plain_text(self):
        path = os.path.join(self.fix, "nse-option-RELIANCE.json")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = nse.main(["oi", "RELIANCE.NS", "--offline", path,
                             "--expiry", "26-NOV-2026"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("call OI", out.getvalue())
        self.assertIn("put OI", out.getvalue())


if __name__ == "__main__":
    unittest.main()
