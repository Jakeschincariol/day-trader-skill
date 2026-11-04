"""Offline tests for the web dashboard (dashboard/server.py)."""

import http.client
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error

from _load import ROOT, load

srv = load("dashboard", "server")


def fake_bars(closes, vol=1000000):
    bars = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        bars.append({"t": 1700000000 + i * 86400, "o": o, "h": max(o, c) * 1.005, "l": min(o, c) * 0.995, "c": c, "v": vol})
    return {"meta": {"symbol": "TEST", "name": "Test Co", "currency": "USD", "exchange": "X", "type": "EQUITY"}, "bars": bars}


class Indicators(unittest.TestCase):
    def test_sma(self):
        self.assertEqual(srv.sma([1, 2, 3, 4, 5], 3), [None, None, 2.0, 3.0, 4.0])

    def test_ema_seeds_with_sma(self):
        out = srv.ema([1, 2, 3, 4], 3)
        self.assertEqual(out[2], 2.0)
        self.assertAlmostEqual(out[3], 3.0)

    def test_rsi_extremes(self):
        self.assertEqual(srv.rsi(list(range(1, 40)))[-1], 100.0)
        self.assertLess(srv.rsi(list(range(40, 1, -1)))[-1], 1)

    def test_atr_constant_range(self):
        self.assertAlmostEqual(srv.atr([11] * 30, [9] * 30, [10] * 30)[-1], 2.0)


class Rating(unittest.TestCase):
    def setUp(self):
        self._get = srv.get_bars
        self._spy = srv.spy_return_63
        self._earn, self._reg = srv.next_earnings, srv.market_regime
        srv.next_earnings = lambda s, wait=True: None
        srv.market_regime = lambda: {"level": "green", "label": "ok", "notes": []}

    def tearDown(self):
        srv.get_bars = self._get
        srv.spy_return_63 = self._spy
        srv.next_earnings, srv.market_regime = self._earn, self._reg

    def run_on(self, closes, spy=0.0):
        srv.get_bars = lambda s, rng="2y": fake_bars(closes)
        srv.spy_return_63 = lambda: spy
        return srv.analyse("TEST", with_series=True)

    def test_steady_uptrend_rates_buy(self):
        a = self.run_on([100 * 1.004 ** i + (i % 3) for i in range(300)])
        self.assertIn(a["rating"], ("Buy", "Strong Buy"))
        self.assertGreater(a["score"], 55)
        self.assertNotEqual(a["entryStatus"], "Avoid")

    def test_downtrend_is_avoid_with_no_plan(self):
        a = self.run_on([300 * 0.996 ** i for i in range(300)])
        self.assertIn(a["rating"], ("Sell", "Strong Sell"))
        self.assertEqual(a["entryStatus"], "Avoid")
        self.assertIsNone(a["plan"])

    def test_plan_has_stop_below_entry_and_2r_target(self):
        closes = [100 * 1.003 ** i for i in range(290)] + [100 * 1.003 ** 289 * 0.97] * 10
        a = self.run_on(closes)
        p = a["plan"]
        if p:
            self.assertLess(p["stop"], p["entry"])
            self.assertAlmostEqual(p["target1"] - p["entry"], 2 * (p["entry"] - p["stop"]), delta=0.05)

    def test_series_lengths_match(self):
        a = self.run_on([100 + i * 0.1 for i in range(260)])
        n = len(a["series"]["c"])
        for k, v in a["series"].items():
            self.assertEqual(len(v), n, k)


