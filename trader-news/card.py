#!/usr/bin/env python3
"""Create an informational market-analysis PNG and traceable JSON.

This tool only reports public market data and scanner/news matches. It does
not recommend trades, size positions, place orders, or connect to a broker.
"""

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import struct
import sys
import zlib


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_skill(name, filename):
    path = os.path.join(ROOT, name, filename)
    spec = importlib.util.spec_from_file_location("card_" + name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scan = load_skill("trader-scanner", "scan.py")
news = load_skill("trader-news", "news.py")


FONT = {
    "A": ("01110","10001","10001","11111","10001","10001","10001"),
    "B": ("11110","10001","10001","11110","10001","10001","11110"),
    "C": ("01111","10000","10000","10000","10000","10000","01111"),
    "D": ("11110","10001","10001","10001","10001","10001","11110"),
    "E": ("11111","10000","10000","11110","10000","10000","11111"),
    "F": ("11111","10000","10000","11110","10000","10000","10000"),
    "G": ("01111","10000","10000","10111","10001","10001","01111"),
    "H": ("10001","10001","10001","11111","10001","10001","10001"),
    "I": ("11111","00100","00100","00100","00100","00100","11111"),
    "J": ("00111","00010","00010","00010","10010","10010","01100"),
    "K": ("10001","10010","10100","11000","10100","10010","10001"),
    "L": ("10000","10000","10000","10000","10000","10000","11111"),
    "M": ("10001","11011","10101","10101","10001","10001","10001"),
    "N": ("10001","11001","10101","10011","10001","10001","10001"),
    "O": ("01110","10001","10001","10001","10001","10001","01110"),
    "P": ("11110","10001","10001","11110","10000","10000","10000"),
    "Q": ("01110","10001","10001","10001","10101","10010","01101"),
    "R": ("11110","10001","10001","11110","10100","10010","10001"),
    "S": ("01111","10000","10000","01110","00001","00001","11110"),
    "T": ("11111","00100","00100","00100","00100","00100","00100"),
    "U": ("10001","10001","10001","10001","10001","10001","01110"),
    "V": ("10001","10001","10001","10001","10001","01010","00100"),
    "W": ("10001","10001","10001","10101","10101","10101","01010"),
    "X": ("10001","10001","01010","00100","01010","10001","10001"),
    "Y": ("10001","10001","01010","00100","00100","00100","00100"),
    "Z": ("11111","00001","00010","00100","01000","10000","11111"),
    "0": ("01110","10001","10011","10101","11001","10001","01110"),
    "1": ("00100","01100","00100","00100","00100","00100","01110"),
    "2": ("01110","10001","00001","00010","00100","01000","11111"),
    "3": ("11110","00001","00001","01110","00001","00001","11110"),
    "4": ("00010","00110","01010","10010","11111","00010","00010"),
    "5": ("11111","10000","10000","11110","00001","00001","11110"),
    "6": ("01110","10000","10000","11110","10001","10001","01110"),
    "7": ("11111","00001","00010","00100","01000","01000","01000"),
    "8": ("01110","10001","10001","01110","10001","10001","01110"),
    "9": ("01110","10001","10001","01111","00001","00001","01110"),
    ":": ("00000","00100","00100","00000","00100","00100","00000"),
    ".": ("00000","00000","00000","00000","00000","00100","00100"),
    "-": ("00000","00000","00000","11111","00000","00000","00000"),
    "/": ("00001","00010","00010","00100","01000","01000","10000"),
    "%": ("11001","11010","00010","00100","01000","01011","10011"),
    "+": ("00000","00100","00100","11111","00100","00100","00000"),
    "$": ("00100","01111","10100","01110","00101","11110","00100"),
    "_": ("00000","00000","00000","00000","00000","00000","11111"),
    " ": ("00000","00000","00000","00000","00000","00000","00000"),
}


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


class Canvas:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.pixels = bytearray([255]) * (width * height * 3)

    def rect(self, x, y, w, h, color):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.width, x + w), min(self.height, y + h)
        for py in range(y0, y1):
            pos = (py * self.width + x0) * 3
            row = bytes(color) * (x1 - x0)
            self.pixels[pos:pos + len(row)] = row

    def text(self, x, y, value, color=(25, 31, 44), scale=3):
        cursor = x
        value = str(value).upper()
        for ch in value:
            rows = FONT.get(ch, FONT[" "])
            for ry, row in enumerate(rows):
                for rx, bit in enumerate(row):
                    if bit == "1":
                        self.rect(cursor + rx * scale, y + ry * scale, scale, scale, color)
            cursor += 6 * scale

    def save(self, path):
        rows = []
        for y in range(self.height):
            start = y * self.width * 3
            rows.append(b"\x00" + bytes(self.pixels[start:start + self.width * 3]))
        raw = b"".join(rows)
        png = b"\x89PNG\r\n\x1a\n"
        png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0))
        png += png_chunk(b"IDAT", zlib.compress(raw, 9))
        png += png_chunk(b"IEND", b"")
        with open(path, "wb") as fh:
            fh.write(png)


