#!/usr/bin/env python3
"""Order tickets and the decision log for trader-broker. Standard library only.

This tool never talks to a broker and never places anything. It does its
work around the one moment that matters, your yes:

  show      renders each proposed order as a plain-English ticket plus the
            exact JSON Claude will send to Alpaca's place_stock_order tool.
            A bracket order shows its stop-loss, take-profit and the max loss
            at the stop. An order is READY only if trader-risk passed THIS
            exact order today (matched by fingerprint) and nobody has decided
            on it yet.
  approve   records your explicit yes for ONE order, with your reply word for
            word. It refuses "yes to all", "sure", "ok", a yes that names a
            different stock or amount, and any order that is not READY.
  decline   records a no.
  result    records what happened after the Allow once / Deny card:
            placed (with the broker's order id), denied, or failed.
  fill      records a fill in trader/portfolio.json (cash and shares).
  flatten   builds a sell ticket that closes a symbol's open position by
            flat_by. It still goes through trader-risk and your yes.
  log       prints today's decisions.
  slippage  fill quality: each fill against the price you expected (the
            plan's entry, stop or target, a limit, or --expected), in cents
            a share, basis points and R, with averages by kind. Positive =
            it cost you. The Time Machine's --slippage auto reads it.

    python3 ticket.py show                    # every order, READY or not
    python3 ticket.py show --index 1 --json   # one ticket as JSON
    python3 ticket.py approve --index 1 --reply "yes"
    python3 ticket.py result --index 1 --status placed --broker-id 61e6...
    python3 ticket.py fill --symbol TSLA --side buy --qty 8 --price 364.20
    python3 ticket.py flatten --symbol TSLA --qty 8
    python3 ticket.py fill --symbol TSLA --side sell --qty 8 --price 358.10 --kind stop
    python3 ticket.py log
    python3 ticket.py slippage --all

Everything is written to trader/state/broker.json (append only). Dates are
New York dates; --now "2026-10-19 10:15" pins the clock.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

ALPACA_FIELDS = ("symbol", "side", "qty", "notional", "type", "time_in_force", "limit_price",
                 "stop_price", "trail_price", "trail_percent", "extended_hours", "client_order_id",
                 "order_class", "take_profit_limit_price", "stop_loss_stop_price",
                 "stop_loss_limit_price", "advanced_instructions")
STRING_FIELDS = ("qty", "notional", "limit_price", "stop_price", "trail_price", "trail_percent",
                 "take_profit_limit_price", "stop_loss_stop_price", "stop_loss_limit_price")
TIF_WORDS = {"day": "good for today", "gtc": "good until canceled", "opg": "at the open",
             "cls": "at the close", "ioc": "immediate or cancel", "fok": "fill or kill"}
YES_WORDS = ("yes", "y")
BATCH_WORDS = {"all", "every", "everything", "rest", "remaining", "them", "both", "batch", "each"}
DOUBT_WORDS = {"no", "not", "dont", "don't", "wait", "cancel", "stop", "but", "maybe", "later",
               "hold", "unless", "if"}


class TicketError(Exception):
    pass


# ---------------------------------------------------------------- time (New York, no tz files)

def _nth_sunday(year, month, n):
    d = datetime.date(year, month, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def eastern_offset(utc):
    """Hours from UTC for New York: -4 in daylight time, -5 otherwise.
    DST runs from 2:00 a.m. on the second Sunday of March to 2:00 a.m. on the
    first Sunday of November (US rule since 2007)."""
    y = utc.year
    start = datetime.datetime.combine(_nth_sunday(y, 3, 2), datetime.time(7, 0))   # 2:00 EST
    end = datetime.datetime.combine(_nth_sunday(y, 11, 1), datetime.time(6, 0))    # 2:00 EDT
    naive = utc.replace(tzinfo=None)
    return -4 if start <= naive < end else -5


def to_eastern(utc):
    return utc.replace(tzinfo=None) + datetime.timedelta(hours=eastern_offset(utc))


def eastern_to_utc(local):
    for off in (-4, -5):
        utc = local - datetime.timedelta(hours=off)
        if eastern_offset(utc) == off:
            return utc
    return local + datetime.timedelta(hours=5)


def parse_now(text):
    """ISO time -> naive UTC. A time without an offset is taken as New York time."""
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = text.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(t)
    except ValueError:
        raise TicketError("--now wants a time like \"2026-10-19 10:15\" (New York) or ...Z (UTC)")
    if dt.tzinfo is None:
        return eastern_to_utc(dt)
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def ny_iso(now_utc):
    """naive UTC -> "2026-10-19T10:15:00-04:00" (New York wall clock with its offset)."""
    off = eastern_offset(now_utc)
    return "%s%+03d:00" % (to_eastern(now_utc).replace(microsecond=0).isoformat(), off)


# ---------------------------------------------------------------- files

def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise TicketError("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise TicketError("%s is not valid JSON: %s" % (path, e))


def write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def rec_day(rec):
    """The trading day a decision belongs to: its "date" (the day it was made under), else the day of "at"."""
    return str(rec.get("date") or str(rec.get("at", ""))[:10])


# ---------------------------------------------------------------- the order

def fingerprint(order):
    """Same function as trader-risk/check.py: identifies the exact order."""
    core = {k: order[k] for k in ALPACA_FIELDS if k in order and order[k] is not None}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _str_num(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        f = float(v)
        return str(int(f)) if f == int(f) else repr(f)
    return str(v)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def tool_input(order):
    """The exact arguments for place_stock_order: Alpaca's parameter names,
    numbers as strings (its signature types qty, notional and prices as str).
    "why" and "plan" are ours and are never sent."""
    out = {}
    for k in ALPACA_FIELDS:
        if k in order and order[k] is not None:
            out[k] = _str_num(order[k]) if k in STRING_FIELDS else order[k]
    return out


def _money(v):
    f = float(v)
    s = "{:,.2f}".format(f)
    return "$" + (s[:-3] if s.endswith(".00") else s)


def _p(v):
    return "%.2f" % float(v)


def is_bracket(order):
    oc = str(order.get("order_class") or "").lower()
    legs = order.get("take_profit_limit_price") is not None or order.get("stop_loss_stop_price") is not None
    return oc == "bracket" or (not oc and legs)


def max_loss(order):
    """(dollars, stop) lost if the stop fills exactly at the stop, or (None, stop)."""
    stop = _f(order.get("stop_loss_stop_price")) or _f((order.get("plan") or {}).get("stop"))
    q = _f(order.get("qty"))
    if not stop or not q:
        return None, stop
    plan = order.get("plan") or {}
    if str(order.get("type", "market")) == "limit" and _f(order.get("limit_price")):
        entry = _f(order["limit_price"])
    elif _f(plan.get("max_loss")) is not None:
        return round(_f(plan["max_loss"]), 2), stop
    else:
        entry = _f(plan.get("entry"))
    if not entry:
        return None, stop
    risk = abs(entry - stop)
    return round(q * int(round(risk * 100)) / 100.0, 2), stop


def plain_parts(order):
    """The ticket in plain words, one part per line."""
    side = str(order.get("side", "")).upper()
    sym = order.get("symbol", "?")
    typ = str(order.get("type", "market"))
    tif = TIF_WORDS.get(str(order.get("time_in_force", "day")), order.get("time_in_force"))
    if is_bracket(order):
        how = "limit %s" % _p(order["limit_price"]) if typ == "limit" and order.get("limit_price") else typ
        parts = ["%s %s %s, %s, %s" % (side, _str_num(order.get("qty")), sym, how, tif)]
        if order.get("stop_loss_stop_price") is not None:
            leg = "stop-loss %s" % _p(order["stop_loss_stop_price"])
            if order.get("stop_loss_limit_price") is not None:
                leg += " (limit %s)" % _p(order["stop_loss_limit_price"])
            parts.append(leg)
        if order.get("take_profit_limit_price") is not None:
            parts.append("take-profit %s" % _p(order["take_profit_limit_price"]))
        loss, stop = max_loss(order)
        if loss is not None:
            parts.append("max loss about %s if the stop fills at %s (it can fill worse in a fast market)"
                         % (_money(loss), _p(stop)))
        return parts
    if order.get("notional") is not None:
        what = "%s of %s" % (_money(order["notional"]), sym)
    else:
        q = _str_num(order.get("qty"))
        what = "%s share%s of %s" % (q, "" if q == "1" else "s", sym)
    if typ == "limit":
        how = "limit order at %s" % _money(order.get("limit_price"))
    elif typ == "stop":
        how = "stop order at %s" % _money(order.get("stop_price"))
    elif typ == "stop_limit":
        how = "stop %s, limit %s" % (_money(order.get("stop_price")), _money(order.get("limit_price")))
    else:
        how = "%s order" % typ.replace("_", " ")
    return ["%s %s, %s, %s" % (side, what, how, tif)]


def plain(order):
    """BUY $1,250 of AAPL, market order, good for today
    BUY 8 TSLA, market, good for today / stop-loss 358.32 / take-profit 370.04 / max loss about $46.88 ..."""
    return " / ".join(plain_parts(order))


def amount_numbers(order):
    nums = []
    for k in ("notional", "qty", "limit_price", "stop_loss_stop_price", "take_profit_limit_price",
              "stop_loss_limit_price"):
        if order.get(k) is not None:
            v = _f(order[k])
            if v is not None:
                nums.append(v)
    loss, _ = max_loss(order)
    if loss is not None:
        nums.append(loss)
    return nums


def parse_yes(reply, order, batch_symbols=()):
    """Is this reply an explicit yes for THIS one order? Returns (ok, why)."""
    raw = (reply or "").strip()
    if not raw:
        return False, "the reply is empty"
    if "?" in raw:
        return False, "the reply is a question, not a yes"
    words = re.findall(r"[a-z']+", raw.lower())
    if not words or words[0] not in YES_WORDS:
        return False, "only a reply that starts with \"yes\" counts (not ok, sure, go, do it)"
    if BATCH_WORDS & set(words):
        return False, "a yes covers one order at a time, not a batch"
    if DOUBT_WORDS & set(words[1:]):
        return False, "the reply has a condition or a doubt in it; ask again"
    sym = str(order.get("symbol", "")).upper()
    tokens = set(re.findall(r"[A-Z][A-Z.\-]{0,6}", raw.upper()))
    others = {s.upper() for s in batch_symbols} - {sym}
    named = tokens & others
    if named:
        return False, "the reply names %s, but this order is for %s" % (", ".join(sorted(named)), sym)
    nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", raw)]
    if nums:
        want = amount_numbers(order)
        if not any(abs(n - w) < 0.005 for n in nums for w in want):
            return False, "the reply says %s, but this order is %s" % (
                ", ".join(_str_num(n) for n in nums), plain(order))
    return True, "explicit yes for %s" % plain(order)


# ---------------------------------------------------------------- state

def load_state(path):
    return read_json(path, "broker state", required=False) or {"orders": []}


def latest(state, fp, today):
    """The latest decision recorded today for this fingerprint, or None."""
    found = None
    for rec in state.get("orders", []):
        if rec.get("fingerprint") == fp and rec_day(rec) == today:
            found = rec
    return found


def risk_verdict(risk, fp, today):
    if not risk:
        return None, "trader-risk has not checked these orders (run check.py)"
    if risk.get("date") != today:
        return None, "the risk check is from %s, not today; run check.py again" % risk.get("date")
    for r in risk.get("results", []):
        if r.get("fingerprint") == fp:
            return r, None
    return None, "this exact order was not in the last risk check (it changed or is new); run check.py again"


def status_of(order, risk, state, today):
    """(ready, label, risk_result)"""
    fp = fingerprint(order)
    rv, why = risk_verdict(risk, fp, today)
    if rv is None:
        return False, "NOT READY: " + why, None
    if rv.get("verdict") != "PASS":
        return False, "BLOCKED by trader-risk: " + "; ".join(rv.get("reasons", [])), rv
    rec = latest(state, fp, today)
    if rec:
        st = rec.get("status")
        if st == "approved":
            return False, "APPROVED by you at %s, waiting for the place_stock_order call" % rec.get("at"), rv
        return False, "DONE: %s at %s" % (st, rec.get("at")), rv
    return True, "READY: trader-risk PASS, waiting for your yes", rv


def kind_of(order, rv):
    """entry or exit, as trader-risk saw it (older checks: a buy is an entry)."""
    if rv and rv.get("kind"):
        return rv["kind"]
    return "entry" if str(order.get("side", "")).lower() == "buy" else "exit"


# ---------------------------------------------------------------- rendering

def render(order, idx, total, cfg, risk, state, today):
    ready, label, rv = status_of(order, risk, state, today)
    broker = str(cfg.get("broker", "alpaca")).lower()
    paper = cfg.get("paper", True)
    acct = "PAPER account" if paper else "LIVE ACCOUNT, REAL MONEY"
    lines = ["ORDER %d of %d, %s, %s" % (idx, total, acct, "Interactive Brokers" if broker == "ibkr" else "Alpaca")]
    for part in plain_parts(order):
        lines.append("  " + part)
    if order.get("why"):
        lines.append("  why: " + order["why"])
    lines.append("  " + label)
    for w in (rv or {}).get("warnings", []):
        lines.append("  note: " + w)
    if broker == "ibkr":
        lines.append("  Claude drafts this with the Interactive Brokers connector. IBKR sends it to your")
        lines.append("  IBKR account, and it only goes to the market after you approve it there.")
    else:
        lines.append("  Claude will call place_stock_order with exactly:")
        for l in json.dumps(tool_input(order), indent=2).splitlines():
            lines.append("    " + l)
        if is_bracket(order):
            lines.append("  Alpaca places the entry, then the stop-loss and the take-profit as two orders")
            lines.append("  that cancel each other: when one fills, the other is canceled.")
    if ready:
        lines.append("  Reply \"yes\" to place this one order, or \"no\" to skip it.")
        if broker != "ibkr":
            lines.append("  Claude's own card then asks again: Allow once places it, Deny stops it.")
    return "\n".join(lines), ready


def ticket_json(order, idx, cfg, risk, state, today):
    ready, label, rv = status_of(order, risk, state, today)
    loss, stop = max_loss(order)
    return {"index": idx, "ready": ready, "status": label, "plain": plain(order),
            "fingerprint": fingerprint(order), "paper": bool(cfg.get("paper", True)),
            "broker": cfg.get("broker", "alpaca"), "tool": "place_stock_order",
            "tool_input": tool_input(order), "why": order.get("why", ""),
            "bracket": is_bracket(order), "max_loss": loss, "stop": stop}


# ---------------------------------------------------------------- fills -> portfolio

def apply_fill(portfolio_path, cfg, symbol, side, qty, price, date):
    """Record a filled order in trader/portfolio.json: cash and shares, with a
    cost-basis lot per buy (oldest lots are relieved first on a sell)."""
    pf = read_json(portfolio_path, "portfolio", required=False)
    if pf is None:
        budget = cfg.get("budget")
        if not budget:
            raise TicketError("no %s yet and no budget in the config to start it from" % portfolio_path)
        pf = {"cash": float(budget), "positions": []}
    symbol = symbol.upper()
    qty, price = float(qty), float(price)
    if qty <= 0 or price <= 0:
        raise TicketError("a fill needs a positive qty and price")
    cost = round(qty * price, 2)
    pos = None
    for p in pf.setdefault("positions", []):
        if str(p.get("ticker", "")).upper() == symbol:
            pos = p
    if side == "buy":
        if pos is None:
            pos = {"ticker": symbol, "shares": 0.0, "lots": []}
            pf["positions"].append(pos)
        lots = pos.setdefault("lots", [])
        lots.append({"id": "%s-%d" % (symbol, len(lots) + 1), "date": date, "shares": qty, "cost": cost})
        pos["shares"] = round(float(pos.get("shares", 0)) + qty, 6)
        pf["cash"] = round(float(pf.get("cash", 0)) - cost, 2)
    else:
        if pos is None or float(pos.get("shares", 0)) + 1e-9 < qty:
            raise TicketError("cannot record selling %s %s: the portfolio holds %s"
                              % (_str_num(qty), symbol, pos.get("shares", 0) if pos else 0))
        left = qty
        for lot in sorted(pos.get("lots", []), key=lambda l: l.get("date", "")):
            if left <= 1e-9:
                break
            take = min(left, float(lot["shares"]))
            per = float(lot["cost"]) / float(lot["shares"]) if float(lot["shares"]) else 0
            lot["cost"] = round(float(lot["cost"]) - per * take, 2)
            lot["shares"] = round(float(lot["shares"]) - take, 6)
            left -= take
        pos["lots"] = [l for l in pos.get("lots", []) if float(l["shares"]) > 1e-9]
        pos["shares"] = round(float(pos["shares"]) - qty, 6)
        if pos["shares"] <= 1e-9:
            pf["positions"].remove(pos)
        pf["cash"] = round(float(pf.get("cash", 0)) + cost, 2)
    write_json(portfolio_path, pf)
    return pf


def slippage(side, expected, price, qty, risk=None):
    """How much worse than expected a fill was. Positive = it cost you (a buy above,
    or a sell below, the expected price); negative = price improvement."""
    expected, price, qty = float(expected), float(price), float(qty)
    per = (price - expected) if side == "buy" else (expected - price)
    out = {"per_share": round(per, 4), "bps": round(10000.0 * per / expected, 2),
           "dollars": round(per * qty, 2)}
    if risk:
        out["r"] = round(per / float(risk), 4)
    return out


def plan_for(plan_path, symbol, date):
    """trader/plan.json when it is for this symbol and this day, else None."""
    plan = read_json(plan_path, "plan", required=False) if plan_path else None
    if not isinstance(plan, dict) or str(plan.get("symbol", "")).upper() != symbol.upper():
        return None
    if plan.get("date") and str(plan["date"]) != date:
        return None
    return plan


def plan_risk(plan):
    plan = plan or {}
    r = _f(plan.get("risk_per_share"))
    if r:
        return r
    e, s = _f(plan.get("entry")), _f(plan.get("stop"))
    return abs(e - s) if e and s and e != s else None


def expectation(side, kind, expected, plan, order=None):
    """(expected price, kind, risk per share) for a fill. The expected price is, in order:
    --expected; a limit order's limit; the plan's entry (a buy), stop or target (a sell
    that says --kind stop / target). A flatten has no plan price: pass --expected
    (the bid when you sent it)."""
    order = order or {}
    plan = plan or order.get("plan") or {}
    if not kind:
        kind = "entry" if side == "buy" else None
    if expected is None:
        if str(order.get("type", "")) == "limit" and _f(order.get("limit_price")):
            expected = _f(order["limit_price"])
        elif kind in ("entry", "stop", "target"):
            expected = _f(plan.get(kind))
    else:
        expected = _f(expected)
        if expected is None or expected <= 0:
            raise TicketError("--expected wants a positive price, like --expected 364.18")
    return expected, kind, plan_risk(plan)


def plan_context(plan):
    """What the journal needs from an entry's plan: its stop, target, risk a share and setup."""
    plan = plan or {}
    out = {}
    for k in ("stop", "target"):
        if _f(plan.get(k)):
            out[k] = _f(plan[k])
    if plan_risk(plan):
        out["risk_per_share"] = round(plan_risk(plan), 4)
    if plan.get("setup"):
        out["setup"] = str(plan["setup"])
    return out