class Trading212(unittest.TestCase):
    def test_ticker_mapping(self):
        self.assertEqual(srv.t212_to_yahoo("AAPL_US_EQ"), "AAPL")
        self.assertEqual(srv.t212_to_yahoo("BRK.B_US_EQ"), "BRK-B")
        self.assertEqual(srv.t212_to_yahoo("VUSAl_EQ"), "VUSA.L")
        self.assertEqual(srv.t212_to_yahoo("SAPd_EQ"), "SAP.DE")

    def test_portfolio_normalises_v0_fields(self):
        fake = {
            "/equity/account/info": {"currencyCode": "GBP"},
            "/equity/account/cash": {"free": 10, "total": 110, "ppl": 5, "result": 1, "invested": 95},
            "/equity/portfolio": [{"ticker": "VUSAl_EQ", "quantity": 2, "averagePrice": 90, "currentPrice": 100, "ppl": 20}],
        }

        def get(path):
            if path in fake:
                return fake[path]
            raise urllib.error.HTTPError(path, 404, "nf", {}, None)
        old = srv.t212_get
        srv.t212_get = get
        srv.T212.update(key="k-test", secret="s", env="demo")
        try:
            out = srv.t212_portfolio()
        finally:
            srv.t212_get = old
            srv.T212.update(key=None, secret=None)
        self.assertEqual(out["currency"], "GBP")
        self.assertEqual(out["cash"]["total"], 110)
        self.assertEqual(out["positions"][0]["symbol"], "VUSA.L")
        self.assertEqual(out["positions"][0]["qty"], 2)

    def test_trading212_is_read_only(self):
        # every Trading 212 call goes through t212_get, which only ever sends GET requests
        import re
        with open(os.path.join(ROOT, "dashboard", "server.py")) as fh:
            src = fh.read()
        # the assistant's two POSTs go to the Anthropic API and to Ollama on this computer, never to Trading 212
        for fn in ("_claude", "ai_chat_ollama"):
            body = re.search(r"\ndef %s\(.*?(?=\ndef )" % fn, src, re.S).group(0)
            self.assertNotIn("trading212", body.lower())
            self.assertNotIn("t212", body.lower())
            src = src.replace(body, "")
        for bad in ("/equity/orders/limit", "/equity/orders/market", "/equity/orders/stop", "method=\"POST\"",
                    "method=\"DELETE\"", "urlopen(req, data", "data=json"):
            self.assertNotIn(bad, src)
        seen = []
        old = srv.http_get
        srv.http_get = lambda url, headers=None, timeout=20: seen.append(url) or {}
        srv.T212.update(key="k", secret="s", env="demo")
        try:
            srv.t212_get("/equity/orders")
        finally:
            srv.http_get = old
            srv.T212.update(key=None, secret=None)
        self.assertEqual(seen, ["https://demo.trading212.com/api/v0/equity/orders"])

    def test_keys_file_is_git_ignored(self):
        with open(os.path.join(ROOT, ".gitignore")) as fh:
            text = fh.read()
        for secret in ("dashboard/.t212.json", "dashboard/.access.json", "dashboard/.logo-cache/"):
            self.assertIn(secret, text)


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = srv.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        cls.httpd.allow_any_host = False
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def req(self, method, path, headers=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        return r.status, r.read()

    def test_serves_app(self):
        status, body = self.req("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Trader", body)

    def test_blocks_foreign_host_and_origin(self):
        self.assertEqual(self.req("GET", "/api/t212/status", {"Host": "evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/api/t212/disconnect",
                                  {"Origin": "https://evil.example", "Content-Type": "application/json"}, "{}")[0], 403)

    def test_post_needs_json(self):
        self.assertEqual(self.req("POST", "/api/t212/connect", {"Content-Type": "text/plain"}, "x")[0], 415)

    def test_status_never_returns_the_key(self):
        srv.T212.update(key="SECRET-KEY-123", secret="SECRET-456")
        try:
            status, body = self.req("GET", "/api/t212/status")
        finally:
            srv.T212.update(key=None, secret=None)
        self.assertEqual(json.loads(body)["linked"], True)
        self.assertNotIn(b"SECRET", body)

    def test_static_path_traversal_falls_back(self):
        status, body = self.req("GET", "/../server.py")
        self.assertNotIn(b"def main", body)


class Fundamentals(unittest.TestCase):
    def test_money_num(self):
        self.assertEqual(srv.money_num("$109,417,000"), 109417000.0)
        self.assertEqual(srv.money_num("-$4,508,000"), -4508000.0)
        self.assertEqual(srv.money_num("$143,756(m)"), 143756e6)
        self.assertIsNone(srv.money_num("--"))

    def test_fiscal_quarters_and_yoy(self):
        data = {"revenueTable": {"headers": {"value1": "Fiscal Quarter:", "value2": "2026 (Fiscal Year)", "value3": "2025 (Fiscal Year)"},
                "rows": [{"value1": "December", "value2": "", "value3": ""},
                         {"value1": "Revenue", "value2": "$120(m)", "value3": "$100(m)"},
                         {"value1": "EPS", "value2": "$2.20 (12/27/2025)", "value3": "$2.00 (12/28/2024)"},
                         {"value1": "March", "value2": "", "value3": ""},
                         {"value1": "Revenue", "value2": "", "value3": "$90(m)"},
                         {"value1": "EPS", "value2": "", "value3": "$1.50 (03/29/2025)"}]}}
        q = srv._fiscal_quarters(data)
        self.assertEqual([x["label"] for x in q], ["Q1 FY25", "Q2 FY25", "Q1 FY26"])
        self.assertEqual(q[-1]["epsYoY"], 10.0)
        self.assertEqual(q[-1]["revYoY"], 20.0)

    def test_non_us_symbols_skip_nasdaq(self):
        self.assertFalse(srv.fundamentals("VUSA.L")["available"])


class Forecast(unittest.TestCase):
    def test_bands_are_ordered_and_widen(self):
        f = srv.forecast([100 * 1.001 ** i * (1 + 0.01 * ((i % 5) - 2)) for i in range(200)])
        for k in range(f["days"]):
            self.assertLess(f["lo2"][k], f["lo1"][k])
            self.assertLess(f["lo1"][k], f["mid"][k])
            self.assertLess(f["mid"][k], f["hi1"][k])
            self.assertLess(f["hi1"][k], f["hi2"][k])
        self.assertGreater(f["hi1"][-1] - f["lo1"][-1], f["hi1"][0] - f["lo1"][0])


class PortfolioHistory(unittest.TestCase):
    def setUp(self):
        self._dc = srv._daily_closes
        days = ["2026-01-%02d" % d for d in range(2, 31)]
        self.days = days

        def fake(sym, start):
            if sym == "AAA":
                return {d: 10.0 + i for i, d in enumerate(days)}, "USD"
            raise ValueError("no fx needed")
        srv._daily_closes = fake

    def tearDown(self):
        srv._daily_closes = self._dc

    def ts(self, d):
        import calendar, time
        return calendar.timegm(time.strptime(d, "%Y-%m-%d"))

    def test_buy_then_sell_tracks_invested_value_and_realized(self):
        lots = [{"symbol": "AAA", "ts": self.ts("2026-01-02"), "qty": 10, "price": 10.0},
                {"symbol": "AAA", "ts": self.ts("2026-01-12"), "qty": -5, "price": 20.0}]
        h = srv.portfolio_history(lots, "USD")
        self.assertEqual(h["invested"][0], 100.0)
        self.assertEqual(h["invested"][-1], 50.0)  # cost of the 5 shares still held
        self.assertEqual(h["realized"][-1], 50.0)  # sold 5 at 20 that cost 10
        self.assertEqual(h["value"][-1], 5 * (10.0 + len(self.days) - 1))
        # all-time gain = value now + cash received from the sale - cash spent
        self.assertAlmostEqual(h["returns"]["Max"]["gain"], h["value"][-1] + 5 * 20.0 - 10 * 10.0, 2)

    def test_pence_fix(self):
        lots = [{"symbol": "AAA", "ts": self.ts("2026-01-02"), "qty": 1, "price": 1000.0}]
        h = srv.portfolio_history(lots, "USD")
        self.assertEqual(h["invested"][0], 10.0)


class Refresh(unittest.TestCase):
    def test_purge_symbols(self):
        srv._cache[("bars", "AAPL", "2y")] = (0, 1)
        srv._cache[("bars", "MSFT", "2y")] = (0, 1)
        srv._cache[("nasdaq", "quote/AAPL/summary?assetclass=stocks")] = (0, 1)
        srv.purge_symbols(["AAPL"])
        self.assertNotIn(("bars", "AAPL", "2y"), srv._cache)
        self.assertNotIn(("nasdaq", "quote/AAPL/summary?assetclass=stocks"), srv._cache)
        self.assertIn(("bars", "MSFT", "2y"), srv._cache)


class Radar(unittest.TestCase):
    def test_features_on_a_steady_uptrend(self):
        c = [100 * 1.003 ** i for i in range(300)]
        f = srv._features(c, [1e6] * 300, 299, lambda i, back: 0.0)
        self.assertGreater(f["r12"], 0.5)
        self.assertAlmostEqual(f["fromHigh"], 0.0, places=6)
        self.assertGreater(f["d200"], 0)
        self.assertAlmostEqual(f["volr"], 0.0)
        self.assertIsNone(srv._features(c, [1] * 300, 100, lambda i, back: 0.0))

    def test_launch_is_start_of_the_best_confirmed_run(self):
        flat = [100.0 + (i % 3) for i in range(300)]
        run = [101.0 * 1.01 ** k for k in range(1, 260)]
        c = flat + run
        t = [1600000000 + i * 86400 for i in range(len(c))]
        L = srv._launch(t, c, [1e6] * len(c), lambda ts, back: 0.0)
        self.assertIsNotNone(L)
        self.assertGreater(L["peak12"], 200)
        self.assertEqual(L["path"][0], 1.0)

    def test_growth_needs_three_data_points(self):
        g, why = srv._growth({"available": True, "earnings": [], "analyst": {"upside": 50}})
        self.assertIsNone(g)
        fa = {"available": True, "earnings": [{"revYoY": 20, "epsYoY": 30}, {"revYoY": 40, "epsYoY": 75}],
              "highlights": {"operatingMargin": 30, "epsTTM": 4}, "forecasts": [{"eps": 1.5}] * 4, "analyst": {"upside": 30}}
        g, why = srv._growth(fa)
        self.assertTrue(0 < g <= 100)
        self.assertTrue(any("accelerating" in w[0] for w in why))


class Vendor(unittest.TestCase):
    def test_every_local_script_and_font_exists(self):
        import re
        static = os.path.join(ROOT, "dashboard", "static")
        with open(os.path.join(static, "index.html")) as fh:
            html = fh.read()
        with open(os.path.join(static, "style.css")) as fh:
            css = fh.read()
        refs = re.findall(r'src="/([^"]+)"', html) + re.findall(r'url\("/([^"]+)"\)', css)
        self.assertTrue(any("lightweight-charts" in x for x in refs))
        for ref in refs:
            self.assertTrue(os.path.isfile(os.path.join(static, ref)), ref)

    def test_licenses_ship_with_the_libraries(self):
        with open(os.path.join(ROOT, "dashboard", "static", "vendor", "THIRD_PARTY_LICENSES.txt")) as fh:
            text = fh.read()
        for name in ("Lightweight Charts", "ECharts", "CountUp", "Lucide", "Inter", "JetBrains Mono"):
            self.assertIn(name, text)


REV_CSV = """Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate
2024-01-05T14:32:11.123Z,,CASH TOP-UP,,,EUR 2000,EUR,1.0
2024-01-06T15:00:00.000Z,NVDA,BUY - MARKET,5,USD 48.00,USD 240.00,USD,1.09
2024-03-01T15:00:00.000Z,AMD,BUY - MARKET,3,USD 200.00,USD 600.00,USD,1.08
2024-06-01T15:00:00Z,AMD,SELL - MARKET,1,USD 160.00,USD 160.00,USD,1.08
2024-06-10T08:00:00Z,NVDA,STOCK SPLIT,45,,,USD,1.07
2024-07-01T15:00:00Z,NVDA,DIVIDEND,,,USD 0.05,USD,1.07
2025-02-02T10:00:00Z,BRK.B,BUY - LIMIT,"0,5","$480.10","$240.05",USD,1.04
2025-02-02T10:00:00Z,,CUSTODY FEE,,,USD -1.00,USD,1.04
2025-03-01T10:00:00Z,XYZ,SOMETHING NEW,1,1,1,USD,1
"""


class Revolut(unittest.TestCase):
    def rows(self, text=REV_CSV):
        import csv
        import io
        return list(csv.reader(io.StringIO(text)))

    def test_numbers_in_every_format(self):
        for raw, want in [("USD 1,234.50", 1234.5), ("$1,234.50", 1234.5), ("-€12.30", -12.3), ("1.234,50 €", 1234.5),
                          ("0,5", 0.5), ("USD -1.00", -1.0), ("(5.00)", -5.0), ("", None), ("12", 12.0)]:
            self.assertEqual(srv.num_text(raw), want, raw)

    def test_dates(self):
        self.assertEqual(srv._rev_date("2024-01-05T00:00:00Z"), 1704412800)
        self.assertEqual(srv._rev_date("05/01/2024"), 1704412800)
        self.assertEqual(srv._rev_date("2024-01-05 00:00:00"), 1704412800)
        self.assertEqual(srv._rev_date("45296"), 1704412800)  # Excel date number

    def test_statement_to_positions(self):
        out = srv.parse_revolut(self.rows())
        self.assertEqual(out["skipped"], 1)
        self.assertIn("SOMETHING NEW", out["otherTypes"])
        book = srv._rev_book(out["trades"])
        self.assertAlmostEqual(book["NVDA"]["qty"], 50)  # 5 shares, then a 10-for-1 split
        self.assertAlmostEqual(book["NVDA"]["cost"], 240)  # a split doesn't change what you paid
        self.assertAlmostEqual(book["AMD"]["qty"], 2)
        self.assertAlmostEqual(book["AMD"]["cost"], 400)  # average cost: 2 left at 200
        self.assertAlmostEqual(book["AMD"]["realized"], -40)
        self.assertAlmostEqual(book["BRK-B"]["qty"], 0.5)  # Yahoo-style ticker, decimal comma
        kinds = [t["kind"] for t in out["trades"]]
        for k in ("deposit", "dividend", "fee", "split"):
            self.assertIn(k, kinds)

    def test_a_fully_sold_holding_disappears(self):
        text = "Date,Ticker,Type,Quantity,Price per share\n2024-01-01,AAA,BUY - MARKET,2,10\n2024-02-01,AAA,SELL - MARKET,2,15\n"
        trades = srv.parse_revolut(self.rows(text))["trades"]
        self.assertEqual(srv.revolut_holdings(trades), {})
        self.assertAlmostEqual(srv._rev_book(trades)["AAA"]["realized"], 10)

    def test_any_broker_holdings_list(self):
        out = srv.parse_revolut(self.rows("Symbol;Quantity;Average price\nASML;2;600\n".replace(";", ",")))
        self.assertTrue(out["snapshot"])
        self.assertAlmostEqual(srv.revolut_holdings(out["trades"])["ASML"]["cost"], 1200)

    def test_helpful_errors(self):
        with self.assertRaises(ValueError):
            srv.parse_revolut(self.rows("Date,Amount\n2024-01-01,5\n"))
        with self.assertRaises(ValueError):
            srv.revolut_import({"data": "%PDF-1.4 ...", "name": "x.pdf"})

    def test_excel_file(self):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                       '<si><t>Date</t></si><si><t>Ticker</t></si><si><t>Type</t></si><si><t>Quantity</t></si><si><t>Price per share</t></si>'
                       '<si><t>MSFT</t></si><si><t>BUY - MARKET</t></si></sst>')
            z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                       '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c><c r="D1" t="s"><v>3</v></c><c r="E1" t="s"><v>4</v></c></row>'
                       '<row r="2"><c r="A2"><v>45296</v></c><c r="B2" t="s"><v>5</v></c><c r="C2" t="s"><v>6</v></c><c r="D2"><v>3</v></c><c r="E2"><v>400</v></c></row>'
                       '</sheetData></worksheet>')
        rows = srv._xlsx_rows(buf.getvalue())
        out = srv.parse_revolut(rows)
        self.assertEqual(out["trades"][0]["ts"], 1704412800)
        self.assertAlmostEqual(srv.revolut_holdings(out["trades"])["MSFT"]["cost"], 1200)

    def test_import_saves_privately_and_clear_removes(self):
        import base64
        d = tempfile.mkdtemp()
        old = srv.REVOLUT_FILE
        srv.REVOLUT_FILE = os.path.join(d, ".revolut.json")
        try:
            out = srv.revolut_import({"data": base64.b64encode(REV_CSV.encode()).decode(), "base64": True, "name": "s.csv", "currency": "EUR"})
            self.assertEqual(out["positions"], 3)
            self.assertEqual(oct(os.stat(srv.REVOLUT_FILE).st_mode & 0o777), "0o600")
            again = srv.revolut_import({"data": REV_CSV, "name": "s.csv", "merge": True})
            self.assertEqual(again["trades"], out["trades"])  # merging the same file adds nothing
        finally:
            srv.REVOLUT_FILE = old

    def test_lots_feed_the_history_chart(self):
        trades = srv.parse_revolut(self.rows())["trades"]
        d = tempfile.mkdtemp()
        old, oldp = srv.REVOLUT_FILE, srv.revolut_portfolio
        srv.REVOLUT_FILE = os.path.join(d, ".revolut.json")
        srv.revolut_portfolio = lambda: {"positions": []}
        try:
            srv.revolut_save({"currency": "EUR", "trades": trades})
            lots, base = srv.revolut_lots()
        finally:
            srv.REVOLUT_FILE, srv.revolut_portfolio = old, oldp
        self.assertEqual(base, "EUR")
        amd = [x for x in lots if x["symbol"] == "AMD"]
        self.assertEqual([x["qty"] for x in amd], [3, -1])

    def test_revolut_file_is_git_ignored(self):
        with open(os.path.join(ROOT, ".gitignore")) as fh:
            self.assertIn("dashboard/.revolut.json", fh.read())


