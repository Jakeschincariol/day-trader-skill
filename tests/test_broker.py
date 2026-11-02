import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

ticket = load("trader-broker", "ticket")
check = load("trader-risk", "check")

CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
ORDERS_PATH = os.path.join(FIX, "trader-risk", "orders-tsla.json")
PLAN_PATH = os.path.join(FIX, "trader-budget", "plan-tsla.json")
NOW = "2026-10-19 10:15"
TODAY = "2026-10-19"
AAPL = {"symbol": "AAPL", "side": "buy", "notional": "1250", "type": "market", "time_in_force": "day"}
BATCH = ["AAPL", "AXP", "GOOGL", "KO", "BAC"]
TSLA_CALL = {"symbol": "TSLA", "side": "buy", "qty": "8", "type": "market", "time_in_force": "day",
             "order_class": "bracket", "take_profit_limit_price": "370.04", "stop_loss_stop_price": "358.32"}
TSLA_PLAIN = ("BUY 8 TSLA, market, good for today / stop-loss 358.32 / take-profit 370.04 / max loss about "
              "$46.88 if the stop fills at 358.32 (it can fill worse in a fast market)")


def tsla(**over):
    with open(ORDERS_PATH) as fh:
        o = json.load(fh)["orders"][0]
    o.update(over)
    return o


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ticket.main(argv)
    return code, out.getvalue(), err.getvalue()


class ExplicitYes(unittest.TestCase):
    def yes(self, reply, order=AAPL, batch=BATCH):
        return ticket.parse_yes(reply, order, batch)[0]

    def test_plain_yes_counts(self):
        for r in ("yes", "Yes.", "YES", "y", "yes place it", "Yes, buy it", "yes AAPL", "yes $1,250 of AAPL",
                  "yes 1250"):
            self.assertTrue(self.yes(r), r)

    def test_anything_else_does_not(self):
        for r in ("", "sure", "ok", "okay", "go", "do it", "yeah", "yep", "absolutely", "send it",
                  "yes to all", "yes, all of them", "yes to the rest", "yes both",
                  "yes AXP", "yes 1000", "yes but make it 1000", "yes?", "no", "not yes",
                  "yes, wait", "yes if it is under 340"):
            self.assertFalse(self.yes(r), r)

    def test_amount_must_match_this_order(self):
        sell = {"symbol": "KO", "side": "sell", "qty": "3", "type": "market", "time_in_force": "day"}
        self.assertTrue(self.yes("yes sell 3 KO", sell))
        self.assertFalse(self.yes("yes sell 4", sell))

    def test_a_bracket_yes(self):
        o = tsla()
        for r in ("yes", "yes 8 TSLA", "yes 358.32", "yes max loss 46.88", "yes target 370.04"):
            self.assertTrue(self.yes(r, o, ["TSLA"]), r)
        for r in ("yes 9", "yes 10 TSLA", "yes but stop at 357", "yes, stop 358.32", "yes AAPL", "sure"):
            self.assertFalse(self.yes(r, o, ["TSLA", "AAPL"]), r)


class TicketShape(unittest.TestCase):
    def test_tool_input_is_the_alpaca_call(self):
        o = dict(AAPL, why="from a list")
        self.assertEqual(ticket.tool_input(o), AAPL)
        self.assertEqual(ticket.tool_input({"symbol": "KO", "side": "buy", "qty": 3, "type": "limit",
                                            "limit_price": 89.5, "time_in_force": "day"}),
                         {"symbol": "KO", "side": "buy", "qty": "3", "type": "limit", "limit_price": "89.5",
                          "time_in_force": "day"})

    def test_the_bracket_call_leaves_out_why_and_plan(self):
        self.assertEqual(ticket.tool_input(tsla()), TSLA_CALL)
        self.assertEqual(ticket.fingerprint(tsla()), ticket.fingerprint(TSLA_CALL))

    def test_plain_english(self):
        self.assertEqual(ticket.plain(AAPL), "BUY $1,250 of AAPL, market order, good for today")
        self.assertEqual(ticket.plain({"symbol": "KO", "side": "sell", "qty": "1", "type": "limit",
                                       "limit_price": "95", "time_in_force": "gtc"}),
                         "SELL 1 share of KO, limit order at $95, good until canceled")
        self.assertEqual(ticket.plain(tsla()), TSLA_PLAIN)
        lim = tsla(type="limit", limit_price="364.00")
        self.assertEqual(ticket.plain(lim).split(" / ")[0], "BUY 8 TSLA, limit 364.00, good for today")
        self.assertEqual(ticket.max_loss(lim), (45.44, 358.32))
        no_plan = dict(TSLA_CALL)
        self.assertEqual(ticket.max_loss(no_plan), (None, 358.32))