def log_fill(state_path, now, today, symbol, side, qty, price, expected=None, kind=None, risk=None,
             context=None):
    """A fill in the log, so trader-risk can count day trades (a buy and a sell the same day).
    With an expected price it also records the fill's slippage; an entry also keeps its plan's
    stop, target, risk a share and setup (context) for the journal. Returns the record."""
    state = load_state(state_path)
    rec = {
        "at": ny_iso(now), "date": today, "status": "filled", "symbol": symbol.upper(), "side": side,
        "qty": _str_num(float(qty)), "price": float(price),
        "plain": "%s %s %s at %s" % (side.upper(), _str_num(float(qty)), symbol.upper(), _p(price))}
    if kind:
        rec["kind"] = kind
    if side == "buy" and context:
        rec.update(context)
    if expected:
        rec["expected"] = float(expected)
        rec["slippage"] = slippage(side, expected, price, qty, risk)
    state.setdefault("orders", []).append(rec)
    write_json(state_path, state)
    return rec


def slip_words(rec):
    s = rec.get("slippage")
    if not s:
        return ""
    word = "worse" if s["per_share"] > 0 else "better" if s["per_share"] < 0 else "exactly"
    r = (", %+.3fR" % s["r"]) if s.get("r") is not None else ""
    if word == "exactly":
        return "filled exactly at the expected %s" % _p(rec["expected"])
    return "%s than the expected %s by %s a share (%+.1f bps%s, %s in all)" % (
        word, _p(rec["expected"]), "%.4g" % abs(s["per_share"]), s["bps"], r, _money(abs(s["dollars"])))


