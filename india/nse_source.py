"""Optional data from NSE's website API, through the `nse` package
(PyPI `nse`, BennyThadikaran/NseIndiaApi, GPL-3.0; pip install -r
requirements-nse.txt). This is the ONLY file in the pack that imports it.

Everything here is optional: without the package (or when NSE refuses the
request) every method returns an empty result, records why, and the tools
carry on with what they have. Answers are cached for 6 hours under
<cache_dir>/nse/.
"""

import datetime
import hashlib
import json
import os
import time
from typing import Callable, Dict, List, Optional

TTL = 6 * 3600
INSTALL = "nse package not installed (pip install -r requirements-nse.txt)"


def _default_factory(cache_dir: str) -> Optional[Callable]:
    try:
        from nse import NSE  # noqa: the one import of the optional package
    except Exception:
        return None
    folder = os.path.join(cache_dir, "nse", "downloads")

    def make():
        os.makedirs(folder, exist_ok=True)
        return NSE(download_folder=folder)
    return make


def _iso(text: str) -> Optional[str]:
    for fmt in ("%d-%b-%Y", "%d-%b-%Y %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(str(text).strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


class NseSource:
    def __init__(self, cache_dir: str, client_factory: Optional[Callable] = None,
                 offline: Optional[str] = None):
        self.cache_dir = cache_dir
        self.offline = offline
        self.last_error = ""
        self.factory = client_factory or (None if offline else _default_factory(cache_dir))
        self.available = bool(self.factory) or bool(offline and os.path.isdir(os.path.join(offline, "nse")))
        self.why_unavailable = "" if self.available else INSTALL

    # one cached call -----------------------------------------------------
    def _key(self, method: str, kwargs: Dict) -> str:
        blob = json.dumps(kwargs, sort_keys=True, default=str)
        return "%s-%s.json" % (method, hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10])

    def _call(self, method: str, **kwargs):
        key = self._key(method, kwargs)
        if self.offline:
            path = os.path.join(self.offline, "nse", key)
            if not os.path.exists(path):
                path = os.path.join(self.offline, "nse", method + ".json")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)
            return None
        if not self.factory:
            return None
        path = os.path.join(self.cache_dir, "nse", key)
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < TTL:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        try:
            with self.factory() as client:
                got = getattr(client, method)(**kwargs)
        except Exception as e:   # NSE refuses, changes shape, times out: soft
            self.last_error = "%s: %s" % (method, e)
            return None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(got, fh, default=str)
        return got

    # what the tools use --------------------------------------------------
    def trading_holidays(self) -> Dict[str, str]:
        got = self._call("holidays", type="trading") or {}
        out = {}
        for row in (got.get("CM") or []) if isinstance(got, dict) else []:
            iso = _iso(row.get("tradingDate", ""))
            if iso:
                out[iso] = str(row.get("description", "")).strip()
        return out

    def results_dates(self, symbols: List[str], start: datetime.date, end: datetime.date) -> Dict[str, List[str]]:
        out = {}
        for sym in symbols:
            rows = self._call("board_meetings", symbol=sym, from_date=start, to_date=end) or []
            dates = set()
            for r in rows:
                text = ("%s %s" % (r.get("bm_purpose", ""), r.get("bm_desc", ""))).lower()
                iso = _iso(r.get("bm_date", ""))
                if "financial result" in text and iso and start.isoformat() <= iso <= end.isoformat():
                    dates.add(iso)
            if dates:
                out[sym] = sorted(dates)
        return out

    def corporate_actions(self, symbols: List[str], start: datetime.date, end: datetime.date) -> Dict[str, List[Dict]]:
        out = {}
        for sym in symbols:
            rows = self._call("actions", symbol=sym, from_date=start, to_date=end) or []
            acts = []
            for r in rows:
                iso = _iso(r.get("exDate", ""))
                if iso and start.isoformat() <= iso <= end.isoformat():
                    acts.append({"ex_date": iso, "purpose": str(r.get("subject", "")).strip()})
            if acts:
                out[sym] = sorted(acts, key=lambda a: a["ex_date"])
        return out

    def announcements(self, symbol: str, start: datetime.date, end: datetime.date) -> List[Dict]:
        rows = self._call("announcements", symbol=symbol, from_date=start, to_date=end) or []
        out = []
        for r in rows:
            try:
                t = datetime.datetime.strptime(r.get("an_dt", ""), "%d-%b-%Y %H:%M:%S")
            except ValueError:
                continue
            out.append({"time_ist": t.strftime("%Y-%m-%d %H:%M"), "subject": str(r.get("desc", "")).strip(),
                        "text": str(r.get("attchmntText") or "").strip(), "url": r.get("attchmntFile") or ""})
        return sorted(out, key=lambda a: a["time_ist"], reverse=True)


def soft_notice(src: NseSource) -> Optional[str]:
    if not src.available:
        return "NSE data off: %s. Results dates, corporate actions and announcements are skipped." % src.why_unavailable
    if src.last_error:
        return "NSE data partly unavailable (%s)." % src.last_error
    return None
