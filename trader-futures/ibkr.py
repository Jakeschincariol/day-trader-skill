"""The Interactive Brokers side of trader-futures, through IB Gateway or TWS on
the user's own computer, with the ib_async library (pip install ib_async).

Everything the autotrader needs from a broker goes through the small
`Broker` class below, so the strategy code never touches ib_async and the
tests can swap in a fake broker.

Ports (IBKR defaults):  IB Gateway paper 4002, live 4001;  TWS paper 7497, live 7496.
A paper account's id starts with "DU": the autotrader checks that before it
trades in paper mode, and refuses a "DU" account in live mode.
"""

import datetime
import math

import futures as fx

ORDER_REF = "trader-futures"
UTC = datetime.timezone.utc


class BrokerError(Exception):
    pass


def _ib():
    try:
        import ib_async
    except ImportError:
        raise BrokerError("ib_async is not installed: run  pip install ib_async  (Python 3.10+)")
    return ib_async


def _f(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


class Broker(object):
    def __init__(self, host="127.0.0.1", port=4002, client_id=17, readonly=False, log=print):
        self.ib_mod = _ib()
        self.ib = self.ib_mod.IB()
        self.host, self.port, self.client_id, self.readonly = host, port, client_id, readonly
        self.log = log
        self.acct = None
        self.base = None
        self._pnl = None
        self._bars = {}

    # ------------------------------------------------------------ connection

    def connect(self):
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=15, readonly=self.readonly)
        except Exception as e:
            raise BrokerError("cannot reach IB Gateway/TWS on %s:%s (%s). Is it running and logged in, with "
                              "the API enabled (Configure > Settings > API)?" % (self.host, self.port, e))
        accts = self.ib.managedAccounts()
        if not accts:
            raise BrokerError("IBKR returned no account")
        self.acct = accts[0]
        for v in self.ib.accountValues(self.acct):
            if v.tag == "NetLiquidation" and v.currency not in ("", "BASE"):
                self.base = v.currency
        self.base = self.base or "EUR"
        try:
            self._pnl = self.ib.reqPnL(self.acct)
        except Exception:
            self._pnl = None
        return self

    def connected(self):
        return self.ib.isConnected()

    def reconnect(self):
        try:
            self.ib.disconnect()
        except Exception:
            pass
        self._bars = {}
        return self.connect()

    def disconnect(self):
        self.ib.disconnect()

    def sleep(self, seconds):
        self.ib.sleep(seconds)

    # ------------------------------------------------------------ account

    def account_info(self):
        vals = {}
        for v in self.ib.accountValues(self.acct):
            if v.currency in (self.base, "BASE", ""):
                vals.setdefault(v.tag, v.value)
        return {"account": self.acct, "paper": self.acct.upper().startswith("DU"), "base": self.base,
                "net_liq": _f(vals.get("NetLiquidation")), "available": _f(vals.get("AvailableFunds"))}

    def _to_eur(self, amount):
        if amount is None:
            return None
        if self.base == "EUR":
            return amount
        return fx.to_eur(amount, self.base, self.eurusd())

    def eurusd(self):
        """USD per EUR, from the account's own exchange rates."""
        for v in self.ib.accountValues(self.acct):
            if v.tag == "ExchangeRate":
                r = _f(v.value)
                if not r:
                    continue
                if self.base == "EUR" and v.currency == "USD":
                    return 1.0 / r          # EUR per USD -> USD per EUR
                if self.base == "USD" and v.currency == "EUR":
                    return r
        return None

    def daily_pnl_eur(self):
        """Today's P&L (realized + open) in EUR, as IBKR reports it."""
        if self._pnl is None:
            return None
        return self._to_eur(_f(self._pnl.dailyPnL))

    def available_eur(self):
        return self._to_eur(self.account_info().get("available"))

    # ------------------------------------------------------------ contracts

    def resolve(self, spec, today, roll_days=8):
        """The contract to trade today and its real multiplier and tick."""
        m = self.ib_mod
        kw = {"exchange": spec["exchange"], "currency": spec["currency"]}
        if spec.get("trading_class"):
            kw["tradingClass"] = spec["trading_class"]
        details = self.ib.reqContractDetails(m.Future(spec["symbol"], **kw))
        if not details:
            raise BrokerError("IBKR knows no %s futures on %s: check the symbol, and that your account has "
                              "futures trading permission for %s" % (spec["key"], spec["exchange"], spec["exchange"]))
        months = [{"expiry": d.contract.lastTradeDateOrContractMonth, "detail": d} for d in details]
        pick = fx.pick_contract(months, today, roll_days)["detail"]
        c = pick.contract
        over = {"multiplier": _f(c.multiplier) or spec["multiplier"], "tick": _f(pick.minTick) or spec["tick"],
                "local_symbol": c.localSymbol, "expiry": c.lastTradeDateOrContractMonth}
        return c, over

    # ------------------------------------------------------------ data

    def bars(self, contract, days=20):
        """5-minute TRADES bars of this contract, all hours, merged with what we
        already have: the first call asks for `days`, later calls the last hour."""
        key = contract.conId
        have = self._bars.get(key)
        dur = "%d D" % days if not have else "3600 S"
        raw = self.ib.reqHistoricalData(contract, endDateTime="", durationStr=dur, barSizeSetting="5 mins",
                                        whatToShow="TRADES", useRTH=False, formatDate=2, timeout=60)
        merged = {b["t"]: b for b in (have or [])}
        for r in raw or []:
            t = r.date
            if isinstance(t, datetime.date) and not isinstance(t, datetime.datetime):
                continue
            if t.tzinfo is None:
                t = t.replace(tzinfo=UTC)
            merged[t.astimezone(UTC)] = {"t": t.astimezone(UTC), "o": r.open, "h": r.high, "l": r.low,
                                         "c": r.close, "v": float(r.volume or 0)}
        out = [merged[k] for k in sorted(merged)]
        self._bars[key] = out
        return out

    # ------------------------------------------------------------ orders

    def position(self, contract):
        n = 0
        for p in self.ib.positions(self.acct):
            if p.contract.conId == contract.conId:
                n += p.position
        return int(n)

    def margin_eur(self, contract, action, qty):
        """Initial margin for the order, from IBKR's what-if check."""
        try:
            st = self.ib.whatIfOrder(contract, self.ib_mod.MarketOrder(action, qty))
        except Exception:
            return None
        return self._to_eur(_f(getattr(st, "initMarginChange", None)))

    def place_bracket(self, contract, plan, qty, timeout=60):
        """Limit entry + stop-loss + take-profit, linked so one exit cancels the
        other. Waits `timeout` seconds for the entry; cancels it if unfilled."""
        if self.readonly:
            raise BrokerError("connected read-only (observe mode): no orders")
        bo = self.ib.bracketOrder(plan["action"], qty, plan["limit"], plan["target"], plan["stop"])
        for o in (bo.parent, bo.takeProfit, bo.stopLoss):
            o.orderRef = ORDER_REF
            o.account = self.acct
        bo.parent.tif = "DAY"
        bo.takeProfit.tif = bo.stopLoss.tif = "GTC"
        trades = [self.ib.placeOrder(contract, o) for o in (bo.parent, bo.takeProfit, bo.stopLoss)]
        parent = trades[0]
        waited = 0.0
        while waited < timeout:
            self.ib.sleep(1)
            waited += 1
            st = parent.orderStatus.status
            if st == "Filled":
                return {"status": "filled", "qty": int(parent.orderStatus.filled),
                        "avg": parent.orderStatus.avgFillPrice, "order_id": parent.order.orderId}
            if st in ("Cancelled", "ApiCancelled", "Inactive"):
                msg = "; ".join(e.message for e in parent.log if e.message)
                return {"status": "rejected", "detail": msg or st}
        self.ib.cancelOrder(parent.order)
        self.ib.sleep(2)
        filled = int(parent.orderStatus.filled or 0)
        if filled:
            return {"status": "filled", "qty": filled, "avg": parent.orderStatus.avgFillPrice,
                    "order_id": parent.order.orderId, "partial": True}
        return {"status": "not-filled", "detail": "limit %s not reached within %ds" % (plan["limit"], timeout)}

    def cancel_ours(self, contract):
        n = 0
        for t in self.ib.openTrades():
            if t.contract.conId == contract.conId and t.order.orderRef == ORDER_REF:
                self.ib.cancelOrder(t.order)
                n += 1
        if n:
            self.ib.sleep(2)
        return n

    def flatten(self, contract):
        """Cancel our open orders on this contract, then close the position at market."""
        if self.readonly:
            raise BrokerError("connected read-only (observe mode): no orders")
        self.cancel_ours(contract)
        pos = self.position(contract)
        if pos == 0:
            return {"closed": 0}
        o = self.ib_mod.MarketOrder("SELL" if pos > 0 else "BUY", abs(pos))
        o.orderRef = ORDER_REF
        o.account = self.acct
        tr = self.ib.placeOrder(contract, o)
        for _ in range(30):
            self.ib.sleep(1)
            if tr.orderStatus.status == "Filled":
                break
        return {"closed": pos, "avg": tr.orderStatus.avgFillPrice, "status": tr.orderStatus.status}

    def exit_fill(self, contract, since):
        """Average price and commission (EUR) of the fills that closed our
        position on this contract after `since`."""
        qty = px = comm = 0.0
        for f in self.ib.fills():
            if f.contract.conId != contract.conId:
                continue
            t = f.execution.time
            if t.tzinfo is None:
                t = t.replace(tzinfo=UTC)
            if t < since:
                continue
            q = f.execution.shares
            qty += q
            px += q * f.execution.price
            comm += _f(getattr(f.commissionReport, "commission", 0)) or 0.0
        if not qty:
            return None
        return {"avg": px / qty, "qty": qty, "commission": comm}
