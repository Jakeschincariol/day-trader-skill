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
        with open(os.path.join(ROOT, "dashboard", "server.py")) as fh:
            src = fh.read()
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


class EntryCheck(unittest.TestCase):
    def series(self, closes):
        c = list(closes)
        return c, srv.sma(c, 20), srv.sma(c, 50), srv.sma(c, 200)

    def test_states(self):
        up = [100 * 1.001 ** i for i in range(400)]
        self.assertEqual(srv._entry_state(*self.series(up), 399), "uptrend")
        fall = up[:300] + [up[299] * 0.995 ** k for k in range(1, 101)]
        self.assertEqual(srv._entry_state(*self.series(fall), 399), "falling")
        dip = up[:380] + [up[379] * 0.985 ** k for k in range(1, 21)]  # sharp 3-week dip, long trend still rising
        self.assertIn(srv._entry_state(*self.series(dip), 399), ("pullback", "falling"))
        self.assertIsNone(srv._entry_state(*self.series(up[:150]), 149))

    def test_verdicts(self):
        v = lambda **k: srv._entry_verdict(k)
        self.assertEqual(v(state="falling", zone="Accumulate")["title"], "Don't buy it all at once")
        self.assertEqual(v(state="uptrend", zone="Accumulate")["tone"], "up")
        self.assertEqual(v(state="uptrend", zone="Speculative")["title"], "Careful")
        self.assertEqual(v(state="uptrend", zone="Stretched")["title"], "Fine, but no discount")
        notes = v(state="falling", zone="Accumulate+", earnings={"date": "2026-11-20", "days": 5}, marketWeak="red")["notes"]
        self.assertEqual(len(notes), 3)

    def test_ladder_from_past_dips(self):
        import random
        rnd = random.Random(3)
        px, c = 100.0, []
        for i in range(2600):
            px *= 1 + rnd.gauss(0.0004, 0.02)
            c.append(px)
        res = {"meta": {"currency": "USD"}}
        old = (srv._chart, srv._adj, srv.next_earnings, srv.market_regime, srv.lt_profile)
        srv._chart = lambda sym, q, ttl: res
        srv._adj = lambda r: [(i * 86400, x) for i, x in enumerate(c)]
        srv.next_earnings = lambda s, wait=True: None
        srv.market_regime = lambda: {"level": "green"}
        srv.lt_profile = lambda s: {"zone": "Accumulate", "score": 70}
        srv.purge(lambda k: k[0] == "entry")
        try:
            e = srv.lt_entry("TEST")
        finally:
            srv._chart, srv._adj, srv.next_earnings, srv.market_regime, srv.lt_profile = old
            srv.purge(lambda k: k[0] == "entry")
        self.assertAlmostEqual(sum(l["share"] for l in e["ladder"]), 1.0, places=3)
        prices = [l["price"] for l in e["ladder"] if l["price"]]
        self.assertEqual(prices, sorted(prices, reverse=True))
        self.assertTrue(all(p < e["price"] * 0.98 for p in prices))
        self.assertLess(e["any"]["typicalDip"], 0)
        self.assertLessEqual(e["any"]["deepDip"], e["any"]["typicalDip"])