class DesktopConfig(unittest.TestCase):
    def test_example_is_paper_with_placeholder_keys(self):
        with open(os.path.join(ROOT, "trader-broker", "claude_desktop_config.example.json")) as fh:
            server = json.load(fh)["mcpServers"]["alpaca"]
        self.assertEqual((server["command"], server["args"]), ("uvx", ["alpaca-mcp-server"]))
        self.assertEqual(server["env"]["ALPACA_PAPER_TRADE"], "true")
        for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
            self.assertIn("NEVER_IN_CHAT", server["env"][k])


class Flow(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.orders = os.path.join(self.d, "orders.json")
        shutil.copy(ORDERS_PATH, self.orders)
        self.cfg = os.path.join(self.d, "config.json")
        shutil.copy(CFG_PATH, self.cfg)
        self.risk = os.path.join(self.d, "state", "risk.json")
        self.state = os.path.join(self.d, "state", "broker.json")
        self.pf = os.path.join(self.d, "portfolio.json")
        self.none = os.path.join(self.d, "none")

    def tearDown(self):
        shutil.rmtree(self.d)

    def args(self, *extra, **kw):
        return list(extra) + ["--orders", self.orders, "--config", self.cfg, "--risk", self.risk,
                              "--state", self.state, "--now", kw.get("now", NOW)]

    def run_risk(self, now=NOW):
        with redirect_stdout(io.StringIO()):
            return check.main(["--orders", self.orders, "--config", self.cfg, "--portfolio", self.pf,
                               "--prices", self.none, "--state", self.state, "--now", now, "--out", self.risk])

    def state_doc(self):
        with open(self.state) as fh:
            return json.load(fh)

    def test_nothing_is_ready_before_the_risk_check(self):
        code, text, _ = run(self.args("show"))
        self.assertEqual(code, 1)
        self.assertIn("NOT READY", text)
        self.assertNotIn("Reply \"yes\"", text)
        code, _, err = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 1)
        self.assertIn("not ready", err)

    def test_the_full_two_yes_flow(self):
        self.assertEqual(self.run_risk(), 0)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertEqual(code, 0)
        self.assertIn("ORDER 1 of 1, PAPER account, Alpaca", text)
        for part in TSLA_PLAIN.split(" / "):
            self.assertIn("  " + part + "\n", text)
        self.assertIn("READY: trader-risk PASS", text)
        self.assertIn('"order_class": "bracket"', text)
        self.assertIn('"stop_loss_stop_price": "358.32"', text)
        self.assertNotIn('"plan"', text)
        self.assertNotIn('"why"', text)
        self.assertIn("Allow once", text)

        code, text, _ = run(self.args("approve", "--index", "1", "--reply", "sure"))
        self.assertEqual(code, 1)
        self.assertIn("Not recorded", text)
        self.assertFalse(os.path.exists(self.state))

        code, text, _ = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 0)
        self.assertIn("place_stock_order", text)
        self.assertEqual(json.loads(text[text.index("{"):text.rindex("}") + 1]), TSLA_CALL)
        code, _, err = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 1)
        self.assertIn("APPROVED", err)

        code, text, _ = run(self.args("result", "--index", "1", "--status", "placed", "--broker-id", "abc123",
                                      "--filled-qty", "8", "--filled-price", "364.20", "--portfolio", self.pf,
                                      now="2026-10-19 10:16"))
        self.assertEqual(code, 0)
        st = self.state_doc()
        self.assertEqual([r["status"] for r in st["orders"]], ["approved", "placed", "filled"])
        appr, plc = st["orders"][0], st["orders"][1]
        self.assertEqual((appr["reply"], appr["kind"], appr["max_loss"], appr["date"]), ("yes", "entry", 46.88, TODAY))
        self.assertEqual(appr["at"], "2026-10-19T10:15:00-04:00")
        self.assertEqual((plc["broker_order_id"], plc["max_loss"], plc["kind"]), ("abc123", 46.88, "entry"))
        with open(self.pf) as fh:
            pf = json.load(fh)
        self.assertEqual(pf["cash"], 2086.4)
        self.assertEqual(pf["positions"][0]["shares"], 8)

        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("DONE: filled", text)                  # the fill is linked to this exact order
        self.assertEqual(code, 1)
        code, text, _ = run(["log", "--state", self.state, "--now", NOW])
        self.assertIn("1 placed today", text)
        self.assertIn("max loss $46.88", text)

        # trader-risk now counts it: a second TSLA buy today is a duplicate, and $46.88 is used
        res = check.check([tsla()], {"budget": 5000}, state=st, now=check.parse_now("2026-10-19 10:30"))
        self.assertIn("already placed today", " ".join(res["results"][0]["reasons"]))
        self.assertEqual((res["today"]["entries_placed"], res["today"]["loss_at_risk"]), (1, 46.88))

    def test_flatten_by_the_close(self):
        self.run_risk()
        run(self.args("approve", "--index", "1", "--reply", "yes"))
        run(self.args("result", "--index", "1", "--status", "placed", "--broker-id", "abc",
                      "--filled-qty", "8", "--filled-price", "364.20", "--portfolio", self.pf))
        late = "2026-10-19 15:55"
        code, text, _ = run(["flatten", "--symbol", "TSLA", "--orders", self.orders, "--portfolio", self.pf,
                             "--plan", PLAN_PATH, "--config", self.cfg, "--now", late])
        self.assertEqual(code, 0)
        self.assertIn("SELL 8 shares of TSLA, market order, good for today (flat by 15:55 New York)", text)
        self.assertIn("replaced 1 earlier proposal", text)
        self.assertIn("cancel_order_by_id", text)
        with open(self.orders) as fh:
            doc = json.load(fh)
        self.assertEqual(ticket.tool_input(doc["orders"][0]),
                         {"symbol": "TSLA", "side": "sell", "qty": "8", "type": "market", "time_in_force": "day"})
        self.assertEqual(self.run_risk(now=late), 0)       # after the 15:30 entry cutoff: an exit still passes
        with open(self.risk) as fh:
            self.assertEqual(json.load(fh)["results"][0]["kind"], "exit")
        code, text, _ = run(self.args("show", now=late))
        self.assertEqual(code, 0)
        self.assertIn("READY", text)
        self.assertEqual(run(self.args("approve", "--index", "1", "--reply", "yes sell 8 TSLA", now=late))[0], 0)
        code, _, err = run(self.args("result", "--index", "1", "--status", "placed", "--filled-qty", "8",
                                     "--filled-price", "366.10", "--portfolio", self.pf, now="2026-10-19 15:56"))
        self.assertEqual(code, 1)                    # placed needs the broker's order id
        self.assertIn("broker order id is required", err)
        code, _, err = run(self.args("result", "--index", "1", "--status", "placed", "--broker-id", "def456",
                                     "--filled-qty", "8", "--filled-price", "366.10", "--portfolio", self.pf,
                                     now="2026-10-19 15:56"))
        self.assertEqual(code, 0, err)
        with open(self.pf) as fh:
            pf = json.load(fh)
        self.assertEqual((pf["cash"], pf["positions"]), (5015.2, []))
        self.assertEqual(check.day_trades(self.state_doc(), TODAY), (1, ["2026-10-19 TSLA"]))
        code, _, err = run(["flatten", "--symbol", "TSLA", "--orders", self.orders, "--portfolio", self.pf,
                            "--now", late])
        self.assertEqual(code, 1)
        self.assertIn("nothing to flatten", err)

    def test_flatten_with_the_broker_qty(self):
        code, text, _ = run(["flatten", "--symbol", "tsla", "--qty", "8", "--orders", self.orders,
                             "--portfolio", self.none, "--plan", self.none, "--config", self.cfg, "--now", NOW])
        self.assertEqual(code, 0)
        self.assertNotIn("Check it against get_open_position", text)
        self.assertEqual(run(["flatten", "--symbol", "TSLA", "--qty", "0", "--orders", self.orders])[0], 1)

    def test_an_edited_order_is_not_ready(self):
        self.run_risk()
        with open(self.orders) as fh:
            doc = json.load(fh)
        doc["orders"][0]["qty"] = "9"
        with open(self.orders, "w") as fh:
            json.dump(doc, fh)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertEqual(code, 1)
        self.assertIn("was not in the last risk check", text)

    def test_yesterdays_check_does_not_count(self):
        self.run_risk(now="2026-10-16 10:15")
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("not today", text)

    def test_blocked_orders_are_never_ready(self):
        self.assertEqual(self.run_risk(now="2026-10-19 09:40"), 1)
        code, text, _ = run(self.args("show", "--index", "1", now="2026-10-19 09:40"))
        self.assertIn("BLOCKED by trader-risk: window: no new entries before 09:45", text)
        code, _, _ = run(self.args("approve", "--index", "1", "--reply", "yes", now="2026-10-19 09:40"))
        self.assertEqual(code, 1)

    def test_result_needs_an_approval_and_decline_is_logged(self):
        self.run_risk()
        code, _, err = run(self.args("result", "--index", "1", "--status", "placed"))
        self.assertEqual(code, 1)
        self.assertIn("no yes recorded", err)
        code, text, _ = run(self.args("decline", "--index", "1", "--reply", "no thanks"))
        self.assertEqual(code, 0)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("DONE: declined", text)

    def test_ibkr_tickets_send_the_final_yes_to_ibkr(self):
        with open(self.cfg) as fh:
            c = json.load(fh)
        c["broker"] = "ibkr"
        with open(self.cfg, "w") as fh:
            json.dump(c, fh)
        self.run_risk()
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("Interactive Brokers", text)
        self.assertIn("after you approve it there", text)
        self.assertNotIn("place_stock_order", text)

    def test_fill_sell_relieves_the_oldest_lot(self):
        pf = {"cash": 0, "positions": [{"ticker": "KO", "shares": 3, "lots": [
            {"id": "KO-1", "date": "2025-01-02", "shares": 2, "cost": 120.0},
            {"id": "KO-2", "date": "2026-01-02", "shares": 1, "cost": 70.0}]}]}
        with open(self.pf, "w") as fh:
            json.dump(pf, fh)
        write_state(self.state, ko_sell_records("ko-sell-1", "3"))
        code, text, err = run(["fill", "--broker-id", "ko-sell-1", "--symbol", "KO", "--side", "sell", "--qty", "2.5",
                               "--price", "90", "--date", TODAY, "--portfolio", self.pf, "--config", self.cfg,
                               "--state", self.state])
        self.assertEqual(code, 0, err)
        with open(self.pf) as fh:
            pf = json.load(fh)
        self.assertEqual(pf["cash"], 225.0)
        lots = pf["positions"][0]["lots"]
        self.assertEqual([l["id"] for l in lots], ["KO-2"])
        self.assertEqual(lots[0]["shares"], 0.5)
        self.assertEqual(lots[0]["cost"], 35.0)
        self.assertEqual(self.state_doc()["orders"][-1]["status"], "filled")
        code, _, err = run(["fill", "--broker-id", "ko-sell-1", "--symbol", "KO", "--side", "sell", "--qty", "5",
                            "--price", "90", "--portfolio", self.pf, "--config", self.cfg, "--state", self.state])
        self.assertEqual(code, 1)
        self.assertIn("more than the 3 shares of order ko-sell-1", err)
        self.assertNotIn("Traceback", err)