def fill_quality(state, days=None):
    """Every measured fill (one with an expected price), and averages by kind.
    A take-profit is a limit order, so it cannot fill worse than its price; it is listed
    but left out of "market" (the average the Time Machine uses for --slippage auto)."""
    rows = [r for r in state.get("orders", []) if r.get("status") == "filled" and r.get("slippage")
            and (days is None or rec_day(r) in days)]

    def avg(rs):
        if not rs:
            return None
        return {"n": len(rs),
                "bps": round(sum(r["slippage"]["bps"] for r in rs) / len(rs), 2),
                "per_share": round(sum(r["slippage"]["per_share"] for r in rs) / len(rs), 4),
                "dollars": round(sum(r["slippage"]["dollars"] for r in rs), 2),
                "worst_bps": max(r["slippage"]["bps"] for r in rs)}
    by = {}
    for k in ("entry", "stop", "target", "flatten", "other"):
        a = avg([r for r in rows if (r.get("kind") or "other") == k])
        if a:
            by[k] = a
    return {"fills": rows, "by_kind": by, "all": avg(rows),
            "market": avg([r for r in rows if r.get("kind") != "target"])}


# ---------------------------------------------------------------- commands

def _clock(a):
    now = parse_now(getattr(a, "now", None))
    today = getattr(a, "today", None) or to_eastern(now).date().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", today):
        raise TicketError("--today wants a date like 2026-10-19")
    return now, today


