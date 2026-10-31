#!/usr/bin/env python3
"""Serve a local dashboard and run an allowlisted set of trader tools."""

import argparse
import json
import re
import secrets
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = Path(__file__).resolve().parent
TRADER_DIR = ROOT / "trader"
MAX_BODY = 8192
MAX_STATE_BYTES = 512 * 1024
MAX_OUTPUT_CHARS = 12000
MAX_JOBS = 100
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
JOBS = {}
JOBS_LOCK = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=2)

STATE_FILES = (
    "config.json",
    "watchlist.json",
    "news.json",
    "entry.json",
    "plan.json",
    "timemachine.json",
    "orders.json",
    "portfolio.json",
    "prices.json",
    "metrics.json",
    "universe.txt",
    "state/risk.json",
    "state/broker.json",
    "state/alerts.json",
    "state/pelosi.json",
)


class DashboardError(ValueError):
    """Raised when a dashboard task request is not supported."""


def _ticker(value):
    if not isinstance(value, str):
        raise DashboardError("Enter a ticker symbol.")
    symbol = value.strip().upper()
    if not TICKER_RE.fullmatch(symbol):
        raise DashboardError("Ticker must contain 1 to 10 letters, numbers, dots, or hyphens.")
    return symbol


def build_command(payload):
    """Translate a small task vocabulary into fixed local Python commands."""
    if not isinstance(payload, dict):
        raise DashboardError("Task request must be a JSON object.")

    task = payload.get("task")
    if not isinstance(task, str):
        raise DashboardError("Choose a supported dashboard task.")
    commands = {
        "scanner-daily": ["trader-scanner/scan.py", "daily"],
        "scanner-orb": ["trader-scanner/scan.py", "orb"],
        "exit-plan": ["trader-exit/exit.py", "plan", "--write"],
        "timemachine": ["trader-timemachine/timemachine.py", "run", "--write"],
        "budget": ["trader-budget/size.py", "--write"],
        "risk": ["trader-risk/check.py", "--json"],
        "tickets": ["trader-broker/ticket.py", "show"],
        "alerts-check": ["trader-alerts/alerts.py", "check"],
        "alerts-clock": ["trader-alerts/alerts.py", "clock"],
        "alerts-list": ["trader-alerts/alerts.py", "list"],
        "pelosi": ["trader-pelosi/ptr.py", "index", "--member", "pelosi"],
    }

    if task in ("news", "entry", "analyst"):
        symbol = _ticker(payload.get("symbol"))
        if task == "news":
            args = ["trader-news/news.py", "--tickers", symbol]
        elif task == "entry":
            args = ["trader-entry/entry.py", "check", symbol, "--write"]
        else:
            args = ["trader-analyst/facts.py", symbol, "--json"]
    elif task in commands:
        args = commands[task]
    else:
        raise DashboardError("That dashboard task is not available.")

    script, *arguments = args
    return [sys.executable, str(ROOT / script), *arguments]


def read_state():
    files = {}
    for relative in STATE_FILES:
        path = TRADER_DIR / relative
        item = {"exists": path.is_file()}
        if path.is_file():
            try:
                stat = path.stat()
                item["modified"] = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")
                if stat.st_size > MAX_STATE_BYTES:
                    item["error"] = "File exceeds the dashboard read limit."
                else:
                    text = path.read_text(encoding="utf-8")
                    if path.suffix == ".json":
                        item["data"] = json.loads(text)
                    else:
                        item["data"] = {"lines": sum(1 for line in text.splitlines() if line.strip())}
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                item["error"] = str(exc)
        files[relative] = item
    return {"files": files, "paper": _paper_mode(files)}


def _paper_mode(files):
    config = files.get("config.json", {}).get("data")
    if not isinstance(config, dict):
        return "unknown"
    return "paper" if config.get("paper") is True else "live" if config.get("paper") is False else "unknown"


