import datetime
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from _load import FIX, load

ptr = load("trader-pelosi", "ptr")
DIR = os.path.join(FIX, "trader-pelosi")
ZIP = os.path.join(DIR, "2026FD.zip")


def text(name):
    with open(os.path.join(DIR, name), encoding="utf-8") as fh:
        return fh.read()


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ptr.main(args)
    return code, out.getvalue(), err.getvalue()


class Index(unittest.TestCase):
    def setUp(self):
        self.rows = ptr.load_index(2026, offline=ZIP)

    def test_finds_her_four_2026_ptrs(self):
        hers = ptr.select(self.rows, ["pelosi"])
        self.assertEqual([r["doc_id"] for r in hers],
                         ["20035553", "20035143", "20034836", "20033725"])
        self.assertEqual([r["filed"] for r in hers],
                         ["2026-10-02", "2026-08-21", "2026-06-23", "2026-01-23"])
        self.assertEqual(hers[1]["url"],
                         "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20035143.pdf")
        self.assertEqual(hers[0]["district"], "CA11")
        self.assertEqual(hers[0]["name"], "Hon. Nancy Pelosi")

    def test_member_names_in_any_order(self):
        for m in ("pelosi", "Nancy Pelosi", "Pelosi, Nancy", "PELOSI"):
            self.assertEqual(len(ptr.select(self.rows, [m])), 4, m)
        self.assertEqual(ptr.select(self.rows, ["Paul Pelosi"]), [])
        both = ptr.select(self.rows, ["pelosi", "gottheimer"])
        self.assertEqual(len(both), 5)

    def test_only_ptrs_unless_asked(self):
        ptrs = ptr.select(self.rows)
        self.assertTrue(all(r["type"] == "P" for r in ptrs))
        everything = ptr.select(self.rows, kind=None)
        self.assertGreater(len(everything), len(ptrs))
        other = next(r for r in everything if r["type"] == "C")
        self.assertIn("/financial-pdfs/2026/", other["url"])

    def test_since_and_newest_first(self):
        recent = ptr.select(self.rows, since="2026-10-07")
        self.assertEqual({r["filed"] for r in recent} <= {"2026-10-07", "2026-10-12"}, True)
        self.assertEqual(recent[0]["filed"], "2026-10-12")
        self.assertIn("Salazar", [r["last"] for r in recent])

    def test_reads_the_xml_inside_or_alone(self):
        import zipfile
        with zipfile.ZipFile(ZIP) as z:
            raw = z.read("2026FD.xml")
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))  # the Clerk's file has a BOM
        self.assertEqual(len(ptr.parse_index(ptr.read_index_bytes(raw), 2026)), len(self.rows))
        with self.assertRaises(ptr.PtrError):
            ptr.parse_index(b"not xml", 2026)


BAD_INDEX = """<?xml version="1.0" encoding="utf-8"?>
<FinancialDisclosure>
  <Member><Prefix>Hon.</Prefix><Last>Pelosi</Last><First>Nancy</First><Suffix /><FilingType>P</FilingType>
    <StateDst>CA11</StateDst><Year>2026</Year><FilingDate>10/2/2026</FilingDate><DocID>20035553</DocID></Member>
  <Member><Prefix>Hon.</Prefix><Last>Evil</Last><First>Path</First><Suffix /><FilingType>P</FilingType>
    <StateDst>XX00</StateDst><Year>2026</Year><FilingDate>10/3/2026</FilingDate><DocID>../evil</DocID></Member>
  <Member><Prefix>Hon.</Prefix><Last>Evil</Last><First>Drive</First><Suffix /><FilingType>P</FilingType>
    <StateDst>XX00</StateDst><Year>2026</Year><FilingDate>10/4/2026</FilingDate>
    <DocID>C:\\Windows\\System32\\evil</DocID></Member>
  <Member><Prefix>Hon.</Prefix><Last>Evil</Last><First>Url</First><Suffix /><FilingType>P</FilingType>
    <StateDst>XX00</StateDst><Year>2026</Year><FilingDate>10/5/2026</FilingDate>
    <DocID>https://example.com/x.pdf</DocID></Member>
  <Member><Prefix>Hon.</Prefix><Last>Evil</Last><First>Short</First><Suffix /><FilingType>P</FilingType>
    <StateDst>XX00</StateDst><Year>2026</Year><FilingDate>10/6/2026</FilingDate><DocID>123</DocID></Member>
</FinancialDisclosure>
"""