def _load(a):
    doc = read_json(a.orders, "orders file (run trader-budget, or ticket.py flatten, first)")
    orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
    if not isinstance(orders, list) or not orders:
        raise TicketError("no orders in %s" % a.orders)
    cfg = read_json(a.config, "config", required=False) or {}
    risk = read_json(a.risk, "risk check", required=False)
    state = load_state(a.state)
    now, today = _clock(a)
    return orders, cfg, risk, state, today, now


def _pick(orders, index):
    if index is None:
        raise TicketError("say which order: --index N")
    if not 1 <= index <= len(orders):
        raise TicketError("there is no order %d (there are %d)" % (index, len(orders)))
    return orders[index - 1]


def cmd_show(a):
    orders, cfg, risk, state, today, now = _load(a)
    picks = [(a.index, _pick(orders, a.index))] if a.index else list(enumerate(orders, 1))
    if a.json:
        out = [ticket_json(o, i, cfg, risk, state, today) for i, o in picks]
        print(json.dumps(out[0] if a.index else out, indent=2))
        return 0 if any(t["ready"] for t in out) else 1
    blocks, any_ready = [], False
    for i, o in picks:
        text, ready = render(o, i, len(orders), cfg, risk, state, today)
        blocks.append(text)
        any_ready = any_ready or ready
    print("\n\n".join(blocks))
    print("\nOne order at a time: a yes covers one ticket, never the batch. Education and tooling, "
          "not financial advice.")
    return 0 if any_ready else 1


