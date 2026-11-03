#!/usr/bin/env python3
"""trader-futures autotrader: runs the volume-surge breakout on index futures
by itself, on YOUR computer, through IB Gateway (or TWS).

  python3 autotrader.py --mode observe     # watches and notifies, never orders (read-only connection)
  python3 autotrader.py --mode paper       # trades the PAPER account by itself (account must start with DU)
  python3 autotrader.py --mode live        # real money: only with "paper": false AND the live_confirm
                                           # sentence in trader/config.json, and a non-DU account

Stop it any time: Ctrl+C (open positions keep their stop and target at IBKR),
or create the file trader/STOP: it flattens everything it opened and exits.

What it does every few seconds, for each contract in the config:
  - at the flat-by time: cancels its orders and closes the position;
  - when a 5-minute bar completes: checks the signal (futures.evaluate), makes
    the plan, sizes it in EUR, asks IBKR for the margin, runs the risk rules,
    and in paper/live mode sends ONE bracket order (limit entry + stop + target);
  - when a position closes: writes the trade to trader/journal.csv (Excel-ready);
  - when today's P&L reaches the daily loss limit: flattens and stops for the day.

Not financial advice. Futures are leveraged and a loss can exceed your deposit.
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import futures as fx  # noqa: E402

UTC = datetime.timezone.utc
LIVE_SENTENCE = "IK BEGRIJP DAT DIT ECHT GELD IS"
PORTS = {"paper": 4002, "live": 4001, "observe": 4002}


def utc_now():
    return datetime.datetime.now(UTC).replace(microsecond=0)


# ---------------------------------------------------------------- notify + log

class Notifier(object):
    """Push to the phone through ntfy.sh (free app, no account): set
    "notify": {"ntfy_topic": "a-long-random-name"} in the config and subscribe
    to that topic in the ntfy app. Always also prints and logs."""

    def __init__(self, cfg, log_path, quiet=False):
        self.topic = ((cfg.get("notify") or {}).get("ntfy_topic") or "").strip()
        self.server = ((cfg.get("notify") or {}).get("ntfy_server") or "https://ntfy.sh").rstrip("/")
        self.log_path = log_path
        self.quiet = quiet

    def __call__(self, title, text="", priority="default", push=True):
        line = "%s  %s%s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), title,
                             (" | " + text.replace("\n", " | ")) if text else "")
        if not self.quiet:
            print(line, flush=True)
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
        if push and self.topic:
            try:
                req = urllib.request.Request("%s/%s" % (self.server, self.topic), data=(text or title).encode(),
                                             headers={"Title": title.encode("ascii", "replace").decode(),
                                                      "Priority": priority})
                urllib.request.urlopen(req, timeout=10).close()
            except Exception:
                pass


# ---------------------------------------------------------------- state

class State(object):
    """trader/state/futures-YYYY-MM-DD.json: today's trades, open trade, halt."""

    def __init__(self, folder, day):
        self.path = os.path.join(folder, "futures-%s.json" % day)
        self.data = {"date": day, "trades": 0, "open_trades": {}, "last_loss": {}, "halted": None,
                     "closed": []}
        if os.path.exists(self.path):
            with open(self.path) as fh:
                self.data.update(json.load(fh))

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.data, fh, indent=2, default=str)
        os.replace(tmp, self.path)


# ---------------------------------------------------------------- the engine

