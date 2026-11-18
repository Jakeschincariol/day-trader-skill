"""Load a script from a skill folder (the folder names have hyphens)."""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
INDIA_FIX = os.path.join(FIX, "india")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# tests read the fixture holiday list, never the shipped one
os.environ["INDIA_HOLIDAYS"] = os.path.join(INDIA_FIX, "holidays.json")


def load(folder, name):
    path = os.path.join(ROOT, folder, name + ".py")
    spec = importlib.util.spec_from_file_location("swing_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# the 20 NSE stocks the offline fixtures were cut from (tests/capture_fixtures.py)
FIXTURE_SYMBOLS = ["TCS", "M&M", "IDEA", "RELIANCE", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT",
                   "BAJAJ-AUTO", "TATASTEEL", "SUZLON", "YESBANK", "IRFC", "ETERNAL", "ADANIENT",
                   "BHARTIARTL", "SUNPHARMA", "TITAN"]
FIXTURE_DATE = "2026-11-18"