def cmd_approve(a):
    orders, cfg, risk, state, today, now = _load(a)
    order = _pick(orders, a.index)
    ready, label, rv = status_of(order, risk, state, today)
    if not ready:
        raise TicketError("order %d is not ready: %s" % (a.index, label))
    ok, why = parse_yes(a.reply, order, [o.get("symbol", "") for o in orders])
    if not ok:
        print("Not recorded: %s. Ask the user again with the ticket for order %d." % (why, a.index))
        return 1
    loss, stop = max_loss(order)
    rec = {"at": ny_iso(now), "date": today, "index": a.index, "fingerprint": fingerprint(order),
           "symbol": str(order.get("symbol", "")).upper(), "side": order.get("side"),
           "qty": order.get("qty"), "kind": kind_of(order, rv), "max_loss": loss, "stop": stop,
           "plain": plain(order), "status": "approved", "reply": a.reply,
           "paper": bool(cfg.get("paper", True)), "broker": cfg.get("broker", "alpaca")}
    state.setdefault("orders", []).append(rec)
    write_json(a.state, state)
    print("Recorded your yes for order %d: %s." % (a.index, plain(order)))
    if str(cfg.get("broker", "alpaca")).lower() == "ibkr":
        print("Now draft it with the Interactive Brokers connector; approve it in your IBKR account.")
    else:
        print("Now call place_stock_order with exactly:")
        print(json.dumps(tool_input(order), indent=2))
        print("Claude's card shows Allow once / Deny. Then: ticket.py result --index %d --status "
              "placed|denied|failed" % a.index)
    return 0


