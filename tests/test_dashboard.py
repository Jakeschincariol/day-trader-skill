"""Offline tests for the web dashboard (dashboard/server.py)."""

import http.client
import json
import os
import tempfile
import threading
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
        st, _, body = self.req("/api/phone", {"Cookie": "td_key=" + "t" * 32})
        self.assertEqual(st, 403)
        self.assertNotIn(b"tttt", body)


if __name__ == "__main__":
    unittest.main()