def iso_now(value=None):
    if value:
        parsed = news.parse_time(value)
        if parsed is None:
            raise ValueError("--now wants an ISO 8601 value")
        return parsed
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def format_et(value):
    if not value:
        return "No disponible"
    if isinstance(value, str):
        if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} ET$", value):
            return value
        parsed = news.parse_time(value)
        if parsed is not None:
            value = parsed
        else:
            return value + " (zona horaria no disponible)"
    if getattr(value, "tzinfo", None) is not None:
        eastern = news.to_eastern(value)
    else:
        eastern = value
    return eastern.strftime("%Y-%m-%d %H:%M ET")


def parse_data_timestamp(value):
    """Convert scanner/news timestamp representations to aware UTC for comparison."""
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)
    if not isinstance(value, str):
        return None
    match = re.match(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) ET$", value)
    if match:
        try:
            local = dt.datetime.strptime(match.group(1) + " " + match.group(2), "%Y-%m-%d %H:%M")
            return scan.eastern_to_utc(local).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        try:
            local = dt.datetime.strptime(value, "%Y-%m-%d").replace(hour=16)
            return scan.eastern_to_utc(local).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return None
    parsed = news.parse_time(value)
    return parsed if parsed is not None else None


def scanner_daily(ticker, now, offline):
    if offline:
        try:
            data, failed = scan.load_offline(offline)
        except scan.ScanError as exc:
            return {"status": "unavailable", "matches": [], "reason": str(exc)}
        if ticker not in data and ticker not in failed:
            return {"status": "unavailable", "matches": [], "reason": "ticker absent from scanner offline data"}
        hits, counts, last_date = scan.scan_daily(data, [ticker], now, 5.0, 1000000)
    else:
        data, failed = scan.fetch_spark([ticker], "3mo", "1d", 0.3)
        if ticker not in data:
            return {"status": "unavailable", "matches": [], "reason": "no daily data: " + failed.get(ticker, "Yahoo returned no data")}
        hits, counts, last_date = scan.scan_daily(data, [ticker], now, 5.0, 1000000)
    own = [h for h in hits if h["symbol"] == ticker]
    return {"status": "available", "matches": own,
            "as_of": last_date.isoformat() if last_date else None,
            "counts": counts}


def scanner_orb(ticker, now, offline, at):
    if offline:
        try:
            data, failed = scan.load_offline(offline)
        except scan.ScanError as exc:
            return {"status": "unavailable", "matches": [], "reason": str(exc)}
        if ticker not in data and ticker not in failed:
            return {"status": "unavailable", "matches": [], "reason": "ticker absent from scanner offline data"}
        days = [scan.ts_to_eastern(s["t"][-1]).date() for s in data.values() if s["t"]]
        if not days:
            return {"status": "unavailable", "matches": [], "reason": "offline data has no bar timestamps"}
        day = max(days)
    else:
        now_eastern = scan.to_eastern(now)
        day = now_eastern.date()
        rng = "1d"
        data, failed = scan.fetch_spark([ticker], rng, "5m", 0.3)
        if ticker not in data:
            return {"status": "unavailable", "matches": [], "reason": "no intraday data: " + failed.get(ticker, "Yahoo returned no data")}
        confirm = lambda symbol: scan.parse_chart(scan.yahoo_get(scan.chart_path(symbol, rng, "5m")), symbol)
        try:
            at_time = scan.parse_hhmm(at) if at else scan.to_eastern(now).time().replace(second=0, microsecond=0)
            day, cutoff = scan.orb_window(now, at_time, 15, dt.time(15, 30))
            hits, counts, failed2 = scan.scan_orb(data, [ticker], day, cutoff, 15, 5.0, 0, confirm, 0)
            return {"status": "available", "matches": [h for h in hits if h["symbol"] == ticker],
                    "as_of": "%s %s ET" % (day.isoformat(), cutoff.strftime("%H:%M")), "counts": counts}
        except scan.ScanError as exc:
            return {"status": "unavailable", "matches": [], "reason": str(exc)}
    try:
        at_time = scan.parse_hhmm(at) if at else dt.time(10, 15)
        day, cutoff = scan.orb_window(now, at_time, 15, dt.time(15, 30), explicit_day=day)
        hits, counts, failed2 = scan.scan_orb(data, [ticker], day, cutoff, 15, 5.0, 0)
        return {"status": "available", "matches": [h for h in hits if h["symbol"] == ticker],
                "as_of": "%s %s ET" % (day.isoformat(), cutoff.strftime("%H:%M")), "counts": counts}
    except scan.ScanError as exc:
        return {"status": "unavailable", "matches": [], "reason": str(exc)}