def cmd_decline(a):
    orders, cfg, risk, state, today, now = _load(a)
    order = _pick(orders, a.index)
    rec = {"at": ny_iso(now), "date": today, "index": a.index, "fingerprint": fingerprint(order),
           "symbol": str(order.get("symbol", "")).upper(), "side": order.get("side"),
           "plain": plain(order), "status": "declined", "reply": a.reply or "no"}
    state.setdefault("orders", []).append(rec)
    write_json(a.state, state)
    print("Recorded: you said no to order %d (%s). Nothing was sent." % (a.index, plain(order)))
    return 0


def cmd_result(a):
    orders, cfg, risk, state, today, now = _load(a)
    order = _pick(orders, a.index)
    fp = fingerprint(order)
    rec = latest(state, fp, today)
    if not rec or rec.get("status") != "approved":
        raise TicketError("order %d has no yes recorded today; a result can only follow an approval" % a.index)
    new = {"at": ny_iso(now), "date": today, "index": a.index, "fingerprint": fp, "symbol": rec["symbol"],
           "side": rec["side"], "plain": rec["plain"], "status": a.status}
    for k in ("qty", "kind", "max_loss", "stop"):
        if rec.get(k) is not None:
            new[k] = rec[k]
    if a.broker_id:
        new["broker_order_id"] = a.broker_id
    if a.note:
        new["note"] = a.note
    state["orders"].append(new)
    write_json(a.state, state)
    print("Recorded order %d as %s." % (a.index, a.status))
    if a.status == "placed" and a.filled_qty and a.filled_price:
        apply_fill(a.portfolio, cfg, rec["symbol"], rec["side"], a.filled_qty, a.filled_price, today)
        kind = "entry" if rec.get("kind") == "entry" else ("flatten" if rec["side"] == "sell" else None)
        exp, kind, risk = expectation(rec["side"], kind, a.expected, None, order)
        plan = order.get("plan") or plan_for(a.plan, rec["symbol"], today)
        if risk is None:
            risk = plan_risk(plan)
        frec = log_fill(a.state, now, today, rec["symbol"], rec["side"], a.filled_qty, a.filled_price,
                        exp, kind, risk, plan_context(plan))
        print("Added the fill to %s." % a.portfolio)
        if frec.get("slippage"):
            print("Fill quality: %s." % slip_words(frec))
        else:
            print("Fill quality not measured: no expected price. Next time pass --expected P "
                  "(the bid or ask when you sent it).")
    elif a.status == "placed":
        print("When it fills, record it: ticket.py fill --symbol %s --side %s --qty Q --price P"
              % (rec["symbol"], rec["side"]))
        if rec.get("kind") == "entry" and is_bracket(order):
            print("When the stop-loss or the take-profit fills later, record that sell the same way.")
    return 0


def cmd_fill(a):
    cfg = read_json(a.config, "config", required=False) or {}
    now = parse_now(a.now)
    date = a.date or to_eastern(now).date().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise TicketError("--date wants a date like 2026-10-19")
    plan = plan_for(a.plan, a.symbol, date)
    exp, kind, risk = expectation(a.side, a.kind, a.expected, plan)
    if a.side == "sell" and kind == "entry":
        raise TicketError("a sell is not an entry here (long only): use --kind stop, target, flatten or other")
    pf = apply_fill(a.portfolio, cfg, a.symbol, a.side, a.qty, a.price, date)
    rec = log_fill(a.state, now, date, a.symbol, a.side, a.qty, a.price, exp, kind, risk, plan_context(plan))
    print("Recorded %s %s %s at %s on %s in %s. Cash now %s." % (a.side, a.qty, a.symbol.upper(),
                                                                _money(a.price), date, a.portfolio,
                                                                _money(pf["cash"])))
    if rec.get("slippage"):
        print("Fill quality: %s." % slip_words(rec))
    elif a.side == "sell" and not a.kind:
        print("Fill quality not measured: say which exit it was (--kind stop or target, so the plan's price "
              "is the expected one) or pass --expected P.")
    else:
        print("Fill quality not measured: no expected price (pass --expected P).")
    return 0