class BadDocIds(unittest.TestCase):
    def setUp(self):
        self._download = ptr.download

        def never(url, timeout=60):
            raise AssertionError("the network was touched for %s" % url)
        ptr.download = never

    def tearDown(self):
        ptr.download = self._download

    def test_the_index_skips_them_and_says_so(self):
        skipped = []
        rows = ptr.parse_index(BAD_INDEX.encode("utf-8"), 2026, skipped)
        self.assertEqual([r["doc_id"] for r in rows], ["20035553"])
        self.assertEqual(len(skipped), 4)
        self.assertEqual(ptr.parse_index(BAD_INDEX.encode("utf-8"), 2026), rows)   # the list is optional
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2026FD.xml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(BAD_INDEX)
            code, out, err = run(["index", "--offline", path, "--year", "2026"])
            self.assertEqual(code, 0)
            self.assertIn("doc 20035553", out)
            self.assertNotIn("evil", out)
            self.assertEqual(err.count("skipped 4 index row(s)"), 1)

    def test_fetch_refuses_them_before_any_url_or_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_dir = os.path.join(tmp, "pdfs")
            for bad in ("../evil", "C:\\Windows\\System32\\evil", "123", "2003555x", "", "20035553.pdf"):
                with self.assertRaises(ptr.PtrError, msg=bad):
                    ptr._fetch_and_read(bad, 2026, pdf_dir)
                code, _, err = run(["fetch", bad, "--pdf-dir", pdf_dir])
                self.assertEqual(code, 2, bad)
                self.assertIn("not a Clerk DocID", err)
            self.assertFalse(os.path.exists(pdf_dir))                   # nothing was created
        self.assertEqual(ptr.check_doc_id("20035553"), "20035553")

    def test_a_junk_year_is_a_plain_error(self):
        xml = BAD_INDEX.replace("<Year>2026</Year><FilingDate>10/2/2026", "<Year>twenty</Year><FilingDate>10/2/2026")
        with self.assertRaises(ptr.PtrError) as cm:
            ptr.parse_index(xml.encode("utf-8"), 2026)
        self.assertIn("Year", str(cm.exception))


class Download(unittest.TestCase):
    def test_a_response_over_the_cap_is_refused(self):
        import urllib.request

        class Resp(object):
            def __init__(self, n):
                self.n = n

            def read(self, limit=-1):
                return b"x" * (self.n if limit < 0 else min(self.n, limit))

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        saved = urllib.request.urlopen
        try:
            urllib.request.urlopen = lambda req, timeout=60: Resp(ptr.MAX_DOWNLOAD + 1)
            with self.assertRaises(ptr.PtrError) as cm:
                ptr.download("https://example.com/big.zip")
            self.assertIn("over 50 MB", str(cm.exception))
            urllib.request.urlopen = lambda req, timeout=60: Resp(ptr.MAX_DOWNLOAD)
            self.assertEqual(len(ptr.download("https://example.com/ok.zip")), ptr.MAX_DOWNLOAD)
        finally:
            urllib.request.urlopen = saved

    def test_an_unexpected_error_is_one_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2026FD.zip")
            with open(path, "wb") as fh:
                fh.write(b"PK\x03\x04 this is not a zip")
            code, _, err = run(["index", "--offline", path])
            self.assertEqual(code, 1)
            self.assertIn("ptr: unexpected BadZipFile", err)
            self.assertNotIn("Traceback", err)


class NewSinceLastCheck(unittest.TestCase):
    def test_alerts_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "state", "pelosi.json")
            base = ["new", "--member", "pelosi", "--offline", ZIP, "--year", "2026",
                    "--state", state, "--portfolio", os.path.join(tmp, "none.json")]
            code, out, _ = run(base + ["--today", "2026-10-13"])
            self.assertEqual(code, 0)
            # first run: the last 45 days only
            self.assertIn("doc 20035553", out)
            self.assertNotIn("doc 20035143", out)
            with open(state) as fh:
                saved = json.load(fh)
            self.assertEqual(saved["seen"], ["20033725", "20034836", "20035143", "20035553"])
            code, out, _ = run(base + ["--today", "2026-10-13"])
            self.assertEqual(code, 1)
            self.assertIn("Nothing new", out)

    def test_a_new_doc_id_is_new(self):
        rows = ptr.select(ptr.load_index(2026, offline=ZIP), ["pelosi"])
        state = {"seen": ["20033725", "20034836", "20035553"], "last_check": "2026-08-01T09:00:00"}
        fresh = ptr.new_since(rows, state, datetime.date(2026, 10, 13))
        self.assertEqual([r["doc_id"] for r in fresh], ["20035143"])

    def test_dry_run_keeps_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "pelosi.json")
            run(["new", "--offline", ZIP, "--state", state, "--today", "2026-10-13",
                 "--dry-run", "--portfolio", os.path.join(tmp, "none.json")])
            self.assertFalse(os.path.exists(state))