class Engine(object):
    """All decisions. `broker` is ibkr.Broker or a fake with the same methods."""

    def __init__(self, broker, cfg, mode, folder, notify, clock=utc_now):
        self.b, self.cfg, self.mode, self.folder = broker, cfg, mode, folder
        self.notify, self.clock = notify, clock
        self.contracts = {}          # key -> {"spec", "contract"}
        self.last_bar = {}           # key -> iso of the last bar evaluated
        self.last_fetch = {}         # key -> when we last asked IBKR for bars (pacing)
        self.state = None
        self.journal = os.path.join(folder, "journal.csv")

    # -- setup ---------------------------------------------------------

    def check_account(self):
        info = self.b.account_info()
        acct, paper = info["account"], info["paper"]
        if self.mode == "paper" and not paper:
            raise SystemExit("REFUSED: paper mode, but account %s is not a paper account (paper ids start with "
                             "DU). Log IB Gateway in to your paper account, or use port 4002." % acct)
        if self.mode == "live":
            if paper:
                raise SystemExit("REFUSED: live mode, but account %s is a paper account." % acct)
            if self.cfg.get("paper", True) is not False or self.cfg.get("live_confirm") != LIVE_SENTENCE:
                raise SystemExit('REFUSED: live mode needs "paper": false and "live_confirm": "%s" in '
                                 'trader/config.json, typed by you.' % LIVE_SENTENCE)
        return info

    def setup(self):
        info = self.check_account()
        today = self.clock().date()
        roll = int(self.cfg.get("roll_days", 8))
        lines = []
        for key in self.cfg.get("contracts") or ["MES"]:
            spec = fx.spec_for(key, self.cfg)
            c, over = self.b.resolve(spec, today, roll)
            spec.update(over)
            self.contracts[spec["key"]] = {"spec": spec, "contract": c}
            lines.append("%s %s (expiry %s), %s %s per point, tick %s, sessions: %s" % (
                spec["key"], over.get("local_symbol", ""), over.get("expiry", ""), spec["currency"],
                spec["multiplier"], spec["tick"], fx.windows_text(spec)))
        r = self.cfg["risk"]
        acct = info["account"]
        masked = acct[:2] + "*" * max(0, len(acct) - 5) + acct[-3:]
        self.notify("trader-futures started: %s mode, account %s" % (self.mode.upper(), masked),
                    "\n".join(lines) + "\nmax loss/trade EUR %s, daily limit EUR %s, max %s trades/day"
                    % (r["max_loss_per_trade_eur"], r["max_daily_loss_eur"], r["max_trades_per_day"]))

    # -- per-day state -------------------------------------------------

    def day_state(self, now):
        day = now.astimezone(fx.tz("Europe/Amsterdam")).date().isoformat()
        if self.state is None or self.state.data["date"] != day:
            self.state = State(os.path.join(self.folder, "state"), day)
        return self.state

    def risk_state(self, pnl, positions=None):
        d = self.state.data
        open_ = {k: (v.get("qty") or 0) for k, v in d["open_trades"].items()}
        for k, q in (positions or {}).items():   # a position you opened yourself also counts
            if q:
                open_[k] = q
        return {"date": d["date"], "trades": d["trades"], "pnl_eur": pnl or 0.0, "halted": d["halted"],
                "open": open_, "last_loss": d["last_loss"]}

    # -- one pass ------------------------------------------------------

    def tick(self):
        now = self.clock()
        st = self.day_state(now)
        if os.path.exists(os.path.join(self.folder, "STOP")):
            self.flatten_all("STOP file found")
            return "stop"
        pnl = self.b.daily_pnl_eur()
        r = self.cfg["risk"]
        if pnl is not None and pnl <= -r["max_daily_loss_eur"] and not st.data["halted"]:
            st.data["halted"] = "daily loss limit: P&L EUR %.2f" % pnl
            st.save()
            self.flatten_all("daily loss limit reached (EUR %.2f)" % pnl)
        for key, item in self.contracts.items():
            self.manage(key, item, now, pnl)
        return "ok"

    def manage(self, key, item, now, pnl):
        spec, c = item["spec"], item["contract"]
        st = self.state.data
        pos = self.b.position(c) if self.mode != "observe" else 0
        rec = st["open_trades"].get(key)
        # a trade we opened has closed (stop, target or flatten)
        if rec and pos == 0:
            self.record_close(key, item, rec, now)
            rec = None
        # flat by the end of the session it was opened in: only positions this
        # autotrader opened
        if rec and pos != 0:
            flat_t = fx.parse_time(rec["flat_by_utc"]) if rec.get("flat_by_utc") else fx.at_local(
                fx.session_day(now, spec), spec["flat_by"], spec)
            if now >= flat_t:
                res = self.b.flatten(c)
                self.notify("%s flat by %s (end of the %s session)" % (key, fx.dutch(flat_t), rec.get("session", "")),
                            "closed %s at %s" % (res.get("closed"), res.get("avg")))
                return
        # a new completed bar? Ask IBKR only when one is due, and not more than
        # every 20 seconds (IBKR's historical-data pacing rules)
        due = now.replace(minute=now.minute - now.minute % 5, second=0, microsecond=0) - fx.BAR
        if self.last_bar.get(key) == due.isoformat():
            return
        lf = self.last_fetch.get(key)
        if lf and (now - lf).total_seconds() < 20:
            return
        self.last_fetch[key] = now
        bars = self.b.bars(c)
        done = fx.completed(bars, now)
        if not done:
            return
        last = done[-1]["t"].isoformat()
        if self.last_bar.get(key) == last:
            return
        self.last_bar[key] = last
        sig = fx.evaluate(bars, now, spec, self.cfg["strategy"])
        if sig["status"] != "signal":
            return
        plan, why = fx.make_plan(sig, spec, self.cfg["strategy"])
        head = "%s %s signal %s (%s session)" % (key, sig["direction"].upper(), sig["slot"], sig["session"])
        if not plan:
            self.notify(head + ": no trade", why, push=False)
            return
        eurusd = self.b.eurusd() or self.cfg["risk"]["eurusd"]
        sized = fx.size(plan, spec, self.cfg["risk"], eurusd)
        margin = None
        if sized["qty"] >= 1:
            m = self.b.margin_eur(c, plan["action"], sized["qty"])
            avail = self.b.available_eur()
            if m is not None and avail:
                margin = {"init_eur": m, "available_eur": avail}
        ok, reasons = fx.risk_check(plan, sized, spec, self.risk_state(pnl, {key: pos}), now, self.cfg["risk"], margin)
        text = ("%s %d %s limit %s, stop %s, target %s, max loss EUR %.2f\nvolume %.1fx usual"
                % (plan["action"], sized["qty"], spec.get("local_symbol", key), plan["limit"], plan["stop"],
                   plan["target"], sized["max_loss_eur"], sig["metrics"]["rvol"]))
        if not ok:
            self.notify(head + ": BLOCKED", text + "\n" + "; ".join(reasons))
            return
        if self.mode == "observe":
            self.notify(head + " (observe: no order)", text, priority="high")
            return
        st["trades"] += 1               # counts on submit, so a rejected order still uses a slot
        self.state.save()
        res = self.b.place_bracket(c, plan, sized["qty"], int(self.cfg.get("entry_timeout_s", 60)))
        if res["status"] == "filled":
            st["open_trades"][key] = {"qty": res["qty"] if plan["action"] == "BUY" else -res["qty"],
                                      "entry": res["avg"], "stop": plan["stop"], "target": plan["target"],
                                      "risk_eur": sized["max_loss_eur"] * res["qty"] / sized["qty"],
                                      "direction": plan["direction"], "signal": sig["slot"],
                                      "entered_at": self.clock().isoformat(), "rvol": sig["metrics"]["rvol"],
                                      "eurusd": eurusd, "session": sig["session"],
                                      "flat_by_utc": sig["flat_by_utc"]}
            self.state.save()
            self.notify(head + ": IN %s" % ("PAPER" if self.mode == "paper" else "LIVE"),
                        text.replace("limit %s" % plan["limit"], "filled %s" % res["avg"]), priority="high")
        else:
            self.notify(head + ": no fill", res.get("detail", res["status"]))

    def record_close(self, key, item, rec, now):
        spec, c = item["spec"], item["contract"]
        st = self.state.data
        since = fx.parse_time(rec["entered_at"])
        fill = self.b.exit_fill(c, since)
        exit_px = fill["avg"] if fill else None
        qty = abs(rec["qty"])
        sgn = 1 if rec["qty"] > 0 else -1
        pnl_eur = None
        if exit_px is not None:
            gross = (exit_px - rec["entry"]) * sgn * spec["multiplier"] * qty
            comm = (fill.get("commission") or 0.0) + qty * self.cfg["risk"]["commission_per_side"]
            pnl_eur = round(fx.to_eur(gross - comm, spec["currency"], rec.get("eurusd")), 2)
        reason = "target" if exit_px is not None and (exit_px - rec["target"]) * sgn >= -spec["tick"] else (
            "stop" if exit_px is not None and (exit_px - rec["stop"]) * sgn <= spec["tick"] else "closed")
        row = {"date": st["date"], "session": rec.get("session"), "direction": rec["direction"],
               "signal": rec["signal"], "entry_time": fx.dutch(since), "exit_time": fx.dutch(now),
               "qty": qty, "entry": rec["entry"], "stop": rec["stop"], "target": rec["target"], "exit": exit_px,
               "exit_reason": reason, "points": round((exit_px - rec["entry"]) * sgn, 6) if exit_px is not None else None,
               "pnl_eur": pnl_eur, "risk_eur": round(rec["risk_eur"], 2),
               "r": round(pnl_eur / rec["risk_eur"], 2) if pnl_eur is not None and rec["risk_eur"] else None,
               "rvol": rec.get("rvol"), "contract": spec.get("local_symbol", key), "mode": self.mode}
        append_journal(self.journal, row)
        if pnl_eur is not None and pnl_eur < 0:
            st["last_loss"][key] = now.isoformat()
        st["closed"].append(row)
        del st["open_trades"][key]
        self.state.save()
        self.notify("%s OUT (%s)" % (key, reason), "exit %s, P&L about EUR %s" % (exit_px, pnl_eur), priority="high")

    def flatten_all(self, why):
        if self.mode == "observe":
            self.notify("observe mode: " + why)
            return
        for key, item in self.contracts.items():
            res = self.b.flatten(item["contract"])
            if res.get("closed"):
                self.notify("%s flattened: %s" % (key, why), "closed %s at %s" % (res["closed"], res.get("avg")),
                            priority="high")
        self.notify("all trader-futures positions closed: " + why, priority="high")