def write_state(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"orders": records}, fh)


def ko_sell_records(broker_id, qty, approved=True, side="sell", bracket=False, kind="exit"):
    base = {"date": TODAY, "index": 1, "fingerprint": "fp-" + broker_id, "symbol": "KO", "side": side, "qty": qty,
            "kind": kind, "bracket": bracket, "plain": "%s %s KO" % (side.upper(), qty)}
    out = []
    if approved:
        out.append(dict(base, at=TODAY + "T10:00:00-04:00", status="approved", reply="yes"))
    out.append(dict(base, at=TODAY + "T10:01:00-04:00", status="placed", broker_order_id=broker_id))
    return out


class FillsAreBound(unittest.TestCase):
    """Fix 4: a fill only changes the portfolio when it belongs to an approved, placed, identified order."""

    PF = {"cash": 1000.0, "positions": []}

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.pf = os.path.join(self.d, "portfolio.json")
        self.state = os.path.join(self.d, "state", "broker.json")
        self.cfg = os.path.join(self.d, "none.json")
        with open(self.pf, "w") as fh:
            json.dump(self.PF, fh)

    def tearDown(self):
        shutil.rmtree(self.d)

    def fill(self, *extra, **kw):
        argv = ["fill", "--symbol", kw.get("symbol", "KO"), "--side", kw.get("side", "buy"),
                "--qty=" + kw.get("qty", "2"), "--price=" + kw.get("price", "90"), "--date", TODAY, "--portfolio", self.pf,
                "--config", self.cfg, "--state", self.state] + list(extra)
        return run(argv)

    def pf_doc(self):
        with open(self.pf) as fh:
            return json.load(fh)

    def buy_order(self, bid="ko-buy-1", qty="2", **kw):
        write_state(self.state, ko_sell_records(bid, qty, side="buy", kind="entry", **kw))

    def assert_untouched(self):
        self.assertEqual(self.pf_doc(), self.PF)

    def test_a_fill_without_an_order(self):
        code, _, err = self.fill("--broker-id", "nope-123")
        self.assertEqual(code, 1)
        self.assertIn("no order was recorded as placed with broker id nope-123", err)
        self.assert_untouched()

    def test_a_fill_of_an_order_that_was_not_approved(self):
        self.buy_order(approved=False)
        code, _, err = self.fill("--broker-id", "ko-buy-1")
        self.assertEqual(code, 1)
        self.assertIn("has no recorded yes", err)
        self.assert_untouched()

    def test_a_fill_without_a_broker_order_id(self):
        self.buy_order()
        for bid in ("", "x", "bad id with spaces"):
            code, _, err = self.fill("--broker-id", bid)
            self.assertEqual(code, 1, bid)
            self.assertIn("broker order id is required", err)
        with self.assertRaises(SystemExit):          # argparse: --broker-id is required
            run(["fill", "--symbol", "KO", "--side", "buy", "--qty", "2", "--price", "90",
                 "--portfolio", self.pf, "--state", self.state])
        self.assert_untouched()

    def test_a_fill_that_does_not_match_the_order(self):
        self.buy_order()
        for kw, why in (({"symbol": "PEP"}, "is for KO"), ({"side": "sell"}, "is a buy"),
                        ({"qty": "3"}, "more than the 2 shares")):
            code, _, err = self.fill("--broker-id", "ko-buy-1", **kw)
            self.assertEqual(code, 1, kw)
            self.assertIn(why, err)
        self.assert_untouched()

    def test_nan_infinity_and_bad_numbers(self):
        self.buy_order()
        for field in ("qty", "price"):
            for bad in ("NaN", "nan", "Infinity", "-Infinity", "inf", "0", "-2", "two"):
                code, _, err = self.fill("--broker-id", "ko-buy-1", **{field: bad})
                self.assertEqual(code, 1, (field, bad))
                self.assertIn("must be a finite number above 0", err)
        self.assert_untouched()

    def test_a_duplicate_fill_and_an_idempotent_retry(self):
        self.buy_order(qty="4")
        code, _, err = self.fill("--broker-id", "ko-buy-1", "--fill-id", "f1")
        self.assertEqual(code, 0, err)
        once = self.pf_doc()
        self.assertEqual((once["cash"], once["positions"][0]["shares"]), (820.0, 2))
        code, text, _ = self.fill("--broker-id", "ko-buy-1", "--fill-id", "f1")     # the same fill again
        self.assertEqual(code, 0)
        self.assertIn("Already recorded", text)
        self.assertEqual(self.pf_doc(), once)
        with open(self.state) as fh:
            self.assertEqual(sum(1 for r in json.load(fh)["orders"] if r["status"] == "filled"), 1)
        code, _, err = self.fill("--broker-id", "ko-buy-1", "--fill-id", "f1", price="91")
        self.assertEqual(code, 1)                    # same fill id, different numbers
        self.assertIn("already recorded", err)
        self.assertEqual(self.pf_doc(), once)

    def test_a_failed_portfolio_write_leaves_nothing_half_done(self):
        self.buy_order()
        before = open(self.state).read()
        real = ticket.write_json

        def failing(path, data):
            if path == self.pf:
                raise ticket.TicketError("could not write %s: disk full" % path)
            return real(path, data)

        ticket.write_json = failing
        try:
            code, _, err = self.fill("--broker-id", "ko-buy-1")
        finally:
            ticket.write_json = real
        self.assertEqual(code, 1)
        self.assertIn("disk full", err)
        self.assert_untouched()
        self.assertEqual(open(self.state).read(), before)          # no "filled" record without the portfolio

    def test_a_failed_log_write_is_safe_to_retry(self):
        self.buy_order()
        real = ticket.write_json

        def failing(path, data):
            if path == self.state:
                raise ticket.TicketError("could not write %s: disk full" % path)
            return real(path, data)

        ticket.write_json = failing
        try:
            self.assertEqual(self.fill("--broker-id", "ko-buy-1")[0], 1)
        finally:
            ticket.write_json = real
        after_first = self.pf_doc()
        self.assertEqual(after_first["cash"], 820.0)
        code, _, err = self.fill("--broker-id", "ko-buy-1")          # the retry logs it, without a second buy
        self.assertEqual(code, 0, err)
        self.assertEqual(self.pf_doc(), after_first)

    def test_bracket_legs_cannot_sell_more_than_the_entry_filled(self):
        self.buy_order(qty="2", bracket=True)
        self.assertEqual(self.fill("--broker-id", "ko-buy-1", qty="1")[0], 0)
        code, _, err = self.fill("--broker-id", "ko-buy-1", "--leg", "stop", side="sell", qty="2", price="85")
        self.assertEqual(code, 1)
        self.assertIn("more than the 1 shares the entry filled", err)
        code, _, err = self.fill("--broker-id", "ko-buy-1", qty="0.5")
        self.assertIn("must be whole shares", err)
        code, _, err = self.fill("--broker-id", "ko-buy-1", "--leg", "stop", side="sell", qty="1", price="85")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.pf_doc()["positions"], [])

    def test_result_placed_needs_a_broker_id_and_a_failed_fill_keeps_it_unplaced(self):
        d = self.d
        orders = os.path.join(d, "orders.json")
        shutil.copy(ORDERS_PATH, orders)
        risk = os.path.join(d, "risk.json")
        cfg = os.path.join(d, "config.json")
        shutil.copy(CFG_PATH, cfg)
        with redirect_stdout(io.StringIO()):
            check.main(["--orders", orders, "--config", cfg, "--portfolio", self.cfg, "--prices", self.cfg,
                        "--state", self.state, "--now", NOW, "--out", risk])
        common = ["--orders", orders, "--config", cfg, "--risk", risk, "--state", self.state, "--now", NOW]
        self.assertEqual(run(["approve", "--index", "1", "--reply", "yes"] + common)[0], 0)
        code, _, err = run(["result", "--index", "1", "--status", "placed"] + common)
        self.assertEqual(code, 1)
        self.assertIn("broker order id is required", err)
        code, _, err = run(["result", "--index", "1", "--status", "placed", "--broker-id", "abc123",
                            "--filled-qty", "9", "--filled-price", "364.20", "--portfolio", self.pf] + common)
        self.assertEqual(code, 1)                    # 9 shares on an 8-share order
        self.assertIn("more than the 8 shares", err)
        with open(self.state) as fh:
            self.assertEqual([r["status"] for r in json.load(fh)["orders"]], ["approved"])
        self.assert_untouched()

    def test_flatten_never_sells_more_than_the_position(self):
        with open(self.pf, "w") as fh:
            json.dump({"cash": 0, "positions": [{"ticker": "KO", "shares": 3}]}, fh)
        orders = os.path.join(self.d, "orders.json")
        code, _, err = run(["flatten", "--symbol", "KO", "--qty", "5", "--orders", orders, "--portfolio", self.pf,
                            "--plan", self.cfg, "--config", self.cfg, "--now", NOW])
        self.assertEqual(code, 1)
        self.assertIn("more than the 3 KO shares", err)
        self.assertFalse(os.path.exists(orders))
        for bad in ("NaN", "inf", "-3"):
            self.assertEqual(run(["flatten", "--symbol", "KO", "--qty=" + bad, "--orders", orders, "--portfolio",
                                  self.pf, "--plan", self.cfg, "--config", self.cfg, "--now", NOW])[0], 1, bad)
        code, text, _ = run(["flatten", "--symbol", "KO", "--qty", "3", "--orders", orders, "--portfolio", self.pf,
                             "--plan", self.cfg, "--config", self.cfg, "--now", NOW])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