class Challenger(unittest.TestCase):
    def run_with(self, data):
        old = (srv.lt_profile, srv._quick_stats, srv._peers, srv._outside_ai)
        srv.lt_profile = lambda s: {"name": s, "score": data[s][0], "zone": "Accumulate", "fundamentals": True}
        srv._quick_stats = lambda s, years=5: {"cagr": 10.0, "sortino": data[s][1], "maxdd": data[s][2], "years": 5.0}
        srv._peers = lambda syms: ["P1", "P2"]
        srv._outside_ai = lambda: ["O1", "O2"]
        try:
            return srv.challenger(["A", "B"])
        finally:
            srv.lt_profile, srv._quick_stats, srv._peers, srv._outside_ai = old

    def test_winner_must_beat_every_pick(self):
        data = {"A": (70, 0.8, -50), "B": (75, 0.6, -40), "P1": (80, 0.9, -42), "P2": (90, 0.5, -30),
                "O1": (85, 1.2, -35), "O2": (88, 1.0, -60)}
        c = self.run_with(data)
        self.assertEqual(c["sameGroup"]["winner"]["symbol"], "P1")  # P2 has a higher score but a weaker risk-adjusted return
        self.assertEqual(c["outsideAI"]["winner"]["symbol"], "O1")  # O2's worst fall is too deep
        self.assertEqual(c["bar"], {"score": 75, "sortino": 0.8, "maxdd": -45})

    def test_no_winner_reports_the_closest(self):
        data = {"A": (90, 1.5, -20), "B": (85, 1.4, -25), "P1": (80, 1.6, -15), "P2": (60, 0.2, -70),
                "O1": (50, 0.1, -80), "O2": (40, 0.1, -80)}
        c = self.run_with(data)
        self.assertIsNone(c["sameGroup"]["winner"])
        self.assertEqual(c["sameGroup"]["closest"]["symbol"], "P1")

    def test_needs_two_picks(self):
        with self.assertRaises(ValueError):
            srv.challenger(["A"])


class RadarSectors(unittest.TestCase):
    def test_every_sector_is_scanned(self):
        other = [t for t in srv.RADAR_THEMES if t not in srv.AI_RADAR_THEMES]
        for want in ("Healthcare & biotech", "Energy: oil & gas", "Banks & fintech", "Consumer & retail", "Defense & aerospace"):
            self.assertIn(want, other)
        self.assertGreaterEqual(sum(len(srv.RADAR_THEMES[t]) for t in other), 60)
        self.assertTrue(set(srv.AI_RADAR_THEMES) <= set(srv.RADAR_THEMES))