JOURNAL = fx.JOURNAL_FIELDS + ["contract", "mode"]


def append_journal(path, row):
    """trader/journal.csv: semicolon CSV with decimal commas, one row per trade."""
    new = not os.path.exists(path)
    import csv
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        if new:
            w.writerow(JOURNAL)
        w.writerow([fx.nl(row.get(f)) for f in JOURNAL])


# ---------------------------------------------------------------- main loop

def run(engine, poll=10, max_errors=20, sleep=None):
    sleep = sleep or engine.b.sleep
    errors = 0
    while True:
        try:
            if not engine.b.connected():
                engine.notify("IBKR connection lost: reconnecting (stops and targets stay at IBKR)", priority="high")
                engine.b.reconnect()
                engine.notify("IBKR reconnected")
            if engine.tick() == "stop":
                return 0
            errors = 0
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise
        except Exception as e:  # keep running; tell the user
            errors += 1
            engine.notify("error (%d in a row): %s" % (errors, e), priority="high")
            if errors >= max_errors:
                engine.notify("too many errors in a row: stopping. Open positions keep their stop and target at "
                              "IBKR; check them in TWS or the IBKR app.", priority="urgent")
                return 1
            sleep(min(60, 5 * errors))
            continue
        sleep(poll)


def main(argv=None):
    p = argparse.ArgumentParser(description="trader-futures autotrader (IBKR)")
    p.add_argument("--mode", choices=["observe", "paper", "live"], required=True)
    p.add_argument("--config", default="trader/config.json")
    p.add_argument("--folder", default="trader")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int)
    p.add_argument("--client-id", type=int, default=17)
    p.add_argument("--poll", type=int, default=10)
    a = p.parse_args(argv)
    cfg = fx.load_config(a.config)
    notify = Notifier(cfg, os.path.join(a.folder, "state", "autotrader.log"))
    if os.path.exists(os.path.join(a.folder, "STOP")):
        print("trader/STOP exists: delete it to start.")
        return 1
    import ibkr
    port = a.port or (cfg.get("ibkr") or {}).get("port") or PORTS[a.mode]
    broker = ibkr.Broker(a.host, int(port), a.client_id, readonly=(a.mode == "observe"))
    try:
        broker.connect()
        eng = Engine(broker, cfg, a.mode, a.folder, notify)
        eng.setup()
        return run(eng, a.poll)
    except ibkr.BrokerError as e:
        notify("stopped: %s" % e, priority="high")
        return 1
    except KeyboardInterrupt:
        notify("stopped by you (Ctrl+C). Open positions keep their stop and target at IBKR.")
        return 0
    finally:
        try:
            broker.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
