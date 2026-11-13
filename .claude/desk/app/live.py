"""Live parts of the Trading Desk app: Alpaca (read-only, paper), the desk chat
(a headless Claude Code trader), and the supervisor for the desk agents' loops.

Standard library only. Keys live in %APPDATA%/TradingDesk/alpaca.json on this
PC (never in the repo, never sent anywhere but Alpaca's paper API).
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
APPDIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "TradingDesk")
PAPER_API = "https://paper-api.alpaca.markets"   # paper only, by design: no live URL anywhere
DATA_API = "https://data.alpaca.markets"
VERSION = {"n": 0}
_vlock = threading.Lock()


def python_exe():
    """The Python that runs the repo's scripts. Inside TradingDesk.exe sys.executable is the exe itself."""
    if not getattr(sys, "frozen", False):
        return sys.executable
    return shutil.which("python3") or shutil.which("python") or shutil.which("py") or "python"


def bump():
    with _vlock:
        VERSION["n"] += 1


# ------------------------------------------------------------------ alpaca (read-only)

def keys_path():
    return os.path.join(APPDIR, "alpaca.json")


def load_keys():
    try:
        with open(keys_path(), encoding="utf-8") as fh:
            k = json.load(fh)
        return k if k.get("key_id") and k.get("secret") else None
    except (OSError, ValueError):
        return None


def save_keys(key_id, secret):
    key_id, secret = (key_id or "").strip(), (secret or "").strip()
    if not key_id or not secret:
        raise ValueError("both the key ID and the secret are needed")
    if not key_id.startswith("PK"):
        raise ValueError("that does not look like a PAPER key (paper key IDs start with PK)")
    os.makedirs(APPDIR, exist_ok=True)
    tmp = keys_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"key_id": key_id, "secret": secret, "paper": True}, fh)
    os.replace(tmp, keys_path())
    ALPACA.update({"error": None, "ok": False})
    bump()


def forget_keys():
    try:
        os.remove(keys_path())
    except OSError:
        pass
    ALPACA.update({"ok": False, "account": None, "positions": [], "orders": [], "error": None})
    bump()


