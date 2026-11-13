"""Trading Desk: a local desktop control room for the day-trader desk.

    python3 .claude/desk/app/server.py            # serves http://127.0.0.1:8765 and opens an app window
    python3 .claude/desk/app/server.py --no-open  # just serve

Reads the desk agents' reports (trader/desk/*.json), the ticket log, the
portfolio, the config and this project's Claude Code transcript; serves 5-minute
charts from Yahoo; and writes only control files: trader/desk/STOP,
trader/desk/PAUSE-<agent>, trader/desk/inbox.jsonl (messages for the main
agent), and the autotrade switch (via trader-broker/ticket.py auto).

It never talks to the broker and never places an order. It binds to 127.0.0.1
only, and every POST needs the per-launch token the page was served with.
Standard library only.
"""
import argparse
import datetime as dt
import glob
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DESK = os.path.join(ROOT, "trader", "desk")
NY = ZoneInfo("America/New_York")
TOKEN = secrets.token_urlsafe(24)
AGENTS = ["desk-alerts", "desk-broker", "desk-risk", "desk-exit", "desk-entry", "desk-budget",
          "desk-scanner", "desk-news", "desk-analyst", "desk-pelosi", "desk-timemachine"]
SKILL = {a: "trader-" + a.split("-", 1)[1] for a in AGENTS}
AUTO_TOOLS = ["mcp__alpaca__place_stock_order", "mcp__alpaca__cancel_order_by_id",
              "mcp__alpaca__replace_order_by_id"]
PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
sys.path.insert(0, os.path.join(ROOT, "trader-scanner"))


def p(*parts):
    return os.path.join(ROOT, *parts)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def now_ny():
    return dt.datetime.now(NY)


def parse_time(s):
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=NY)
    except ValueError:
        return None


# ------------------------------------------------------------------ state