def collect_news(ticker, now, offline, hours, no_sec, move_pct):
    watch = {ticker: None}
    state = {}
    errors = []
    ua = None
    if no_sec:
        sec = False
    else:
        ua = news.sec_user_agent(None, os.path.join(ROOT, "trader", "config.json"))
        sec = bool(ua)
        if not sec:
            errors.append("SEC filings unavailable: no SEC User-Agent configured")
    fetcher = news.Fetcher(ua, offline=offline)
    items = news.collect(fetcher, watch, state, sec=sec, forms=("8-K",), count=10, errors=errors)
    items = news.dedupe(news.tag(items, watch))
    selected = news.select(items, state, now, hours=hours, show_all=True)
    moves = [] if offline is None and False else news.collect_moves(fetcher, watch, errors)
    moves = [move for move in moves
             if move.get("time") is None or move["time"].astimezone(dt.timezone.utc) <= now]
    return {
        "items": news._json_ready(selected),
        "moves": [dict(m, time=m["time"].isoformat() if m.get("time") else None,
                       moving=abs(m["pct"]) >= move_pct) for m in moves],
        "notes": errors,
    }


def wrap_text(text, limit):
    words = str(text).split()
    lines, line = [], ""
    for word in words:
        if len(line) + len(word) + 1 <= limit:
            line = (line + " " + word).strip()
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def draw_card(doc, path):
    canvas = Canvas(1200, 1500)
    canvas.rect(0, 0, 1200, 1500, (248, 250, 252))
    canvas.rect(0, 0, 1200, 170, (20, 38, 74))
    canvas.text(55, 55, "MARKET ANALYSIS CARD", (255, 255, 255), 4)
    canvas.text(55, 118, doc["symbol"], (255, 255, 255), 3)

    canvas.rect(55, 210, 1090, 150, (255, 255, 255))
    canvas.text(75, 235, "GENERATED", (80, 90, 110), 2)
    canvas.text(75, 275, format_et(doc["generated_at"]), (25, 31, 44), 3)
    canvas.text(680, 235, "DATA AS OF", (80, 90, 110), 2)
    canvas.text(680, 275, format_et(doc["data_as_of"]), (25, 31, 44), 3)

    y = 405
    for title, lines, color in [
        ("PRICE MOVEMENT", doc["card_sections"]["price"], (36, 99, 74)),
        ("SCANNER - DAILY", doc["card_sections"]["daily"], (43, 73, 119)),
        ("SCANNER - OPENING RANGE", doc["card_sections"]["orb"], (43, 73, 119)),
        ("RECENT NEWS", doc["card_sections"]["news"], (105, 62, 62)),
    ]:
        canvas.rect(55, y, 1090, 215, (255, 255, 255))
        canvas.rect(55, y, 12, 215, color)
        canvas.text(85, y + 25, title, color, 3)
        ty = y + 75
        visible = lines[:6] if title == "RECENT NEWS" else lines[:4]
        for line in visible:
            for wrapped in wrap_text(line, 55)[:2]:
                canvas.text(85, ty, wrapped, (25, 31, 44), 2)
                ty += 32
        y += 255

    canvas.rect(55, 1430, 1090, 55, (232, 235, 241))
    canvas.text(75, 1447, "INFORMATION ONLY - NOT BUY OR SELL ADVICE", (80, 90, 110), 2)
    canvas.save(path)