def _run_job(job_id, command):
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "running"
        JOBS[job_id]["started"] = time.time()
    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            shell=False,
        )
        output = (result.stdout or "") + (("\n" + result.stderr) if result.stderr else "")
        status = "completed" if result.returncode == 0 else "finished"
        with JOBS_LOCK:
            JOBS[job_id].update(
                status=status,
                exit_code=result.returncode,
                output=output[-MAX_OUTPUT_CHARS:],
                finished=time.time(),
            )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        with JOBS_LOCK:
            JOBS[job_id].update(
                status="failed",
                error="Task exceeded the 10 minute limit.",
                output=output[-MAX_OUTPUT_CHARS:],
                finished=time.time(),
            )
    except OSError as exc:
        with JOBS_LOCK:
            JOBS[job_id].update(
                status="failed",
                error="Could not start the tool: %s" % exc,
                output="",
                finished=time.time(),
            )


class Handler(BaseHTTPRequestHandler):
    server_version = "DayTraderDashboard/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            self._json(200, read_state())
        elif path == "/":
            self._static("index.html", "text/html; charset=utf-8")
        elif path == "/app.js":
            self._static("app.js", "text/javascript; charset=utf-8")
        elif path == "/styles.css":
            self._static("styles.css", "text/css; charset=utf-8")
        elif path.startswith("/api/jobs/"):
            self._job(path[len("/api/jobs/"):])
        else:
            self._json(404, {"error": "Not found."})

    def do_POST(self):
        if urlparse(self.path).path != "/api/run":
            self._json(404, {"error": "Not found."})
            return
        if not self._same_origin():
            self._json(403, {"error": "Dashboard tasks must come from this local dashboard."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 1 or length > MAX_BODY:
            self._json(413, {"error": "Task request is empty or too large."})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            command = build_command(payload)
        except (UnicodeError, json.JSONDecodeError, DashboardError) as exc:
            self._json(400, {"error": str(exc)})
            return

        job_id = secrets.token_urlsafe(9)
        with JOBS_LOCK:
            job_key = (payload["task"], payload.get("symbol", "").strip().upper())
            if any(
                job.get("key") == job_key and job.get("status") in ("queued", "running")
                for job in JOBS.values()
            ):
                self._json(409, {"error": "That task is already running for this input."})
                return
            if len(JOBS) >= MAX_JOBS:
                finished = sorted(
                    (job for job in JOBS.values() if job.get("status") not in ("queued", "running")),
                    key=lambda job: job.get("created", 0),
                )
                for job in finished[:len(JOBS) - MAX_JOBS + 1]:
                    JOBS.pop(job["id"], None)
            if len(JOBS) >= MAX_JOBS:
                self._json(503, {"error": "Task history is full. Restart the dashboard to clear completed tasks."})
                return
            JOBS[job_id] = {
                "id": job_id,
                "task": payload["task"],
                "key": job_key,
                "status": "queued",
                "created": time.time(),
                "output": "",
            }
        POOL.submit(_run_job, job_id, command)
        self._json(202, {"id": job_id, "status": "queued"})

    def _same_origin(self):
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if not origin or not host:
            return False
        try:
            parsed = urlparse(origin)
            return (
                parsed.scheme == "http"
                and parsed.hostname in ("127.0.0.1", "localhost")
                and parsed.netloc == host
                and self.client_address[0] in ("127.0.0.1", "::1")
            )
        except ValueError:
            return False

    def _static(self, filename, content_type):
        try:
            content = (DASHBOARD / filename).read_bytes()
        except OSError:
            self._json(500, {"error": "Dashboard asset is unavailable."})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _job(self, job_id):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job:
                job = dict(job)
        if job is None:
            self._json(404, {"error": "Task result was not found. Restarted dashboards do not retain job history."})
        else:
            self._json(200, job)

    def _json(self, code, payload):
        content = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main():
    parser = argparse.ArgumentParser(description="Run the local day-trading dashboard.")
    parser.add_argument("--port", type=int, default=8765, help="Local port to use (default: 8765)")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("Dashboard available at http://127.0.0.1:%d" % args.port)
    print("Local only. Broker orders are not available in this dashboard.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        server.server_close()
        POOL.shutdown(wait=False)


if __name__ == "__main__":
    main()