def _get(base, path, keys, timeout=8):
    req = urllib.request.Request(base + path, headers={
        "APCA-API-KEY-ID": keys["key_id"], "APCA-API-SECRET-KEY": keys["secret"], "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


ALPACA = {"ok": False, "error": None, "account": None, "positions": [], "orders": [], "quotes": {},
          "updated": None}
WATCH_SYMBOLS = {"SPY"}


def _slim_order(o):
    keep = ("id", "symbol", "side", "qty", "filled_qty", "filled_avg_price", "type", "order_type", "status",
            "stop_price", "limit_price", "order_class", "submitted_at", "filled_at", "canceled_at", "group_role")
    s = {k: o.get(k) for k in keep}
    s["legs"] = [_slim_order(x) for x in (o.get("legs") or [])]
    return s


def alpaca_loop():
    """Poll the paper account every 2 s (orders every 4 s, quotes every 2 s). Push only when something changed."""
    tick = 0
    while True:
        keys = load_keys()
        if not keys:
            if ALPACA["ok"] or ALPACA["account"]:
                ALPACA.update({"ok": False, "account": None, "positions": [], "orders": []})
                bump()
            time.sleep(2)
            continue
        try:
            before = json.dumps([ALPACA["account"], ALPACA["positions"], ALPACA["orders"], ALPACA["quotes"]],
                                sort_keys=True, default=str)
            acct = _get(PAPER_API, "/v2/account", keys)
            ALPACA["account"] = {k: acct.get(k) for k in ("account_number", "status", "equity", "last_equity", "cash",
                                                          "buying_power", "portfolio_value", "trading_blocked")}
            pos = _get(PAPER_API, "/v2/positions", keys)
            ALPACA["positions"] = [{k: p.get(k) for k in ("symbol", "qty", "avg_entry_price", "current_price",
                                                           "market_value", "unrealized_pl", "unrealized_plpc",
                                                           "change_today")} for p in pos]
            if tick % 2 == 0:
                day = dt.datetime.now(NY).replace(hour=4, minute=0, second=0, microsecond=0)
                after = day.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                orders = _get(PAPER_API, "/v2/orders?status=all&nested=true&limit=100&after=" + after, keys)
                ALPACA["orders"] = [_slim_order(o) for o in orders]
            syms = sorted(WATCH_SYMBOLS | {p["symbol"] for p in ALPACA["positions"]})
            q = _get(DATA_API, "/v2/stocks/trades/latest?feed=iex&symbols=" + ",".join(syms), keys)
            ALPACA["quotes"] = {s: {"p": t.get("p"), "t": t.get("t")} for s, t in (q.get("trades") or {}).items()}
            ALPACA.update({"ok": True, "error": None, "updated": dt.datetime.now(NY).isoformat(timespec="seconds")})
            after_s = json.dumps([ALPACA["account"], ALPACA["positions"], ALPACA["orders"], ALPACA["quotes"]],
                                 sort_keys=True, default=str)
            if after_s != before:
                bump()
        except urllib.error.HTTPError as e:
            msg = "Alpaca answered HTTP %d%s" % (e.code, " (check the keys)" if e.code in (401, 403) else "")
            if ALPACA["error"] != msg:
                ALPACA.update({"ok": False, "error": msg})
                bump()
        except (OSError, ValueError) as e:
            msg = "Alpaca unreachable: %s" % e
            if ALPACA["error"] != msg:
                ALPACA.update({"ok": False, "error": msg})
                bump()
        tick += 1
        time.sleep(2)


def alpaca_state():
    out = dict(ALPACA)
    out["configured"] = load_keys() is not None
    k = load_keys()
    out["key_hint"] = (k["key_id"][:4] + "…" + k["key_id"][-3:]) if k else None
    return out


# ------------------------------------------------------------------ desk chat (headless Claude trader)

CHAT = {"running": False, "partial": "", "tools": [], "started": None, "error": None, "proc": None}
TRADER_PROMPT = """You are the Trading Desk app's chat trader, talking to the user directly in the desk app.
Follow CLAUDE.md and MACHINE_LEARNING.md in this repo. PAPER account only; never switch anything to live.
You may research, answer, and open, adjust or close PAPER trades when the user asks or when it clearly fits the
plan, but every entry goes through the pipeline: trader-exit plan -> trader-budget size.py --write ->
trader-risk check.py PASS -> `python3 trader-broker/ticket.py approve --index N --auto --who app` (this takes the
shared order lock; if another trader holds it, wait and retry) -> place_stock_order with exactly the ticket JSON ->
`ticket.py result ... --who app` (releases the lock). Record fills with ticket.py fill. Respect the daily limits.
The main Claude session also trades; never undo its orders without saying so. Be brief: the user reads you in a
small chat panel. Times in New York (zoneinfo), never TZ=."""
ALLOWED = ["Bash", "Read", "Grep", "Glob", "mcp__alpaca"]
DISALLOWED = ["mcp__alpaca__close_all_positions", "mcp__alpaca__cancel_all_orders",
              "mcp__alpaca__place_option_order", "mcp__alpaca__place_crypto_order",
              "mcp__alpaca__exercise_options_position", "mcp__alpaca__do_not_exercise_options_position",
              "mcp__alpaca__update_account_config"]


def chat_log_path(desk):
    return os.path.join(desk, "app-chat.jsonl")


def chat_history(desk, limit=60):
    rows = []
    try:
        with open(chat_log_path(desk), encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows[-limit:]


def _append(desk, rec):
    os.makedirs(desk, exist_ok=True)
    with open(chat_log_path(desk), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def claude_exe():
    return shutil.which("claude") or shutil.which("claude.cmd")


def ask(root, desk, text):
    text = (text or "").strip()
    if not text:
        raise ValueError("empty message")
    if CHAT["running"]:
        raise ValueError("Claude is still answering the last message")
    exe = claude_exe()
    if not exe:
        raise ValueError("the Claude Code CLI (claude) is not installed on this PC")
    sess_file = os.path.join(desk, "app-chat.session")
    sid = None
    try:
        with open(sess_file, encoding="utf-8") as fh:
            sid = fh.read().strip() or None
    except OSError:
        pass
    args = [exe, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
            "--append-system-prompt", TRADER_PROMPT, "--allowedTools", *ALLOWED, "--disallowedTools", *DISALLOWED]
    if sid:
        args += ["--resume", sid]
    _append(desk, {"role": "user", "text": text, "at": dt.datetime.now(NY).isoformat(timespec="seconds")})
    CHAT.update({"running": True, "partial": "", "tools": [], "started": time.time(), "error": None})
    bump()

    def run():
        final, cost = "", None
        try:
            p = subprocess.Popen(args, cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            CHAT["proc"] = p
            p.stdin.write(text)
            p.stdin.close()
            last_push = 0
            for line in p.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                t = ev.get("type")
                if t == "system" and ev.get("subtype") == "init" and ev.get("session_id"):
                    with open(sess_file, "w", encoding="utf-8") as fh:
                        fh.write(ev["session_id"])
                elif t == "stream_event":
                    e = ev.get("event") or {}
                    d = e.get("delta") or {}
                    if e.get("type") == "content_block_delta" and d.get("type") == "text_delta":
                        CHAT["partial"] += d.get("text", "")
                    elif e.get("type") == "content_block_start" and (e.get("content_block") or {}).get("type") == "tool_use":
                        CHAT["tools"].append(e["content_block"].get("name"))
                        CHAT["partial"] += "\n"
                elif t == "result":
                    final = ev.get("result") or ""
                    cost = ev.get("total_cost_usd")
                    if ev.get("is_error"):
                        CHAT["error"] = final or "Claude reported an error"
                if time.time() - last_push > 0.15:
                    bump()
                    last_push = time.time()
            p.wait(timeout=30)
            if p.returncode and not final:
                CHAT["error"] = (p.stderr.read() or "claude exited with %s" % p.returncode)[-400:]
        except Exception as e:  # noqa: BLE001
            CHAT["error"] = str(e)
        _append(desk, {"role": "assistant", "text": final or CHAT["partial"] or "", "tools": CHAT["tools"][-20:],
                       "error": CHAT["error"], "cost_usd": cost,
                       "at": dt.datetime.now(NY).isoformat(timespec="seconds")})
        CHAT.update({"running": False, "proc": None})
        bump()

    threading.Thread(target=run, daemon=True).start()
    return "sent"


def stop_chat():
    p = CHAT.get("proc")
    if p and p.poll() is None:
        p.terminate()
    return "stopped"


def reset_chat(desk):
    try:
        os.remove(os.path.join(desk, "app-chat.session"))
    except OSError:
        pass
    _append(desk, {"role": "system", "text": "New conversation", "at": dt.datetime.now(NY).isoformat(timespec="seconds")})
    bump()
    return "new conversation"


def chat_state(desk):
    return {"history": chat_history(desk), "running": CHAT["running"], "partial": CHAT["partial"],
            "tools": CHAT["tools"][-12:], "error": CHAT["error"], "available": claude_exe() is not None}


# ------------------------------------------------------------------ agent loop supervisor

PROCS = {}


def loop_script(desk, agent):
    p = os.path.join(desk, agent, "loop.py")
    return p if os.path.exists(p) else None


def start_agent(root, desk, agent):
    script = loop_script(desk, agent)
    if not script:
        raise ValueError("%s has no loop script yet (trader/desk/%s/loop.py); ask Claude to build one" % (agent, agent))
    pr = PROCS.get(agent)
    if pr and pr.poll() is None:
        return "%s is already running (started by this app)" % agent
    log = open(os.path.join(desk, agent, "loop.log"), "a", encoding="utf-8")
    PROCS[agent] = subprocess.Popen([python_exe(), "-u", script], cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    bump()
    return "%s started" % agent


def stop_agent(agent):
    pr = PROCS.get(agent)
    if pr and pr.poll() is None:
        pr.terminate()
        bump()
        return "%s stopped" % agent
    return "%s was not started by this app; use Pause, or Stop desk" % agent


def agent_proc_state(desk, agent):
    pr = PROCS.get(agent)
    return {"has_loop": loop_script(desk, agent) is not None,
            "owned": bool(pr and pr.poll() is None)}


def agent_log(desk, agent, lines=80):
    p = os.path.join(desk, agent, "loop.log")
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return "".join(fh.readlines()[-lines:])
    except OSError:
        return "(no loop.log)"


# ------------------------------------------------------------------ connections

_claude = {"at": 0, "data": None}


def claude_status(force=False):
    """Claude Code CLI login (the user's Claude subscription). Cached 60 s. No email or org is returned."""
    if not force and _claude["data"] is not None and time.time() - _claude["at"] < 60:
        return _claude["data"]
    exe = claude_exe()
    data = {"installed": exe is not None, "logged_in": False}
    if exe:
        try:
            r = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=25,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            j = json.loads(r.stdout)
            data.update({"logged_in": bool(j.get("loggedIn")), "method": j.get("authMethod"),
                         "plan": j.get("subscriptionType"), "expires": j.get("loginExpiresAt")})
        except Exception as e:  # noqa: BLE001
            data["error"] = str(e)[:200]
    _claude.update({"at": time.time(), "data": data})
    return data


def claude_login(logout=False):
    """Opens a terminal window on this PC running the CLI's own login; the app never sees the credentials."""
    exe = claude_exe()
    if not exe:
        raise ValueError("install Claude Code first: npm install -g @anthropic-ai/claude-code")
    subprocess.Popen(["cmd", "/c", "start", "Claude login", "cmd", "/k", exe, "auth", "logout" if logout else "login"])
    _claude["at"] = 0
    return "A terminal window opened: finish there, then press Refresh."


def conn_path():
    return os.path.join(APPDIR, "connections.json")


def connections():
    try:
        with open(conn_path(), encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    return [{"name": k, "hint": (v.get("key", "")[:3] + "…" + v.get("key", "")[-2:]) if v.get("key") else "",
             "note": v.get("note", "")} for k, v in sorted(d.items())]


def save_connection(name, key, note="", remove=False):
    name = (name or "").strip()[:40]
    if not name:
        raise ValueError("give the connection a name")
    try:
        with open(conn_path(), encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    if remove:
        d.pop(name, None)
    else:
        if not (key or "").strip():
            raise ValueError("paste the API key")
        d[name] = {"key": key.strip(), "note": (note or "")[:120]}
    os.makedirs(APPDIR, exist_ok=True)
    with open(conn_path(), "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=2)
    bump()
    return "Removed %s." % name if remove else "Saved %s on this PC." % name
