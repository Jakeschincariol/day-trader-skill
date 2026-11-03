"""Builds the synthetic MES fixture: 12 New York sessions of 5-minute bars,
08:00-16:55 ET, seeded random walk; the last session has a volume surge
breakout at 10:30 ET (bar 10:25-10:30) that runs to the target."""
import csv, datetime, random, sys
from zoneinfo import ZoneInfo
NY = ZoneInfo("America/New_York")
UTC = datetime.timezone.utc

def build(path):
    rnd = random.Random(7)
    px = 6800.0
    rows = []
    day = datetime.date(2026, 10, 15)
    sessions = 0
    while sessions < 12:
        if day.weekday() < 5:
            sessions += 1
            t = datetime.datetime.combine(day, datetime.time(8, 0), tzinfo=NY)
            end = datetime.datetime.combine(day, datetime.time(17, 0), tzinfo=NY)
            last = sessions == 12
            while t < end:
                hhmm = t.strftime("%H:%M")
                o = px
                base_v = 1500 + (3000 if "09:30" <= hhmm < "10:00" else 0)
                v = int(base_v * rnd.uniform(0.85, 1.15))
                step = rnd.gauss(0, 1.2)
                if last and "09:20" <= hhmm < "10:25":
                    step = 0.0                         # a tight hour before the surge
                if last and hhmm == "10:25":           # the surge bar
                    step, v = 3.5, 6000
                if last and "10:30" <= hhmm < "11:30":
                    step = 1.0                         # it keeps going
                c = round((o + step) * 4) / 4
                if last and hhmm == "10:25":
                    h, l = c + 0.25, o - 0.5
                elif last and "09:20" <= hhmm < "10:25":
                    h, l = o + 1.0, o - 1.0
                else:
                    h = max(o, c) + abs(rnd.gauss(0, 0.6))
                    l = min(o, c) - abs(rnd.gauss(0, 0.6))
                rows.append([t.astimezone(UTC).isoformat(), round(o, 2), round(round(h * 4) / 4, 2),
                             round(round(l * 4) / 4, 2), c, v])
                px = c
                t += datetime.timedelta(minutes=5)
        day += datetime.timedelta(days=1)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time", "open", "high", "low", "close", "volume"])
        w.writerows(rows)

if __name__ == "__main__":
    build(sys.argv[1])