class FinancialModelingPrep(unittest.TestCase):
    ANSWERS = {
        "profile": [{"symbol": "ASML.AS", "companyName": "ASML", "marketCap": 300e9, "sector": "Technology", "industry": "Semiconductors",
                     "country": "NL", "lastDividend": 6.4, "isEtf": False}],
        "ratios-ttm": [{"priceToEarningsRatioTTM": 35.0, "priceToEarningsGrowthRatioTTM": 1.4, "operatingProfitMarginTTM": 0.31,
                        "debtToEquityRatioTTM": 0.25, "dividendYieldTTM": 0.009, "netIncomePerShareTTM": 20.0}],
        "key-metrics-ttm": [{"returnOnEquityTTM": 0.45, "freeCashFlowYieldTTM": 0.03, "cashAndCashEquivalentsTTM": 7e9, "netDebtTTM": -2e9}],
        "income-statement": [{"date": "2025-12-31", "revenue": 32e9, "netIncome": 9e9}, {"date": "2024-12-31", "revenue": 28e9, "netIncome": 7.5e9},
                             {"date": "2023-12-31", "revenue": 27e9, "netIncome": 7.8e9}],
    }

    def setUp(self):
        self.old = (srv.fmp_get, dict(srv.FMP))

    def tearDown(self):
        srv.fmp_get = self.old[0]
        srv.FMP.clear()
        srv.FMP.update(self.old[1])

    def fake(self, answers):
        def get(endpoint, symbol=None, ttl=0, **params):
            if endpoint not in answers:
                raise srv.FmpRefused("not included in your FMP plan")
            return answers[endpoint]
        srv.fmp_get = get

    def test_figures_in_the_score_shape(self):
        self.fake(self.ANSWERS)
        f = srv.fmp_figures("asml.as")
        self.assertTrue(f["available"])
        self.assertAlmostEqual(f["highlights"]["roe"], 45.0)
        self.assertAlmostEqual(f["highlights"]["operatingMargin"], 31.0)
        self.assertAlmostEqual(f["highlights"]["debtEquity"], 25.0)
        self.assertAlmostEqual(f["highlights"]["freeCashFlow"], 9e9)
        self.assertAlmostEqual(f["highlights"]["totalDebt"], 5e9)
        self.assertEqual(f["valuation"]["peTTM"], 35.0)
        self.assertEqual([x["year"] for x in f["revVsEarnings"]["annual"]], ["2023", "2024", "2025"])  # oldest first, like Nasdaq
        self.assertEqual(f["source"], "Financial Modeling Prep")

    def test_older_field_names_still_work(self):
        a = dict(self.ANSWERS)
        a["ratios-ttm"] = [{"priceEarningsRatioTTM": 20.0, "operatingProfitMarginTTM": "0.2"}]
        self.fake(a)
        f = srv.fmp_figures("X")
        self.assertEqual(f["valuation"]["peTTM"], 20.0)
        self.assertAlmostEqual(f["highlights"]["operatingMargin"], 20.0)

    def test_plan_refusals_are_survivable(self):
        a = {k: v for k, v in self.ANSWERS.items() if k in ("profile", "ratios-ttm")}  # metrics and statements refused
        self.fake(a)
        f = srv.fmp_figures("X")
        self.assertEqual(f["revVsEarnings"]["annual"], [])
        self.fake({})
        with self.assertRaises(srv.FmpRefused):
            srv.fmp_figures("X")

    def test_company_figures_prefers_nasdaq_then_fmp(self):
        self.fake(self.ANSWERS)
        srv.FMP["key"] = "k" * 20
        old = srv.fundamentals
        srv.fundamentals = lambda s: {"available": False}
        try:
            self.assertEqual(srv.company_figures("ASML.AS")["source"], "Financial Modeling Prep")
            srv.fundamentals = lambda s: {"available": True, "source": "nasdaq"}
            self.assertEqual(srv.company_figures("AAPL")["source"], "nasdaq")
            srv.FMP["key"] = None
            srv.fundamentals = lambda s: {"available": False}
            self.assertFalse(srv.company_figures("ASML.AS")["available"])
        finally:
            srv.fundamentals = old

    def test_non_us_results_dates(self):
        srv.FMP["key"] = "k" * 20
        future = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 10 * 86400))
        self.fake({"earnings": [{"date": "2020-01-01"}, {"date": future}]})
        srv.purge(lambda k: k[0] == "earnings" and k[1] == "6857.T")
        try:
            e = srv.next_earnings("6857.T", wait=True)
        finally:
            srv.purge(lambda k: k[0] == "earnings" and k[1] == "6857.T")
        self.assertEqual(e["date"], future)
        self.assertIn(e["days"], (9, 10))

    def test_key_route_validates_and_never_echoes(self):
        d = tempfile.mkdtemp()
        old_file = srv.FMP_FILE
        srv.FMP_FILE = os.path.join(d, ".fmp.json")
        httpd = srv.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
            c.request("POST", "/api/fmp/key", body=json.dumps({"key": "bad key!"}), headers={"Content-Type": "application/json"})
            r = c.getresponse(); r.read()
            self.assertEqual(r.status, 400)
            c.request("POST", "/api/fmp/key", body=json.dumps({"key": "abcDEF1234567890xyz"}), headers={"Content-Type": "application/json"})
            r = c.getresponse(); body = r.read()
            self.assertEqual(r.status, 200)
            self.assertNotIn(b"abcDEF", body)
            self.assertTrue(json.loads(body)["hasKey"])
            self.assertEqual(oct(os.stat(srv.FMP_FILE).st_mode & 0o777), "0o600")
        finally:
            httpd.shutdown(); httpd.server_close()
            srv.FMP_FILE = old_file

    def test_files_are_git_ignored(self):
        with open(os.path.join(ROOT, ".gitignore")) as fh:
            g = fh.read()
        for f in ("dashboard/.fmp.json", "dashboard/.fmp-cache.json", "dashboard/.fdb-equities.bz2"):
            self.assertIn(f, g)