def cmd_slippage(a):
    """Fill quality: expected price vs the fill, for every measured fill."""
    state = load_state(a.state)
    now, today = _clock(a)
    q = fill_quality(state, None if a.all else {today})
    if a.json:
        print(json.dumps(q, indent=2))
        return 0 if q["fills"] else 1
    if not q["fills"]:
        print("No measured fills%s. A fill is measured when it has an expected price: the plan's entry, "
              "stop or target, a limit, or --expected." % ("" if a.all else " today (try --all)"))
        return 1
    print("Fill quality%s: positive = worse than expected (it cost you), negative = better." %
          ("" if a.all else " today"))
    for r in q["fills"]:
        s = r["slippage"]
        print("  %s  %-7s %-26s expected %-9s %+8.4f a share  %+7.1f bps  %s%s" % (
            r.get("at", "")[:16].replace("T", " "), r.get("kind") or "other", r.get("plain"),
            _p(r["expected"]), s["per_share"], s["bps"],
            ("%+.3fR  " % s["r"]) if s.get("r") is not None else "",
            ("-" if s["dollars"] > 0 else "+") + _money(abs(s["dollars"]))))
    print("")
    for k, v in q["by_kind"].items():
        print("  %-8s %d fill%s, average %+.1f bps (%+.4f a share), worst %+.1f bps, %s %s in all%s" % (
            k, v["n"], "" if v["n"] == 1 else "s", v["bps"], v["per_share"], v["worst_bps"],
            "cost" if v["dollars"] > 0 else "saved", _money(abs(v["dollars"])),
            " (limit orders: never worse than their price)" if k == "target" else ""))
    m = q["market"]
    if m:
        print("")
        print("Market-type fills (entries, stops, flattens): %d, average %+.1f bps a side. "
              "trader-timemachine run --slippage auto uses this." % (m["n"], m["bps"]))
        if m["n"] < 5:
            print("That is only %d fill%s: too few to trust; the average will move." % (m["n"], "" if m["n"] == 1 else "s"))
    return 0


def cmd_flatten(a):
    cfg = read_json(a.config, "config", required=False) or {}
    sym = a.symbol.strip().upper()
    now, today = _clock(a)
    source = "the broker, get_open_position"
    if a.qty is not None:
        qty = _f(a.qty)
        if qty is None or qty <= 0:
            raise TicketError("--qty wants the number of shares you hold, like --qty 8")
    else:
        pf = read_json(a.portfolio, "portfolio", required=False) or {}
        qty = sum(_f(p.get("shares", p.get("qty"))) or 0 for p in pf.get("positions", [])
                  if str(p.get("ticker") or p.get("symbol") or "").upper() == sym)
        source = a.portfolio
        if qty <= 1e-9:
            raise TicketError("nothing to flatten: no %s shares in %s. Check the broker (get_open_position "
                              "%s) and pass --qty if you do hold some" % (sym, a.portfolio, sym))
    plan = read_json(a.plan, "plan", required=False) or {}
    flat_by = (plan.get("flat_by") if str(plan.get("symbol", "")).upper() == sym else None) \
        or cfg.get("flat_by") or "15:55"
    order = {"symbol": sym, "side": "sell", "qty": _str_num(qty), "type": "market", "time_in_force": "day",
             "why": "flat by %s New York: closes the %s day trade before the close (qty from %s)"
             % (flat_by, sym, source)}
    old = read_json(a.orders, "orders", required=False)
    replaced = len(old.get("orders", [])) if isinstance(old, dict) else 0
    doc = {"created_by": "trader-broker", "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "proposed",
           "paper": bool(cfg.get("paper", True)),
           "note": "Flatten ticket. Nothing is placed until trader-risk passes it and you say yes in the chat.",
           "source": "ticket.py flatten %s on %s" % (sym, today), "orders": [order]}
    write_json(a.orders, doc)
    print("Flatten %s: %s (flat by %s New York)." % (sym, plain(order), flat_by))
    print("Wrote it to %s%s." % (a.orders, (" (it replaced %d earlier proposal%s)"
                                             % (replaced, "" if replaced == 1 else "s")) if replaced else ""))
    if a.qty is None:
        print("The qty comes from %s. Check it against get_open_position %s before you say yes." % (source, sym))
    print("Next:")
    print("  1. trader-risk: check.py. A sell that only closes what you hold is never blocked by the daily")
    print("     limits or the entry window.")
    print("  2. ticket.py show, then the user's yes for this one order.")
    print("  3. If the bracket's stop-loss and take-profit are still open, Alpaca holds these shares for them")
    print("     and rejects a new sell. Cancel them first: get_orders (status open, nested true), then")
    print("     cancel_order_by_id for each open leg (Needs approval). Then place_stock_order with the ticket.")
    return 0


