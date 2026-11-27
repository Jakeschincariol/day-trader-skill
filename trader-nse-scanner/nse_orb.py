import argparse
import json
import math
import urllib.request
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo

from nse_signal_store import claim_signal
from nse_holidays import get_holiday_reason, next_trading_day

IST = ZoneInfo("Asia/Kolkata")

OPEN = time(9, 15)
ORB_END = time(9, 30)
CLOSE = time(15, 30)
CANDLE_MINUTES = 5
MIN_VOLUME_RATIO = 1.5
MAX_CANDLE_AGE_MINUTES = 15

DEFAULT_SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
]


def fetch_candles(symbol):
    """Fetch five-minute candles from Yahoo Finance."""
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + symbol
        + "?range=5d&interval=5m"
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        document = json.loads(response.read().decode("utf-8"))

    chart = document.get("chart", {})
    if chart.get("error"):
        raise ValueError(str(chart["error"]))

    results = chart.get("result")
    if not results:
        raise ValueError("No candle data returned")

    result = results[0]
    quote_data = result.get("indicators", {}).get("quote", [])
    if not quote_data:
        raise ValueError("No quote data returned")

    quote = quote_data[0]
    timestamps = result.get("timestamp", [])
    candles = []

    for index, timestamp in enumerate(timestamps):
        try:
            values = {
                "open": quote["open"][index],
                "high": quote["high"][index],
                "low": quote["low"][index],
                "close": quote["close"][index],
                "volume": quote["volume"][index],
            }
        except (KeyError, IndexError, TypeError):
            continue

        if any(value is None for value in values.values()):
            continue

        candle_time = datetime.fromtimestamp(
            timestamp, timezone.utc
        ).astimezone(IST)

        values["time"] = candle_time
        candles.append(values)

    return candles