class FinanceDatabase(unittest.TestCase):
    def make(self, rows):
        import bz2
        import csv
        import io
        head = ["symbol", "name", "summary", "currency", "sector", "industry_group", "industry", "exchange", "mic", "market", "country",
                "state", "city", "zipcode", "website", "market_cap", "isin", "cusip", "figi", "composite_figi", "shareclass_figi", "delisted"]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(head)
        for r in rows:
            w.writerow([r.get(k, "") for k in head])
        path = os.path.join(tempfile.mkdtemp(), "eq.bz2")
        with bz2.open(path, "wt", encoding="utf-8") as f:
            f.write(buf.getvalue())
        return path

    def test_parse_filters_and_dedupes(self):
        semi = {"sector": "Information Technology", "industry": "Semiconductors & Chip Equipment", "market_cap": "Mega Cap"}
        rows = [dict(semi, symbol="KLAC", name="KLA Corporation", exchange="NMS", country="United States", isin="US1"),
                dict(semi, symbol="ASML", name="ASML Holding N.V.", exchange="NMS", country="Netherlands", isin="NL1"),
                dict(semi, symbol="ASML.AS", name="ASML Holding N.V.", exchange="AMS", country="Netherlands", isin="NL1"),
                dict(semi, symbol="0ABC.L", name="Foreign Line", exchange="LSE", isin="XX9"),
                dict(semi, symbol="MCHPP", name="Microchip Depositary Shares", exchange="NMS", isin="US7"),
                dict(semi, symbol="OLD", name="Gone Inc", exchange="NMS", isin="US8", delisted="True"),
                dict(semi, symbol="000660.KS", name="SK hynix Inc.", exchange="KSC", country="South Korea", isin="KR1"),
                {"symbol": "PG", "name": "Procter & Gamble", "sector": "Consumer Staples", "industry": "Household Products",
                 "market_cap": "Mega Cap", "exchange": "NYQ", "country": "United States", "isin": "US2"}]
        rws, by_ind = srv.fdb_parse(self.make(rows))
        self.assertNotIn("OLD", rws)
        self.assertEqual(rws["000660.KS"][3], "South Korea")
        old = dict(srv.FDB)
        srv.FDB.update(rows=rws, byIndustry=by_ind)
        try:
            peers = srv.fdb_peers(["KLAC"])
            self.assertIn("ASML", peers)
            self.assertNotIn("ASML.AS", peers)  # same company once
            self.assertNotIn("0ABC.L", peers)
            self.assertNotIn("MCHPP", peers)
            self.assertIn("000660.KS", peers)
            self.assertEqual(srv.fdb_mega_outside({"Semiconductors & Chip Equipment"}), ["PG"])
            self.assertEqual(srv.fdb_info("ASML")["country"], "Netherlands")
        finally:
            srv.FDB.clear(); srv.FDB.update(old)

    def test_main_listing_rules(self):
        ok = srv.fdb_main_listing
        self.assertTrue(ok("6857.T", "Advantest"))
        self.assertTrue(ok("BRK-B", "Berkshire"))
        self.assertFalse(ok("BAC-PB", "Bank of America"))
        self.assertFalse(ok("1AMZN.MI", "Amazon"))
        self.assertFalse(ok("XYZ", "XYZ 5% Preferred"))


class Tailscale(unittest.TestCase):
    def test_address_is_tailscale_range_or_none(self):
        ip = srv.tailscale_ip()
        if ip is not None:
            a, b = (int(x) for x in ip.split(".")[:2])
            self.assertEqual(a, 100)
            self.assertTrue(64 <= b <= 127)

    def test_phone_info_includes_the_away_link(self):
        old = srv.tailscale_ip
        srv.tailscale_ip = lambda: "100.101.102.103"
        httpd = srv.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        httpd.phone_token = "TOKEN123"
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
            c.request("GET", "/api/phone", headers={"Host": "127.0.0.1:%d" % httpd.server_address[1]})
            d = json.loads(c.getresponse().read())
        finally:
            httpd.shutdown(); httpd.server_close()
            srv.tailscale_ip = old
        self.assertEqual(d["tailscaleIp"], "100.101.102.103")
        self.assertEqual(d["awayUrl"], "http://100.101.102.103:%d/?key=TOKEN123" % httpd.server_address[1])


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