class Insights(unittest.TestCase):
    def test_news_impact(self):
        self.assertEqual(srv.news_impact("Nvidia beats estimates and raises guidance"), ("bullish", "high"))
        self.assertEqual(srv.news_impact("Lumentum plunges after weak outlook; analysts downgrade"), ("bearish", "high"))
        self.assertEqual(srv.news_impact("Intel to present at investor conference"), ("neutral", "low"))
        self.assertEqual(srv.news_impact("Micron shares jump 8%")[0], "bullish")

    def test_correlation_of_holdings(self):
        days = ["2025-%02d-%02d" % (m, d) for m in range(1, 13) for d in range(1, 29)]
        import random
        rnd = random.Random(1)
        a, b, c = {}, {}, {}
        pa = pb = pc = 100.0
        for d in days:
            x, y = rnd.gauss(0, 0.02), rnd.gauss(0, 0.02)
            pa *= 1 + x
            pb *= 1 + x + rnd.gauss(0, 0.002)  # almost the same as A
            pc *= 1 + y  # independent
            a[d], b[d], c[d] = pa, pb, pc
        data = {"A": a, "B": b, "C": c}
        old = srv._daily_adj
        srv._daily_adj = lambda s, rng="10y": (data[s], "USD")
        try:
            h = srv.holdings_correlation(["A", "B", "C"])
        finally:
            srv._daily_adj = old
        m = h["matrix"]
        self.assertGreater(m[0][1], 0.9)
        self.assertLess(abs(m[0][2]), 0.35)
        self.assertEqual(m[1][0], m[0][1])
        self.assertEqual(h["pairs"][0]["a"] + h["pairs"][0]["b"], "AB")

    def test_calendar_feed_errors_are_reported_not_raised(self):
        old = srv.econ_calendar

        def boom():
            raise OSError("offline")
        srv.econ_calendar = boom
        try:
            out = srv.calendar_for([])
        finally:
            srv.econ_calendar = old
        self.assertEqual(out["econ"], [])
        self.assertIn("unavailable", out["error"])


