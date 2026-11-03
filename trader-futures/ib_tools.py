#!/usr/bin/env python3
"""Small IBKR helpers for trader-futures (IB Gateway or TWS must be running).

  python3 ib_tools.py status                                   # account, paper or live, P&L, positions, contracts
  python3 ib_tools.py download --contract MES --days 60 --out trader/mes-5m.csv
  python3 ib_tools.py flatten  --contract MES                  # cancel its orders, close the position

download writes the CSV that `futures.py backtest --bars` reads, so you can
test the strategy on real IBKR data before it trades anything.
"""

import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import futures as fx  # noqa: E402
import ibkr  # noqa: E402

UTC = datetime.timezone.utc


def connect(a, readonly=True):
    cfg = fx.load_config(a.config)
    port = a.port or (cfg.get("ibkr") or {}).get("port") or 4002
    return ibkr.Broker(a.host, int(port), a.client_id, readonly=readonly).connect(), cfg


def cmd_status(a):
    b, cfg = connect(a)
    info = b.account_info()
    print("account %s (%s), base currency %s" % (info["account"], "PAPER" if info["paper"] else "LIVE", info["base"]))
    print("net liquidation %s, available funds %s" % (info["net_liq"], info["available"]))
    print("today's P&L EUR %s, EUR/USD %s, EUR per unit: %s" % (b.daily_pnl_eur(), b.eurusd(), b.rates_eur()))
    today = datetime.date.today()
    for key in cfg.get("contracts") or ["MES"]:
        spec = fx.spec_for(key, cfg)
        c, over = b.resolve(spec, today, int(cfg.get("roll_days", 8)))
        print("%s -> %s, expiry %s, %s per point, tick %s, position %d" % (
            key, over["local_symbol"], over["expiry"], over["multiplier"], over["tick"], b.position(c)))
        if (spec.get("execute_as") or cfg.get("execute_as")) == "cfd":
            cs = fx.cfd_spec(spec)
            cc, co = b.resolve_cfd(cs)
            print("   orders in CFD %s (%s), tick %s, quote %s, position %d" % (
                cs["symbol"], cs["currency"], co["tick"], b.quote_mid(cc), b.position(cc)))
    b.disconnect()
    return 0


def cmd_download(a):
    b, cfg = connect(a)
    spec = fx.spec_for(a.contract, cfg)
    c, over = b.resolve(spec, datetime.date.today(), int(cfg.get("roll_days", 8)))
    got = {}
    end = ""
    left = a.days
    while left > 0:
        chunk = min(10, left)
        raw = b.ib.reqHistoricalData(c, endDateTime=end, durationStr="%d D" % chunk, barSizeSetting="5 mins",
                                     whatToShow="TRADES", useRTH=False, formatDate=2, timeout=120)
        if not raw:
            break
        for r in raw:
            t = r.date if r.date.tzinfo else r.date.replace(tzinfo=UTC)
            got[t] = {"t": t.astimezone(UTC), "o": r.open, "h": r.high, "l": r.low, "c": r.close,
                      "v": float(r.volume or 0)}
        first = min(r.date for r in raw)
        end = first.astimezone(UTC).strftime("%Y%m%d-%H:%M:%S")
        left -= chunk
        b.sleep(11)   # IBKR pacing: no flood of historical requests
    bars = [got[k] for k in sorted(got)]
    fx.save_bars_csv(a.out, bars)
    print("%d bars of %s (%s) written to %s" % (len(bars), over["local_symbol"], key_name(spec), a.out))
    b.disconnect()
    return 0


def key_name(spec):
    return spec["name"]


def cmd_flatten(a):
    b, cfg = connect(a, readonly=False)
    spec = fx.spec_for(a.contract, cfg)
    c, over = b.resolve(spec, datetime.date.today(), int(cfg.get("roll_days", 8)))
    res = b.flatten(c)
    print("%s: closed %s at %s (%s)" % (over["local_symbol"], res.get("closed"), res.get("avg"), res.get("status", "")))
    b.disconnect()
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="IBKR helpers for trader-futures")
    p.add_argument("--config", default="trader/config.json")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int)
    p.add_argument("--client-id", type=int, default=18)
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status")
    d = sub.add_parser("download")
    d.add_argument("--contract", default="MES")
    d.add_argument("--days", type=int, default=30)
    d.add_argument("--out", required=True)
    f = sub.add_parser("flatten")
    f.add_argument("--contract", required=True)
    a = p.parse_args(argv)
    try:
        if a.cmd == "status":
            return cmd_status(a)
        if a.cmd == "download":
            return cmd_download(a)
        if a.cmd == "flatten":
            return cmd_flatten(a)
        p.print_help()
        return 2
    except (ibkr.BrokerError, fx.FuturesError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