class Runners(unittest.TestCase):
    """Day Runners: who gets in, the setup labels, and the entry/stop/target math."""
    GMT = -18000  # New York (EST)
    OPEN = 1794321000  # 9:30 New York time

    def bars(self, closes, start=None, vol=100000):
        start = self.OPEN if start is None else start
        out, prev = [], closes[0]
        for i, c in enumerate(closes):
            out.append((start + i * 300, prev, max(prev, c) * 1.01, min(prev, c) * 0.99, c, vol))
            prev = c
        return out

    def test_breakout_near_high_of_day(self):
        L = srv.runner_levels(self.bars([2, 2.4, 2.8, 3.0, 3.2, 3.3]), 2.0, self.GMT, "open")
        self.assertEqual(L["setup"], "breakout")
        p = L["plan"]
        self.assertAlmostEqual(p["entry"], L["hod"] + 0.01, places=2)
        self.assertLess(p["stop"], p["entry"] * 0.985 + 1e-9)
        risk = p["entry"] - p["stop"]
        self.assertAlmostEqual(p["t1"], p["entry"] + 2 * risk, places=1)
        self.assertAlmostEqual(p["t2"], p["entry"] + 3 * risk, places=1)
        self.assertAlmostEqual(L["highPct"], 100 * (L["hod"] / 2.0 - 1), delta=0.2)

    def test_pullback_above_vwap(self):
        L = srv.runner_levels(self.bars([2, 2.5, 3.0, 3.5, 4.0, 3.7, 3.6]), 2.0, self.GMT, "open")
        self.assertEqual(L["setup"], "pullback")
        self.assertGreater(L["last"], L["vwap"])
        self.assertLess(L["plan"]["entry"], L["hod"])

    def test_under_vwap_needs_a_reclaim(self):
        L = srv.runner_levels(self.bars([4, 3.9, 3.8, 3.7, 3.65, 3.6] + [3.55] * 6), 3.0, self.GMT, "open")
        self.assertEqual(L["setup"], "below")
        self.assertAlmostEqual(L["plan"]["entry"], L["vwap"] + 0.01, places=2)

    def test_faded_runner_has_no_entry(self):
        # like STAK: ran from 4.09 to 7.00, now back near 4.90
        L = srv.runner_levels(self.bars([4.2, 5.5, 6.9, 6.0, 5.2, 4.9]), 4.09, self.GMT, "open")
        self.assertEqual(L["setup"], "faded")
        self.assertIsNone(L["plan"])
        self.assertLess(L["fromHighPct"], -25)

    def test_premarket_uses_premarket_high_and_closed_plans_the_next_day(self):
        pre = self.bars([2, 2.3, 2.6, 2.5], start=self.OPEN - 3600)  # 8:30 New York time
        L = srv.runner_levels(pre, 2.0, self.GMT, "pre")
        self.assertEqual(L["setup"], "pre")
        self.assertAlmostEqual(L["plan"]["entry"], L["pmHigh"] + 0.01, places=2)
        day = self.bars([2, 2.4, 2.8, 3.0, 3.1])
        C = srv.runner_levels(day, 2.0, self.GMT, "closed")
        self.assertEqual(C["setup"], "next")
        self.assertLessEqual(C["plan"]["stop"], C["vwap"])

    def test_sub_dollar_prices_keep_four_decimals(self):
        L = srv.runner_levels(self.bars([0.5, 0.56, 0.6, 0.62]), 0.45, self.GMT, "open")
        self.assertAlmostEqual(L["plan"]["entry"], L["hod"] + 0.0001, places=4)

    def test_who_gets_in(self):
        q = {"symbol": "RUN", "quoteType": "EQUITY", "marketState": "REGULAR", "regularMarketPrice": 3.0,
             "regularMarketPreviousClose": 2.0, "regularMarketChangePercent": 50.0, "regularMarketVolume": 5e6,
             "averageDailyVolume3Month": 5e5, "sharesOutstanding": 8e6, "fullExchangeName": "NasdaqCM"}
        x = srv.runner_quote(q)
        self.assertEqual(x["relVol"], 10.0)
        self.assertTrue(srv.runner_ok(x))
        self.assertFalse(srv.runner_ok(dict(x, exchange="Other OTC")))
        self.assertFalse(srv.runner_ok(dict(x, price=0.04)))
        self.assertFalse(srv.runner_ok(dict(x, changePct=4.0)))
        self.assertFalse(srv.runner_ok(dict(x, volume=1000)))
        self.assertFalse(srv.runner_ok(dict(x, type="WARRANT")))
        pre = srv.runner_quote(dict(q, marketState="PRE", preMarketPrice=4.0, preMarketChangePercent=33.3))
        self.assertEqual((pre["price"], pre["prev"], pre["changePct"]), (4.0, 3.0, 33.3))
        self.assertTrue(srv.runner_ok(dict(pre, volume=0)))  # pre-market volume is thin: no volume rule

    def test_score_rewards_the_checklist(self):
        hot = {"changePct": 60, "relVol": 25, "shares": 9e6, "price": 4, "news": [1], "levels": {"setup": "breakout"}}
        s, why = srv.runner_score(hot)
        self.assertEqual(s, 100)
        self.assertTrue(any("volume" in w for w in why))
        faded = dict(hot, levels={"setup": "faded"})
        self.assertLess(srv.runner_score(faded)[0], s)
        self.assertEqual(srv.runner_score({})[0], 0)

    def test_runners_end_to_end_offline(self):
        q = lambda sym, chg, vol: {"symbol": sym, "quoteType": "EQUITY", "marketState": "REGULAR", "regularMarketPrice": 3.3,
                                   "regularMarketPreviousClose": 2.0, "regularMarketChangePercent": chg, "regularMarketVolume": vol,
                                   "averageDailyVolume3Month": 1e5, "sharesOutstanding": 1e7, "fullExchangeName": "NasdaqCM"}
        lists = {"small_cap_gainers": [q("AAA", 65, 4e6), q("BBB", 3, 4e6)], "day_gainers": [q("AAA", 65, 4e6), q("CCC", 20, 1e6)]}
        rows = self.bars([2, 2.4, 2.8, 3.0, 3.2, 3.3])
        chart = {"meta": {"gmtoffset": self.GMT, "regularMarketPrice": 3.3, "chartPreviousClose": 2.0, "longName": "Mine Co"},
                 "timestamp": [x[0] for x in rows],
                 "indicators": {"quote": [{k: [x[i] for x in rows] for i, k in enumerate(("t", "open", "high", "low", "close", "volume")) if k != "t"}]}}
        old = (srv._screen, srv._chart, srv._rss)
        srv._screen = lambda scr: lists.get(scr, [])
        srv._chart = lambda sym, query, ttl: chart
        srv._rss = lambda sym: []
        srv.purge(lambda k: k[0] in ("runners", "news"))
        try:
            d = srv.runners(("ZZZ",))
        finally:
            srv._screen, srv._chart, srv._rss = old
            srv.purge(lambda k: k[0] in ("runners", "news"))
        syms = [x["symbol"] for x in d["rows"]]
        self.assertEqual(d["session"], "open")
        self.assertEqual(syms[0], "ZZZ")  # the user's own ticker comes first
        self.assertTrue(d["rows"][0]["mine"])
        self.assertEqual(d["rows"][0]["changePct"], 65.0)  # filled from the chart
        self.assertEqual(sorted(syms[1:]), ["AAA", "CCC"])  # BBB is up only 3%, AAA listed once
        self.assertEqual(syms.count("AAA"), 1)
        self.assertEqual(d["rows"][1]["symbol"], "AAA")  # bigger move and volume ranks first
        self.assertEqual(d["rows"][1]["levels"]["setup"], "breakout")


if __name__ == "__main__":
    unittest.main()