class Assistant(unittest.TestCase):
    def setUp(self):
        self.saved = dict(srv.AI)
        self.old_file = srv.AI_FILE
        srv.AI_FILE = os.path.join(tempfile.mkdtemp(), ".ai.json")
        srv._chats.clear()

    def tearDown(self):
        srv.AI.clear()
        srv.AI.update(self.saved)
        srv.AI_FILE = self.old_file

    def test_status_never_returns_the_key(self):
        srv.AI.update(key="sk-ant-secret-1234567890abcdefghij", provider="claude")
        out = json.dumps(srv.ai_status())
        self.assertNotIn("secret", out)
        self.assertIn('"hasKey": true', out)

    def test_bad_key_changes_nothing(self):
        srv.AI.update(provider="builtin", key=None)
        httpd = srv.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
            c.request("POST", "/api/ai/config", body=json.dumps({"provider": "claude", "key": "nope"}), headers={"Content-Type": "application/json"})
            r = c.getresponse()
            self.assertEqual(r.status, 400)
            r.read()
            self.assertEqual(srv.AI["provider"], "builtin")
            self.assertFalse(os.path.exists(srv.AI_FILE))
            c.request("POST", "/api/ai/config", body=json.dumps({"provider": "claude", "key": "sk-ant-abcdefghijklmnopqrstuvwxyz"}),
                      headers={"Content-Type": "application/json"})
            r = c.getresponse()
            body = r.read()
            self.assertEqual(r.status, 200)
            self.assertNotIn(b"sk-ant", body)
            self.assertEqual(oct(os.stat(srv.AI_FILE).st_mode & 0o777), "0o600")
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_ai_file_is_git_ignored(self):
        with open(os.path.join(ROOT, ".gitignore")) as fh:
            self.assertIn("dashboard/.ai.json", fh.read())

    def test_tools_are_read_only(self):
        names = {n for n, _, _, _ in srv.AI_TOOLS}
        self.assertEqual(names, {"get_portfolio", "get_quotes", "get_news", "get_long_term_profile", "get_market_mood",
                                 "get_calendar", "compare", "get_correlation"})
        for bad in ("order", "buy", "sell", "trade", "cancel", "place"):
            self.assertFalse(any(bad in n for n in names))
        self.assertIn("cannot place", srv.AI_SYSTEM)

    def test_unknown_tool_and_failing_tool_return_errors(self):
        self.assertIn("error", srv.ai_run_tool("place_order", {}, {}))
        old = srv.AI_TOOL_FN["get_market_mood"]
        srv.AI_TOOL_FN["get_market_mood"] = lambda a, c: 1 / 0
        try:
            self.assertIn("error", srv.ai_run_tool("get_market_mood", {}, {}))
        finally:
            srv.AI_TOOL_FN["get_market_mood"] = old

    def test_claude_without_key_falls_back_to_builtin(self):
        srv.AI.update(provider="claude", key=None)
        old = srv.ai_chat_builtin
        srv.ai_chat_builtin = lambda q, ctx: {"text": "rules", "used": [], "sources": [], "engine": "Built-in"}
        try:
            self.assertEqual(srv.ai_chat({"message": "hi"})["text"], "rules")
        finally:
            srv.ai_chat_builtin = old

    def test_claude_tool_loop_keeps_history_append_only(self):
        srv.AI.update(provider="claude", key="sk-ant-test-1234567890abcdefghij", model="claude-opus-5-5")
        calls = []

        def fake(messages, model, key):
            calls.append([dict(m) for m in messages])
            if len(calls) == 1:
                return {"stop_reason": "tool_use", "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "tool_use", "id": "tu1", "name": "get_market_mood", "input": {}}], "usage": {}}
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Market is calm.",
                    "citations": [{"url": "https://example.com/a", "title": "A"}]}], "usage": {"input_tokens": 10, "output_tokens": 5}}
        old, oldm = srv._claude, srv.AI_TOOL_FN["get_market_mood"]
        srv._claude = fake
        srv.AI_TOOL_FN["get_market_mood"] = lambda a, c: {"mood": "calm"}
        try:
            out = srv.ai_chat({"message": "How is the market?"})
            again = srv.ai_chat({"message": "And tomorrow?", "chat": out["chat"]})
        finally:
            srv._claude, srv.AI_TOOL_FN["get_market_mood"] = old, oldm
        self.assertEqual(out["text"], "Market is calm.")
        self.assertEqual(out["sources"][0]["url"], "https://example.com/a")
        self.assertIn("get_market_mood", out["used"][0])
        second = calls[1]
        self.assertEqual(second[1]["content"][0]["signature"], "sig")  # thinking block passed back unchanged
        self.assertEqual(second[2]["content"][0]["type"], "tool_result")
        self.assertEqual(json.loads(second[2]["content"][0]["content"]), {"mood": "calm"})
        self.assertEqual(again["chat"], out["chat"])
        self.assertEqual(calls[2][:len(second)], second)  # earlier turns are never edited

    def test_claude_request_shape(self):
        sent = {}

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"stop_reason": "end_turn", "content": []}'

        def fake_open(req, timeout=None):
            sent["url"], sent["headers"], sent["body"] = req.full_url, dict(req.header_items()), json.loads(req.data)
            return Resp()
        old = srv.urllib.request.urlopen
        srv.urllib.request.urlopen = fake_open
        try:
            srv._claude([{"role": "user", "content": "hi"}], "claude-opus-5-5", "sk-ant-x")
        finally:
            srv.urllib.request.urlopen = old
        b, h = sent["body"], {k.lower(): v for k, v in sent["headers"].items()}
        self.assertEqual(sent["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(h["anthropic-version"], "2026-10-21")
        self.assertEqual(h["x-api-key"], "sk-ant-x")
        self.assertEqual(b["model"], "claude-opus-5-5")
        self.assertNotIn("thinking", b)
        self.assertNotIn("temperature", b)
        self.assertEqual(b["fallbacks"], "default")
        self.assertEqual(h["anthropic-beta"], "server-side-fallback-2026-07-01")
        self.assertIn({"type": "web_search_20260209", "name": "web_search", "max_uses": 4}, b["tools"])

    def test_ollama_tool_loop(self):
        import http.server
        seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append(body)
                if len(seen) == 1:
                    msg = {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_market_mood", "arguments": {}}}]}
                else:
                    msg = {"role": "assistant", "content": "<think>hmm</think>Calm today."}
                data = json.dumps({"message": msg}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        srv.AI.update(provider="ollama", ollama_url="http://127.0.0.1:%d" % httpd.server_address[1], ollama_model="qwen3:8b")
        oldm = srv.AI_TOOL_FN["get_market_mood"]
        srv.AI_TOOL_FN["get_market_mood"] = lambda a, c: {"mood": "calm"}
        try:
            out = srv.ai_chat({"message": "How is the market?"})
        finally:
            srv.AI_TOOL_FN["get_market_mood"] = oldm
            httpd.shutdown()
            httpd.server_close()
        self.assertEqual(out["text"], "Calm today.")
        self.assertEqual(seen[1]["messages"][-1]["role"], "tool")
        self.assertEqual(seen[0]["messages"][0]["role"], "system")

    def test_ollama_must_be_local(self):
        srv.AI.update(provider="ollama", ollama_url="http://evil.example:11434")
        with self.assertRaises(RuntimeError):
            srv.ai_chat({"message": "hi"})

    def test_builtin_finds_tickers_and_names(self):
        old = srv.directory_names
        srv.directory_names = lambda: {"KLAC": "KLA Corporation", "AMAT": "Applied Materials, Inc."}
        try:
            self.assertEqual(srv._find_symbols("Compare KLAC vs AMAT", []), ["KLAC", "AMAT"])
            self.assertEqual(srv._find_symbols("is it a BUY NOW", []), [])
        finally:
            srv.directory_names = old

    def test_builtin_help_for_unknown_questions(self):
        oldp, oldd = srv._portfolio_view, srv.directory_names
        srv._portfolio_view = lambda manual=None: ([], None, None)
        srv.directory_names = lambda: {}
        try:
            out = srv.ai_chat_builtin("hello there", {})
        finally:
            srv._portfolio_view, srv.directory_names = oldp, oldd
        self.assertIn("Try", out["text"])


class Projection(unittest.TestCase):
    """The 10-year plan simulator (runs in the browser; checked here with node)."""

    def run_js(self, expr):
        import shutil, subprocess, json
        if not shutil.which("node"):
            self.skipTest("node not installed")
        js = os.path.join(ROOT, "dashboard", "static", "projection.js")
        code = "global.window={};require(%s);const P=window.Projection;console.log(JSON.stringify(%s))" % (json.dumps(js), expr)
        return json.loads(subprocess.check_output(["node", "-e", code], timeout=60))

    def test_no_growth_no_swings_gives_back_the_deposits(self):
        a = '{etfRet:0,etfVol:0,stkRet:0,stkVol:0,corr:0.75,infl:0}'
        r = self.run_js("P.simulate({start:2500,monthly:1200,years:10,etf:50,raise:0,a:%s},200)" % a)
        self.assertAlmostEqual(r["pct"][10]["p50"], 2500 + 120 * 1200, places=6)
        self.assertEqual(r["deposits"][10], 2500 + 120 * 1200)

    def test_steady_return_matches_the_formula(self):
        a = '{etfRet:6,etfVol:0,stkRet:6,stkVol:0,corr:0.75,infl:0}'
        r = self.run_js("P.simulate({start:0,monthly:100,years:10,etf:100,raise:0,a:%s},50)" % a)
        m = 0.06 / 12
        self.assertAlmostEqual(r["pct"][10]["p50"], 100 * ((1 + m) ** 120 - 1) / m, delta=1)

    def test_an_etf_core_narrows_the_range(self):
        a = '{etfRet:7.5,etfVol:15,stkRet:11,stkVol:42,corr:0.75,infl:2.5}'
        o = "{start:2500,monthly:1200,years:10,raise:0,a:%s,etf:%d}"
        stocks = self.run_js("P.simulate(%s,2000)" % (o % (a, 0)))["pct"][10]
        mixed = self.run_js("P.simulate(%s,2000)" % (o % (a, 50)))["pct"][10]
        self.assertGreater(mixed["p10"], stocks["p10"])
        self.assertLess(mixed["p90"], stocks["p90"])


class Rules(unittest.TestCase):
    def ind(self, closes, vol=1e6, last_vol=None):
        bars = fake_bars(closes, vol)["bars"]
        if last_vol is not None:
            bars[-1]["v"] = last_vol
        return srv.indicators(bars)

    def test_missing_history_does_not_cost_points(self):
        res = srv.rule(self.ind([100 + i * 0.5 for i in range(80)]), 79)  # too short for a 200-day average
        texts = " ".join(x["text"] for x in res["reasons"])
        self.assertNotIn("200-day", texts)
        self.assertNotIn("golden cross", texts)

    def test_extended_limit_is_always_below_the_price(self):
        closes = [100 * 1.002 ** i for i in range(250)] + [100 * 1.002 ** 250 * (1.03 ** k) for k in range(1, 11)]
        res = srv.rule(self.ind(closes), len(closes) - 1)
        self.assertTrue(res["status"].startswith("Wait"))
        self.assertLess(res["plan"]["entry"], closes[-1])

    def test_breakout_needs_volume_and_a_decent_score(self):
        closes = [100.0 + (i % 5) * 0.2 for i in range(260)] + [103.0]
        quiet = srv.rule(self.ind(closes), len(closes) - 1)
        self.assertNotEqual(quiet["status"], "Buy now: breakout")

    def test_volume_uses_completed_days_only(self):
        ind = self.ind([100.0] * 40, vol=1000, last_vol=5000)
        self.assertEqual(ind["vprev"][-1], 1000)

    def test_backtest_produces_r_multiples(self):
        import math as _m
        closes = [100 * 1.0015 ** i * (1 + 0.06 * _m.sin(i / 5.0)) for i in range(700)]  # uptrend with regular pullbacks
        old, old_b = srv.get_bars, srv.bench_by_day
        srv.get_bars = lambda s, rng="2y": fake_bars(closes)
        srv.bench_by_day = lambda s, rng="2y": ("SPY", {})
        try:
            srv._cache.pop(("backtest", "ZZBT", 40), None)
            b = srv.backtest("ZZBT")
        finally:
            srv.get_bars, srv.bench_by_day = old, old_b
        self.assertGreater(b["n"], 0)
        for t in b["trades"]:
            self.assertGreaterEqual(t["R"], -3)  # a stop can gap, but not absurdly
        self.assertEqual(len(b["equity"]), b["n"])


class Journal(unittest.TestCase):
    def test_fifo_pairs_buys_and_sells(self):
        old = srv.t212_orders
        srv.t212_orders = lambda: ([
            {"id": "1", "symbol": "AAA", "ts": 1700000000, "qty": 10, "price": 10.0},
            {"id": "2", "symbol": "AAA", "ts": 1700086400, "qty": 10, "price": 20.0},
            {"id": "3", "symbol": "AAA", "ts": 1700864000, "qty": -15, "price": 30.0},
            {"id": "4", "symbol": "BBB", "ts": 1700000000, "qty": -5, "price": 9.0},  # sell without a known buy
        ], True)
        try:
            j = srv.trade_journal()
        finally:
            srv.t212_orders = old
        self.assertEqual(j["stats"]["n"], 1)
        t = j["trades"][0]
        self.assertAlmostEqual(t["entry"], (10 * 10 + 5 * 20) / 15.0, places=3)
        self.assertAlmostEqual(t["pnl"], 15 * 30 - 200, places=2)
        self.assertEqual(j["openLots"], [{"symbol": "AAA", "qty": 5.0}])


class Currency(unittest.TestCase):
    def test_minor_units_and_same_currency(self):
        self.assertEqual(srv.fx_rate("USD", "USD"), 1.0)
        self.assertEqual(srv.fx_rate("GBp", "GBP"), 0.01)
        self.assertEqual(srv.fx_rate("GBP", "GBp"), 100.0)

    def test_benchmarks_by_exchange(self):
        self.assertEqual(srv.benchmark_for("VUSA.L"), "^FTSE")
        self.assertEqual(srv.benchmark_for("SAP.DE"), "^GDAXI")
        self.assertEqual(srv.benchmark_for("AAPL"), "SPY")


class Earnings(unittest.TestCase):
    def test_no_wait_never_blocks(self):
        import time as _t
        old = srv.nasdaq
        srv.nasdaq = lambda path, ttl=0, timeout=25: (_t.sleep(2), {"announcement": "Earnings announcement* for ZZZ: Jan 05, 2099"})[1]
        srv._cache.pop(("earnings", "ZZZ"), None)
        try:
            t0 = _t.time()
            self.assertIsNone(srv.next_earnings("ZZZ", wait=False))
            self.assertLess(_t.time() - t0, 0.5)
            srv._cache.pop(("earnings", "ZZZ"), None)
            e = srv.next_earnings("ZZZ", wait=True)
            self.assertEqual(e["date"], "2099-01-05")
            self.assertGreater(e["days"], 1000)
        finally:
            srv.nasdaq = old
        self.assertIsNone(srv.next_earnings("VUSA.L"))


class LongTerm(unittest.TestCase):
    def test_linear_scores(self):
        self.assertEqual(srv._lin(25, 8, 25), 100.0)
        self.assertEqual(srv._lin(8, 8, 25), 0.0)
        self.assertEqual(srv._lin(1, 3, 1), 100.0)  # falling scale (lower PEG is better)
        self.assertIsNone(srv._lin(None, 0, 1))

    def test_max_drawdown(self):
        self.assertAlmostEqual(srv._max_drawdown([100, 120, 60, 130, 117]), -0.5)

    def test_irr_of_a_simple_doubling(self):
        self.assertAlmostEqual(srv._irr([(0, -100.0), (1, 110.0)]), 0.10, places=4)

    def test_time_weighted_stats_ignore_deposits(self):
        h = {"dates": ["2024-01-01", "2024-07-01", "2025-01-01", "2025-07-01"],
             "value": [100.0, 110.0, 220.0, 242.0], "flow": [100.0, 0.0, 100.0, 0.0]}
        st = srv._twr_stats(h)["twr"]
        # growth per step with the 100 deposit taken out: 110/100, (220-100)/110, 242/220
        self.assertAlmostEqual(st["total"], 100 * (1.10 * (120 / 110.0) * 1.10 - 1), places=1)


class Logos(unittest.TestCase):
    def test_monogram_for_indices_and_bad_input(self):
        d, t = srv.get_logo("^VIX")
        self.assertEqual(t, "image/svg+xml")
        self.assertIn(b"VIX", d)
        d, t = srv.get_logo("../../etc/passwd")
        self.assertEqual(t, "image/svg+xml")

    def test_cached_logo_is_served_from_disk(self):
        import tempfile
        old = srv.LOGO_DIR
        srv.LOGO_DIR = tempfile.mkdtemp()
        try:
            png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
            with open(os.path.join(srv.LOGO_DIR, "ZZTEST.png"), "wb") as f:
                f.write(png)
            self.assertEqual(srv.get_logo("ZZTEST"), (png, "image/png"))
        finally:
            srv.LOGO_DIR = old


class PhoneMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = srv.ThreadingHTTPServer(("0.0.0.0", 0), srv.Handler)
        cls.httpd.phone_token = "t" * 32
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.ip = srv.lan_ip()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def req(self, path, headers=None, method="GET", body=None):
        c = http.client.HTTPConnection(self.ip, self.port, timeout=5)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        return r.status, r.getheader("Set-Cookie") or "", r.read()

    def test_other_devices_need_the_key(self):
        if not self.ip or self.ip.startswith("127."):
            self.skipTest("no network address")
        self.assertEqual(self.req("/api/universe")[0], 403)
        self.assertEqual(self.req("/?key=wrong")[0], 403)
        status, cookie, body = self.req("/?key=" + "t" * 32)
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", cookie)
        self.assertEqual(self.req("/api/universe", {"Cookie": "td_key=" + "t" * 32})[0], 200)

    def test_key_cookie_doesnt_allow_other_sites(self):
        if not self.ip or self.ip.startswith("127."):
            self.skipTest("no network address")
        st, _, _ = self.req("/api/t212/disconnect", {"Cookie": "td_key=" + "t" * 32, "Origin": "http://evil.example",
                                                     "Content-Type": "application/json"}, "POST", "{}")
        self.assertEqual(st, 403)

    def test_phone_cannot_read_the_key(self):
        if not self.ip or self.ip.startswith("127."):
            self.skipTest("no network address")
        old = srv.lan_ip
        srv.lan_ip = lambda: "203.0.113.9"  # a real phone's address differs from the computer's
        try:
            st, _, body = self.req("/api/phone", {"Cookie": "td_key=" + "t" * 32})
        finally:
            srv.lan_ip = old
        self.assertEqual(st, 403)
        self.assertNotIn(b"tttt", body)


class Directory(unittest.TestCase):
    def setUp(self):
        self._dir = dict(srv._dir)
        srv._dir.update(at=time.time(), rows=[
            {"s": "AAAP", "n": "Obscure Fund", "t": "ETF", "x": "Nasdaq", "r": "United States"},
            {"s": "AAPL", "n": "Apple Inc.", "t": "Stock", "x": "Nasdaq", "r": "United States"},
            {"s": "NESN.SW", "n": "Nestle", "t": "Stock", "x": "", "r": "Switzerland"},
            {"s": "SPY", "n": "SPDR S&P 500 ETF Trust", "t": "ETF", "x": "NYSE Arca", "r": "United States"}], names={})

    def tearDown(self):
        srv._dir.clear()
        srv._dir.update(self._dir)

    def test_well_known_first_and_filters(self):
        d = srv.directory_page()
        self.assertEqual([r["s"] for r in d["rows"]][:2], ["AAPL", "SPY"])
        self.assertEqual(d["rows"][-1]["s"], "AAAP")
        self.assertEqual([r["s"] for r in srv.directory_page(kind="ETF")["rows"]], ["SPY", "AAAP"])
        self.assertEqual([r["s"] for r in srv.directory_page(q="nestle")["rows"]], ["NESN.SW"])
        self.assertEqual(srv.directory_page(q="aapl")["rows"][0]["s"], "AAPL")
        self.assertEqual(srv.directory_page(region="Switzerland")["total"], 1)

    def test_world_list_is_valid(self):
        with open(os.path.join(ROOT, "dashboard", "world.json")) as fh:
            w = json.load(fh)
        n = sum(len(v) for v in w["regions"].values())
        self.assertGreater(n, 150)
        for v in w["regions"].values():
            for it in v:
                self.assertTrue(it["s"] and it["n"])


class CompareRisk(unittest.TestCase):
    def test_stats_blend_and_portfolio_fit(self):
        import math as _m
        days = ["%04d-%02d-%02d" % (2021 + i // 250, 1 + (i % 250) // 21, 1 + (i % 21)) for i in range(1300)]
        series = {
            "AAA": {d: 100 * 1.0006 ** i * (1 + 0.02 * _m.sin(i / 7.0)) for i, d in enumerate(days)},
            "BBB": {d: 100 * 1.0003 ** i * (1 + 0.01 * _m.cos(i / 11.0)) for i, d in enumerate(days)},
            "SPY": {d: 100 * 1.0004 ** i * (1 + 0.01 * _m.sin(i / 9.0)) for i, d in enumerate(days)},
        }
        old = srv._try_daily
        srv._try_daily = lambda sym: (series.get(sym, {}), "USD")
        old_t = srv.time.time
        srv.time.time = lambda: srv.calendar.timegm((2026, 3, 1, 0, 0, 0))
        try:
            d = srv.compare_risk(["AAA", "BBB"], portfolio={"BBB": 1.0}, add_frac=0.2)
        finally:
            srv._try_daily = old
            srv.time.time = old_t
        a, b = d["stats"]["AAA"], d["stats"]["BBB"]
        self.assertGreater(a["vol"], b["vol"])
        self.assertLessEqual(a["maxdd"], 0)
        self.assertIn("AAA|BBB", d["corr"])
        self.assertEqual(sum(d["equalRisk"].values()), 100)
        self.assertGreater(d["equalRisk"]["BBB"], d["equalRisk"]["AAA"])  # calmer one gets more money for equal risk
        self.assertEqual(d["portfolio"]["fit"]["BBB"]["corr"], 1.0)
        self.assertEqual(len(d["norm"]["AAA"]), len(d["dates"]))
        pb = d["pairBlend"]["AAA|BBB"]
        self.assertIn("0.80", pb)
        # more of the calmer stock = smaller swings
        self.assertLess(pb["0.20"]["vol"], pb["0.80"]["vol"])


if __name__ == "__main__":
    unittest.main()