class ParseReport(unittest.TestCase):
    def test_the_reel_alert_bloom_energy_calls(self):
        rep = ptr.parse_ptr_text(text("ptr-20035143.txt"))
        self.assertEqual(rep["name"], "Hon. Nancy Pelosi")
        self.assertEqual(rep["status"], "Member")
        self.assertEqual(rep["district"], "CA11")
        self.assertEqual(rep["doc_id"], "20035143")
        self.assertEqual(rep["filed"], "2026-08-21")
        self.assertEqual(len(rep["rows"]), 7)
        calls = [r for r in rep["rows"] if r["ticker"] == "BE" and r["asset_type"] == "OP"]
        self.assertEqual(len(calls), 2)
        big = calls[0]
        self.assertEqual(big["owner"], "SP")
        self.assertEqual(big["owner_name"], "spouse")
        self.assertEqual(big["type"], "P")
        self.assertEqual(big["date"], "2026-07-24")
        self.assertEqual(big["notified"], "2026-07-24")
        self.assertEqual(big["amount"], "$1,000,001 - $5,000,000")
        self.assertEqual((big["amount_low"], big["amount_high"]), (1000001, 5000000))
        self.assertEqual(big["option"], {"contracts": 100, "kind": "call", "strike": 100.0,
                                         "expires": "2027-06-17", "exercised": False})
        self.assertEqual(big["days_to_disclose"], 28)
        self.assertFalse(big["late"])
        self.assertEqual(big["asset"], "Bloom Energy Corporation Class A Common Stock")
        shares = [r for r in rep["rows"] if r["ticker"] == "BE" and r["asset_type"] == "ST"]
        self.assertEqual([r["shares"] for r in shares], [10000, 5000])
        llc = rep["rows"][-1]
        self.assertIsNone(llc["ticker"])
        self.assertEqual(llc["asset_type"], "AB")
        self.assertIn("luxury hotel", llc["description"])

    def test_render_says_public_and_flags_your_stocks(self):
        rep = ptr.parse_ptr_text(text("ptr-20035143.txt"))
        out = ptr.render_report(rep, watch={"INTC"})
        self.assertIn("100 call options, $100 strike, expires 2027-06-17", out)
        self.assertIn("INTC is on your list", out)
        self.assertIn("Not inside information", out)
        self.assertIn("45 days", out)
        self.assertNotIn(chr(0x2014), out)

    def test_joint_owner_and_account(self):
        rep = ptr.parse_ptr_text(text("ptr-20035590.txt"))
        self.assertEqual([(r["ticker"], r["owner"], r["type"]) for r in rep["rows"]],
                         [("AMAT", "JT", "S"), ("MCD", "JT", "S (partial)")])
        self.assertEqual(rep["rows"][0]["account"], "Morgan Stanley - Select UMA Account # 1")
        self.assertEqual(rep["rows"][0]["notified"], "2026-10-06")

    def test_self_owned_partial_sales_and_crowded_columns(self):
        rep = ptr.parse_ptr_text(text("ptr-20035562-excerpt.txt"))
        tickers = [r["ticker"] for r in rep["rows"]]
        self.assertEqual(tickers, ["BRK.B", "BIIB", "BA", "BEP", "CVX", "CB", "GLW", "IBM"])
        self.assertTrue(all(r["owner"] == "" and r["owner_name"] == "self" for r in rep["rows"]))
        brk = rep["rows"][0]
        self.assertEqual(brk["type_name"], "partial sale")
        self.assertEqual(brk["account"], "UBS IRA Account")
        # "Corning Incorporated Common Stock P" : the type touches the asset text
        glw = rep["rows"][6]
        self.assertEqual((glw["type"], glw["asset"]), ("P", "Corning Incorporated Common Stock"))
        # the asset name runs over three lines
        self.assertEqual(rep["rows"][7]["asset"],
                         "International Business Machines Corporation Common Stock")

    def test_page_breaks_exercises_and_exchanges(self):
        rep = ptr.parse_ptr_text(text("ptr-20033725-excerpt.txt"))
        by = {r["ticker"]: r for r in rep["rows"]}
        self.assertEqual(sorted(by), ["NVDA", "PYPL", "TEM", "VSNT", "VST"])
        tem = by["TEM"]  # the row is split by a page header
        self.assertEqual(tem["asset"], "Tempus AI, Inc. - Class A Common Stock")
        self.assertEqual(tem["amount"], "$50,001 - $100,000")
        self.assertTrue(tem["option"]["exercised"])
        self.assertEqual(tem["option"]["strike"], 20.0)
        self.assertEqual(by["PYPL"]["date"], "2025-12-30")
        self.assertEqual(by["PYPL"]["shares"], 5000)
        self.assertEqual(by["VSNT"]["type_name"], "exchange")

    def test_late_filings_are_flagged(self):
        rep = ptr.parse_ptr_text(text("ptr-20035590.txt"), filed="2026-11-15")
        self.assertTrue(all(r["late"] for r in rep["rows"]))

    def test_parse_cli(self):
        path = os.path.join(DIR, "ptr-20035143.txt")
        code, out, _ = run(["parse", path, "--tickers", "BE", "--portfolio", "/nonexistent"])
        self.assertEqual(code, 0)
        self.assertIn("PTR 20035143, filed 2026-08-21", out)
        code, out, _ = run(["parse", path, "--json"])
        self.assertEqual(len(json.loads(out)["rows"]), 7)

    def test_dates(self):
        self.assertEqual(ptr.iso("8/21/2026"), "2026-08-21")
        self.assertEqual(ptr.iso("6/17/27"), "2027-06-17")
        self.assertIsNone(ptr.iso("13/45/2026"))


if __name__ == "__main__":
    unittest.main()