def cmd_log(a):
    state = load_state(a.state)
    now, today = _clock(a)
    rows = [r for r in state.get("orders", []) if a.all or rec_day(r) == today]
    if not rows:
        print("No decisions recorded%s." % ("" if a.all else " today"))
        return 1
    for r in rows:
        extra = (" id " + r["broker_order_id"]) if r.get("broker_order_id") else ""
        reply = (' reply "%s"' % r["reply"]) if r.get("reply") and r["status"] in ("approved", "declined") else ""
        loss = (" max loss %s" % _money(r["max_loss"])) if r.get("max_loss") is not None and r["status"] == "placed" else ""
        idx = ("#%s" % r["index"]) if r.get("index") is not None else "  "
        print("%s  %s %-9s %s%s%s%s" % (r.get("at"), idx, r.get("status"), r.get("plain"), reply, loss, extra))
    placed = sum(1 for r in rows if r.get("status") == "placed")
    print("%d placed%s." % (placed, "" if a.all else " today"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Order tickets and your yes (trader-broker). Never places orders.")
    sub = ap.add_subparsers(dest="cmd")

    def clock(p):
        p.add_argument("--now", help="pretend it is this New York time, e.g. \"2026-10-19 10:15\"")
        p.add_argument("--today", help="YYYY-MM-DD (default: today in New York)")

    def common(p):
        p.add_argument("--orders", default="trader/orders.json")
        p.add_argument("--config", default="trader/config.json")
        p.add_argument("--risk", default="trader/state/risk.json")
        p.add_argument("--state", default="trader/state/broker.json")
        clock(p)

    p = sub.add_parser("show", help="render the tickets")
    common(p)
    p.add_argument("--index", type=int)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("approve", help="record the user's explicit yes for one order")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--reply", required=True, help="the user's reply, word for word")
    p = sub.add_parser("decline", help="record a no")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--reply")
    p = sub.add_parser("result", help="record what happened after the Allow once / Deny card")
    common(p)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--status", required=True, choices=["placed", "denied", "failed"])
    p.add_argument("--broker-id")
    p.add_argument("--note")
    p.add_argument("--filled-qty")
    p.add_argument("--filled-price")
    p.add_argument("--expected", help="the price you expected (default: the limit, or the plan's entry)")
    p.add_argument("--plan", default="trader/plan.json")
    p.add_argument("--portfolio", default="trader/portfolio.json")
    p = sub.add_parser("fill", help="record a fill in trader/portfolio.json")
    p.add_argument("--symbol", required=True)
    p.add_argument("--side", required=True, choices=["buy", "sell"])
    p.add_argument("--qty", required=True)
    p.add_argument("--price", required=True)
    p.add_argument("--kind", choices=["entry", "stop", "target", "flatten", "other"],
                   help="which leg filled; stop / target take the expected price from the plan")
    p.add_argument("--expected", help="the price you expected (default: from the plan and --kind)")
    p.add_argument("--plan", default="trader/plan.json")
    p.add_argument("--date", help="YYYY-MM-DD (default: today in New York)")
    p.add_argument("--now")
    p.add_argument("--portfolio", default="trader/portfolio.json")
    p.add_argument("--config", default="trader/config.json")
    p.add_argument("--state", default="trader/state/broker.json")
    p = sub.add_parser("slippage", help="fill quality: expected price vs the fill")
    p.add_argument("--state", default="trader/state/broker.json")
    p.add_argument("--all", action="store_true", help="every day, not just today")
    p.add_argument("--json", action="store_true")
    clock(p)
    p = sub.add_parser("flatten", help="a sell ticket that closes a symbol's position by flat_by")
    p.add_argument("--symbol", required=True)
    p.add_argument("--qty", help="shares you hold, from get_open_position (default: trader/portfolio.json)")
    p.add_argument("--orders", default="trader/orders.json", help="where the ticket is written")
    p.add_argument("--portfolio", default="trader/portfolio.json")
    p.add_argument("--plan", default="trader/plan.json")
    p.add_argument("--config", default="trader/config.json")
    clock(p)
    p = sub.add_parser("log", help="today's decisions")
    p.add_argument("--state", default="trader/state/broker.json")
    clock(p)
    p.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    try:
        return {"show": cmd_show, "approve": cmd_approve, "decline": cmd_decline, "result": cmd_result,
                "fill": cmd_fill, "flatten": cmd_flatten, "log": cmd_log, "slippage": cmd_slippage}[a.cmd](a)
    except TicketError as e:
        print("ticket.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