def build_document(ticker, now, scanner_offline, daily_offline, news_offline, at, hours, no_sec, move_pct):
    daily = scanner_daily(ticker, now, daily_offline)
    orb = scanner_orb(ticker, now, scanner_offline, at)
    news_data = collect_news(ticker, now, news_offline, hours, no_sec, move_pct)

    moves = news_data["moves"]
    move = moves[0] if moves else None
    if move:
        price_text = "PRICE {price}; PREV CLOSE {prev_close}; CHANGE {pct:+.2f}%"
        price_text = price_text.format(**move)
        price_lines = [price_text, "PRICE TIME " + format_et(move.get("time"))]
    else:
        price_lines = ["PRICE MOVEMENT DATA NOT AVAILABLE"]

    daily_lines = []
    if daily["status"] != "available":
        daily_lines = ["DATA UNAVAILABLE - " + daily["reason"].upper()]
    elif daily["matches"]:
        for hit in daily["matches"]:
            daily_lines.append("MATCH " + ", ".join(hit["setups"]))
    else:
        daily_lines = ["NO MATCHING DAILY SETUP FOUND"]

    orb_lines = []
    if orb["status"] != "available":
        orb_lines = ["DATA UNAVAILABLE - " + orb["reason"].upper()]
    elif orb["matches"]:
        for hit in orb["matches"]:
            orb_lines.append("MATCH: {symbol} {price} +{pct_over:.2f}% OVER {or_high}".format(**hit))
    else:
        orb_lines = ["NO MATCHING OPENING-RANGE BREAKOUT FOUND"]

    news_lines = []
    if news_data["items"]:
        total_news = len(news_data["items"])
        card_count = min(2, total_news)
        news_lines.append("SHOWING %d OF %d NEWS ITEMS - FULL SET IN JSON" % (card_count, total_news))
        for item in news_data["items"][:card_count]:
            when = format_et(item.get("time"))
            news_lines.append("%s | %s | %s" % (when, item.get("source") or "source unavailable",
                                                 item.get("title") or "title unavailable"))
            if item.get("link"):
                news_lines.append(item["link"])
    else:
        news_lines = ["NO RECENT NEWS ITEMS FOUND"]
    news_lines.extend("NOTE " + note.upper() for note in news_data["notes"])

    data_times = []
    for source in (daily, orb):
        parsed = parse_data_timestamp(source.get("as_of"))
        if parsed is not None:
            data_times.append(parsed)
    if move and move.get("time"):
        parsed = parse_data_timestamp(move["time"])
        if parsed is not None:
            data_times.append(parsed)
    data_as_of = max(data_times).isoformat() if data_times else None

    return {
        "symbol": ticker,
        "generated_at": now.isoformat(),
        "data_as_of": data_as_of,
        "timestamp_timezone": "UTC ISO 8601; card timestamps displayed in America/New_York (ET)",
        "scanner": {"daily": daily, "orb": orb},
        "news": news_data,
        "sources": {
            "price_and_headlines": "Yahoo Finance unofficial endpoints",
            "sec_filings": "SEC EDGAR" if not no_sec else "disabled",
        },
        "disclaimer": "Strictly informational. No buy or sell recommendation, order execution, or broker connection.",
        "card_sections": {
            "price": price_lines,
            "daily": daily_lines,
            "orb": orb_lines,
            "news": news_lines,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("ticker", help="ticker symbol, for example TSLA")
    parser.add_argument("--now", help="ISO 8601 timestamp for reproducible generation")
    parser.add_argument("--at", help="opening-range cutoff in New York time, for example 10:15")
    parser.add_argument("--offline-scanner", help="offline 5-minute scanner JSON/folder")
    parser.add_argument("--offline-daily", help="offline daily spark JSON/folder")
    parser.add_argument("--offline-news", help="offline news fixture folder")
    parser.add_argument("--hours", type=float, default=48)
    parser.add_argument("--no-sec", action="store_true")
    parser.add_argument("--move-pct", type=float, default=3.0)
    parser.add_argument("--output-dir", default="trader/card")
    args = parser.parse_args(argv)

    ticker = args.ticker.strip().upper()
    if not re.match(r"^[A-Z][A-Z0-9.-]{0,9}$", ticker):
        parser.error("ticker must contain only letters, digits, dots or hyphens")
    try:
        now = iso_now(args.now)
    except ValueError as exc:
        parser.error(str(exc))

    doc = build_document(ticker, now, args.offline_scanner, args.offline_daily,
                         args.offline_news, args.at, args.hours, args.no_sec, args.move_pct)
    os.makedirs(args.output_dir, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    png_path = os.path.join(args.output_dir, "%s-%s.png" % (ticker, stamp))
    json_path = os.path.join(args.output_dir, "%s-%s.json" % (ticker, stamp))
    draw_card(doc, png_path)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print(json.dumps({"ticker": ticker, "png": png_path, "json": json_path,
                      "generated_at": doc["generated_at"], "data_as_of": doc["data_as_of"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