def validate_candles(candles, now=None):
    """Validate candle structure, timestamps, OHLC values and volume."""
    if not isinstance(candles, (list, tuple)):
        return "Invalid candle data"

    if now is not None:
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            return "Invalid scan time"

    seen_timestamps = set()

    for candle in candles:
        if not isinstance(candle, dict):
            return "Invalid candle data"

        candle_time = candle.get("time")
        if (
            not isinstance(candle_time, datetime)
            or candle_time.tzinfo is None
            or candle_time.utcoffset() is None
        ):
            return "Invalid candle timestamp"

        if (
            candle_time.minute % CANDLE_MINUTES != 0
            or candle_time.second != 0
            or candle_time.microsecond != 0
        ):
            return "Invalid 5-minute candle timestamp"

        timestamp_key = candle_time.astimezone(timezone.utc)
        if timestamp_key in seen_timestamps:
            return "Duplicate candle timestamp"
        seen_timestamps.add(timestamp_key)

        if now is not None and candle_time > now:
            return "Future candle timestamp"

        try:
            open_price = float(candle["open"])
            high = float(candle["high"])
            low = float(candle["low"])
            close = float(candle["close"])
            volume = float(candle["volume"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return "Invalid price or volume"

        values = (open_price, high, low, close, volume)
        if not all(math.isfinite(value) for value in values):
            return "Invalid price or volume"

        if min(open_price, high, low, close) <= 0 or volume < 0:
            return "Invalid price or volume"

        if high < max(open_price, close) or low > min(open_price, close):
            return "Invalid OHLC relationship"

        if high < low:
            return "Invalid OHLC relationship"

    return None


def _no_breakout():
    return {"status": "NO CONFIRMED BREAKOUT"}


def analyse(symbol, candles, now=None):
    """Analyse completed current-session candles for an NSE opening-range breakout."""
    if now is None:
        now = datetime.now(IST)

    validation_error = validate_candles(candles, now)
    if validation_error:
        return validation_error

    today = now.astimezone(IST).date()

    completed_today = []
    for candle in candles:
        candle_time = candle["time"].astimezone(IST)
        if candle_time.date() != today:
            continue

        # A five-minute candle is complete only after its full interval ends.
        if candle_time + timedelta(minutes=CANDLE_MINUTES) <= now.astimezone(IST):
            completed_today.append(candle)

    completed_today.sort(key=lambda item: item["time"].astimezone(timezone.utc))

    opening_by_time = {
        item["time"].astimezone(IST).time(): item
        for item in completed_today
        if OPEN <= item["time"].astimezone(IST).time() < ORB_END
    }

    required_opening_times = (
        time(9, 15),
        time(9, 20),
        time(9, 25),
    )

    if any(value not in opening_by_time for value in required_opening_times):
        return "Opening range incomplete or missing candles"

    opening_candles = [
        opening_by_time[value] for value in required_opening_times
    ]
    range_high = max(float(item["high"]) for item in opening_candles)
    range_low = min(float(item["low"]) for item in opening_candles)

    session_candles = [
        item for item in completed_today
        if ORB_END <= item["time"].astimezone(IST).time() < CLOSE
    ]

    for index, breakout in enumerate(session_candles):
        entry = float(breakout["close"])
        if entry <= range_high:
            continue

        # Use only preceding post-opening-range candles for the volume baseline.
        prior_candles = session_candles[:index]
        if len(prior_candles) < 3:
            continue

        prior_volumes = [float(item["volume"]) for item in prior_candles]
        average_volume = sum(prior_volumes) / len(prior_volumes)
        breakout_volume = float(breakout["volume"])

        if average_volume <= 0:
            continue

        volume_ratio = breakout_volume / average_volume
        if volume_ratio < MIN_VOLUME_RATIO:
            continue

        risk = entry - range_low
        if risk <= 0:
            continue

        breakout_time = breakout["time"].astimezone(IST)
        return {
            "status": "PAPER BUY CANDIDATE",
            "symbol": symbol,
            "time": breakout_time.strftime("%H:%M"),
            "signal_date": breakout_time.date().isoformat(),
            "entry": entry,
            "stop": range_low,
            "target1": entry + risk,
            "target2": entry + (2 * risk),
            "target3": entry + (3 * risk),
            "range_high": range_high,
            "range_low": range_low,
            "average_volume": average_volume,
            "breakout_volume": breakout_volume,
            "volume_ratio": volume_ratio,
        }

    return _no_breakout()


def _print_candidate(symbol, result):
    print(f"\n{symbol}: {result['status']}")
    print(f"Signal time: {result['time']} IST")
    print(f"Entry: {result['entry']:.2f}")
    print(f"Stop loss: {result['stop']:.2f}")
    print(
        "Targets: "
        f"T1 {result['target1']:.2f} | "
        f"T2 {result['target2']:.2f} | "
        f"T3 {result['target3']:.2f}"
    )
    print(
        f"Volume ratio: {result['volume_ratio']:.2f}x "
        f"(average {result['average_volume']:.0f}, "
        f"breakout {result['breakout_volume']:.0f})"
    )


def main():
    parser = argparse.ArgumentParser(
        description="NSE five-minute Opening Range Breakout paper scanner"
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated Yahoo Finance symbols, e.g. RELIANCE.NS,TCS.NS",
    )
    args = parser.parse_args()

    symbols = [
        symbol.strip().upper()
        for symbol in args.symbols.split(",")
        if symbol.strip()
    ]
    if not symbols:
        print("No symbols supplied.")
        return

    now = datetime.now(IST)

    holiday_reason = get_holiday_reason(now.date())
    if holiday_reason:
        print("MARKET HOLIDAY")
        print(f"Reason: {holiday_reason}")
        print(f"Next trading session: {next_trading_day(now.date()).isoformat()}")
        print("Scanner will resume at 09:15 IST.")
        return

    if now.weekday() >= 5:
        print("MARKET CLOSED: Weekend")
        print("Scanner will resume on the next trading day at 09:15 IST.")
        return

    if now.time() < OPEN:
        print("PRE-MARKET: Scanner waits until 09:15 IST.")
        return

    if now.time() < ORB_END:
        print("OPENING RANGE IN PROGRESS: Scanner waits until 09:30 IST.")
        return

    if now.time() >= CLOSE:
        print("MARKET CLOSED: NSE regular session ended at 15:30 IST.")
        return

    print("NSE OPENING RANGE BREAKOUT SCANNER")
    print("----------------------------------")
    print(f"Current IST: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    for symbol in symbols:
        try:
            candles = fetch_candles(symbol)
        except Exception as error:
            print(f"\n{symbol}: DATA FETCH ERROR: {error}")
            continue

        if not candles:
            print(f"\n{symbol}: NO CURRENT-DAY DATA")
            continue

        current_day_candles = [
            item for item in candles
            if item.get("time") is not None
            and item["time"].astimezone(IST).date() == now.date()
        ]

        if not current_day_candles:
            latest_time = max(
                (item["time"] for item in candles if item.get("time") is not None),
                default=None,
            )
            latest_text = (
                latest_time.astimezone(IST).strftime("%Y-%m-%d %H:%M")
                if latest_time else "unknown"
            )
            print(f"\n{symbol}: NO CURRENT-DAY DATA")
            print(f"Latest available candle: {latest_text} IST")
            continue

        latest_candle_time = max(
            item["time"].astimezone(IST) for item in current_day_candles
        )
        age_minutes = (now - latest_candle_time).total_seconds() / 60

        if age_minutes > MAX_CANDLE_AGE_MINUTES:
            print(f"\n{symbol}: STALE DATA")
            print(
                f"Latest candle: {latest_candle_time.strftime('%H:%M')} IST "
                f"({age_minutes:.0f} minutes old)"
            )
            continue

        result = analyse(symbol, candles, now)

        if isinstance(result, dict) and result.get("status") == "PAPER BUY CANDIDATE":
            try:
                recorded = claim_signal(symbol, result["signal_date"])
            except Exception as error:
                print(f"\n{symbol}: SIGNAL STORE ERROR: {error}")
                continue

            if recorded:
                print("\nNEW PAPER SIGNAL RECORDED")
                _print_candidate(symbol, result)
            else:
                print(f"\n{symbol}: DUPLICATE SIGNAL BLOCKED")
        elif isinstance(result, dict):
            print(f"\n{symbol}: {result.get('status', 'NO SIGNAL')}")
        else:
            print(f"\n{symbol}: {result}")


if __name__ == "__main__":
    main()