def market_clock(n):
    wd = n.weekday() < 5
    o = n.replace(hour=9, minute=30, second=0, microsecond=0)
    c = n.replace(hour=16, minute=0, second=0, microsecond=0)
    if wd and o <= n < c:
        return {"open": True, "label": "Market open", "closes_in_min": int((c - n).total_seconds() // 60)}
    return {"open": False, "label": "Market closed" if wd and n >= c or not wd else "Pre-market"}


def agents_state(n):
    out = []
    for name in AGENTS:
        r = read_json(os.path.join(DESK, name + ".json"), None)
        paused = os.path.exists(os.path.join(DESK, "PAUSE-" + name))
        if r is None:
            out.append({"name": name, "skill": SKILL[name], "status": "missing", "headline": "no report yet",
                        "paused": paused, "items": [], "recommendations": []})
            continue
        t = parse_time(r.get("updated"))
        age = max(0, int((n - t).total_seconds())) if t else None
        cad = r.get("cadence_seconds") or 600
        st = r.get("status", "?")
        out.append({"name": name, "skill": SKILL[name], "status": st, "headline": r.get("headline", ""),
                    "updated": r.get("updated"), "age_s": age, "cadence_s": cad, "cycle": r.get("cycle"),
                    "stale": bool(age is not None and st != "done" and age > 2 * cad), "paused": paused,
                    "items": (r.get("items") or [])[:25], "recommendations": r.get("recommendations") or []})
    return out


def autotrade_state(cfg):
    settings = read_json(p(".claude", "settings.local.json"), {}) or {}
    allow = (settings.get("permissions") or {}).get("allow") or []
    tools = [t for t in AUTO_TOOLS if t in allow]
    on = bool(cfg.get("auto_approve")) and len(tools) == len(AUTO_TOOLS)
    partly = not on and (bool(cfg.get("auto_approve")) or bool(tools))
    return {"on": on, "partly": partly, "auto_approve": bool(cfg.get("auto_approve")),
            "tools": [t.split("__")[-1] for t in tools]}


def trades_today(rows):
    """FIFO-pair today's fills into round trips; realized P/L timeline."""
    fills = sorted([r for r in rows if r.get("status") == "filled" and r.get("price") is not None],
                   key=lambda r: r.get("at", ""))
    open_lots, trips, timeline, cum = {}, [], [], 0.0
    for f in fills:
        sym, side = f.get("symbol"), f.get("side")
        q, px = float(f.get("qty") or 0), float(f.get("price"))
        if side == "buy":
            open_lots.setdefault(sym, []).append({"qty": q, "price": px, "at": f.get("at")})
            continue
        lots, left, pnl, entry_at, cost = open_lots.get(sym, []), q, 0.0, None, 0.0
        while left > 1e-9 and lots:
            lot = lots[0]
            take = min(left, lot["qty"])
            pnl += (px - lot["price"]) * take
            cost += lot["price"] * take
            entry_at = entry_at or lot["at"]
            lot["qty"] -= take
            left -= take
            if lot["qty"] <= 1e-9:
                lots.pop(0)
        cum += pnl
        trips.append({"symbol": sym, "qty": q, "entry": round(cost / q, 4) if q else None, "entry_at": entry_at,
                      "exit": px, "exit_at": f.get("at"), "pnl": round(pnl, 2)})
        timeline.append({"at": f.get("at"), "cum": round(cum, 2), "symbol": sym})
    still = [{"symbol": s, "qty": sum(l["qty"] for l in ls), "entry": ls[0]["price"], "entry_at": ls[0]["at"]}
             for s, ls in open_lots.items() if ls and sum(l["qty"] for l in ls) > 1e-9]
    return trips, timeline, round(cum, 2), still


def build_state():
    n = now_ny()
    today = n.date().isoformat()
    cfg = read_json(p("trader", "config.json"), {}) or {}
    pf = read_json(p("trader", "portfolio.json"), {}) or {}
    log = (read_json(p("trader", "state", "broker.json"), {}) or {}).get("orders", [])
    rows = [r for r in log if (r.get("date") or str(r.get("at", ""))[:10]) == today]
    canceled = {r.get("broker_order_id") for r in rows if r.get("status") == "canceled"}
    entries = [r for r in rows if r.get("status") == "placed" and r.get("kind") == "entry"
               and r.get("broker_order_id") not in canceled]
    used = round(sum(float(r.get("max_loss") or 0) for r in entries), 2)
    trips, timeline, realized, still = trades_today(rows)
    agents = agents_state(n)
    day_pl = None
    for a in agents:
        if a["name"] == "desk-risk":
            for it in a["items"]:
                if isinstance(it, dict) and "day_pl" in it:
                    day_pl = it["day_pl"]
    gate = None
    for a in agents:
        if a["name"] == "desk-alerts":
            for it in a["items"]:
                if isinstance(it, dict) and "breakouts_allowed" in it:
                    gate = {"allowed": it.get("breakouts_allowed"), "spy_vs_open_pct": it.get("spy_vs_open_pct")}
    inbox = read_inbox()
    return {
        "now": n.isoformat(timespec="seconds"), "clock": market_clock(n),
        "account": {"paper": cfg.get("paper", True) is True, "broker": cfg.get("broker", "alpaca"),
                    "cash": pf.get("cash"), "positions": pf.get("positions") or []},
        "limits": {"budget": cfg.get("budget"), "max_loss_per_trade": cfg.get("max_loss_per_trade_usd"),
                   "max_daily_loss": cfg.get("max_daily_loss_usd"), "max_trades": cfg.get("max_trades_per_day"),
                   "entries_from": cfg.get("no_entries_before"), "entries_until": cfg.get("no_entries_after"),
                   "flat_by": cfg.get("flat_by")},
        "risk": {"used": used, "entries": len(entries), "realized": realized, "day_pl": day_pl},
        "autotrade": autotrade_state(cfg), "desk_stopped": os.path.exists(os.path.join(DESK, "STOP")),
        "gate": gate, "agents": agents, "trades": trips, "open_trips": still, "pnl_timeline": timeline,
        "log": [{"at": r.get("at"), "status": r.get("status"), "symbol": r.get("symbol"), "side": r.get("side"),
                 "plain": r.get("plain"), "note": r.get("note"), "max_loss": r.get("max_loss")}
                for r in rows][-60:],
        "inbox": inbox[-20:],
    }


# ------------------------------------------------------------------ chart

_bar_cache = {}


def bars(symbol, interval="5m", rng="1d"):
    key = (symbol, interval, rng)
    hit = _bar_cache.get(key)
    if hit and time.time() - hit[0] < 20:
        return hit[1]
    import scan  # trader-scanner's Yahoo helpers
    doc = json.loads(scan.yahoo_get("/v8/finance/chart/%s?range=%s&interval=%s" % (scan.to_yahoo(symbol), rng, interval)))
    res = (doc.get("chart") or {}).get("result") or []
    if not res:
        raise ValueError("no chart data for %s" % symbol)
    s = scan.series_from_result(res[0])
    out = []
    for i, t in enumerate(s["t"]):
        o, h, l, c = (s["o"] or [None])[i], (s["h"] or [None])[i], (s["l"] or [None])[i], s["c"][i]
        if None in (o, h, l, c):
            continue
        out.append({"time": int(t), "open": round(o, 4), "high": round(h, 4), "low": round(l, 4),
                    "close": round(c, 4), "volume": int((s["v"] or [0])[i] or 0)})
    meta = s.get("meta") or {}
    data = {"symbol": symbol.upper(), "bars": out, "prev_close": meta.get("chartPreviousClose") or meta.get("previousClose")}
    _bar_cache[key] = (time.time(), data)
    return data


def chart_overlay(symbol):
    today = now_ny().date().isoformat()
    log = (read_json(p("trader", "state", "broker.json"), {}) or {}).get("orders", [])
    marks, lines = [], []
    for r in log:
        if (r.get("date") or str(r.get("at", ""))[:10]) != today or str(r.get("symbol", "")).upper() != symbol.upper():
            continue
        t = parse_time(r.get("at"))
        if r.get("status") == "filled" and t:
            marks.append({"time": int(t.timestamp()), "side": r.get("side"), "price": r.get("price"),
                          "text": "%s %s @ %s" % (r.get("side", "").upper(), r.get("qty"), r.get("price"))})
    pf = read_json(p("trader", "portfolio.json"), {}) or {}
    held = any(str(x.get("symbol", "")).upper() == symbol.upper() for x in pf.get("positions") or [])
    if held:
        for r in reversed(log):
            if str(r.get("symbol", "")).upper() == symbol.upper() and r.get("status") == "placed" and r.get("kind") == "entry":
                if r.get("stop") is not None:
                    lines.append({"price": r["stop"], "label": "stop"})
                txt = r.get("plain") or ""
                if "take-profit" in txt:
                    try:
                        lines.append({"price": float(txt.split("take-profit")[1].split("/")[0].strip()), "label": "target"})
                    except ValueError:
                        pass
                break
    return marks, lines


# ------------------------------------------------------------------ chat

def transcript_path():
    folder = os.path.join(PROJECTS, ROOT.replace(":", "-").replace("\\", "-").replace("/", "-"))
    files = [f for f in glob.glob(os.path.join(folder, "*.jsonl"))]
    return max(files, key=os.path.getmtime) if files else None


def _text_of(content):
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
    return "\n".join(parts)


def chat_tail(limit=60, max_bytes=3_000_000):
    path = transcript_path()
    if not path:
        return {"path": None, "messages": []}
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        if size > max_bytes:
            fh.seek(size - max_bytes)
            fh.readline()
        raw = fh.read().decode("utf-8", "replace").splitlines()
    msgs = []
    for line in raw:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("isSidechain") or d.get("type") not in ("user", "assistant"):
            continue
        m = d.get("message") or {}
        c = m.get("content")
        if d["type"] == "user":
            if d.get("isMeta") or (isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c)):
                continue
            text = _text_of(c).strip()
            if not text or text.startswith("<") and ("system-reminder" in text[:40] or "task-notification" in text[:40]
                                                     or "local-command" in text[:40] or "command-name" in text[:40]):
                continue
            msgs.append({"role": "user", "text": text, "at": d.get("timestamp")})
        else:
            text = _text_of(c).strip()
            tools = [b.get("name") for b in (c or []) if isinstance(b, dict) and b.get("type") == "tool_use"]
            if not text and not tools:
                continue
            if msgs and msgs[-1]["role"] == "assistant":
                last = msgs[-1]
                if text:
                    last["text"] = (last["text"] + "\n\n" + text).strip()
                last["tools"] += tools
                last["at"] = d.get("timestamp") or last["at"]
            else:
                msgs.append({"role": "assistant", "text": text, "tools": tools, "at": d.get("timestamp")})
    for mm in msgs:
        if mm["role"] == "assistant":
            mm["tools"] = mm["tools"][-12:]
    return {"path": os.path.basename(path), "messages": msgs[-limit:]}


def read_inbox():
    rows = []
    try:
        with open(os.path.join(DESK, "inbox.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    cursor = (read_json(os.path.join(DESK, "inbox.cursor.json"), {}) or {}).get("read", 0)
    for i, r in enumerate(rows):
        r["read"] = i < cursor
    return rows


# ------------------------------------------------------------------ control

def control(action, agent=None):
    os.makedirs(DESK, exist_ok=True)
    if action == "stop_all":
        open(os.path.join(DESK, "STOP"), "w").close()
        return "Desk STOP set: every agent ends after its current cycle."
    if action == "clear_stop":
        try:
            os.remove(os.path.join(DESK, "STOP"))
        except OSError:
            pass
        return "STOP cleared. Ask Claude to relaunch the agents that ended."
    if action in ("pause", "resume"):
        if agent not in AGENTS:
            raise ValueError("unknown agent")
        f = os.path.join(DESK, "PAUSE-" + agent)
        if action == "pause":
            open(f, "w").close()
            return "%s paused (it skips its work until resumed)." % agent
        try:
            os.remove(f)
        except OSError:
            pass
        return "%s resumed." % agent
    if action in ("autotrade_on", "autotrade_off"):
        r = subprocess.run([sys.executable, p("trader-broker", "ticket.py"), "auto", action.split("_")[1]],
                           cwd=ROOT, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise ValueError((r.stderr or r.stdout).strip() or "ticket.py auto failed")
        return r.stdout.strip().splitlines()[0]
    raise ValueError("unknown action")


def post_message(text):
    text = (text or "").strip()
    if not text:
        raise ValueError("empty message")
    os.makedirs(DESK, exist_ok=True)
    rec = {"at": now_ny().isoformat(timespec="seconds"), "from": "desk-app", "text": text[:4000]}
    with open(os.path.join(DESK, "inbox.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return "Queued for Claude. It is read at the main agent's next desk check (every few minutes)."


# ------------------------------------------------------------------ http

class Handler(BaseHTTPRequestHandler):
    server_version = "TradingDesk/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else (json.dumps(body) if ctype == "application/json" else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), encoding="utf-8") as fh:
                    return self._send(200, fh.read().replace("__DESK_TOKEN__", TOKEN), "text/html")
            if u.path == "/api/state":
                return self._send(200, build_state())
            if u.path == "/api/bars":
                sym = (q.get("symbol") or "SPY").upper()[:12]
                data = bars(sym, q.get("interval", "5m"), q.get("range", "1d"))
                data["marks"], data["lines"] = chart_overlay(sym)
                return self._send(200, data)
            if u.path == "/api/chat":
                return self._send(200, chat_tail(int(q.get("limit", 60))))
            return self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        origin = self.headers.get("Origin")
        host_ok = origin in (None, "http://127.0.0.1:%d" % self.server.server_port,
                             "http://localhost:%d" % self.server.server_port)
        if self.headers.get("X-Desk-Token") != TOKEN or not host_ok:
            return self._send(403, {"error": "forbidden"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(n, 20000)) or b"{}")
            if self.path == "/api/control":
                return self._send(200, {"ok": True, "message": control(body.get("action"), body.get("agent"))})
            if self.path == "/api/chat":
                return self._send(200, {"ok": True, "message": post_message(body.get("text"))})
            return self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            return self._send(400, {"ok": False, "error": str(e)})


def open_window(url):
    edge = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    chrome = [r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
    for exe in edge + chrome:
        if os.path.exists(exe):
            subprocess.Popen([exe, "--app=" + url, "--window-size=1600,1000"])
            return
    webbrowser.open(url)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Trading Desk app (local only)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    url = "http://127.0.0.1:%d/" % a.port
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    except OSError:
        print("Trading Desk is already running on %s; opening the window." % url, flush=True)
        if not a.no_open:
            open_window(url)
        return 0
    print("Trading Desk on %s (Ctrl+C to stop)" % url, flush=True)
    if not a.no_open:
        threading.Timer(0.8, open_window, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
