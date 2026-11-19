"""Flags and context every swing-* tool shares."""

import argparse
import json
import os
import sys

from india import config, data, market
from india.nse_source import NseSource, soft_notice


def common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--dir", default="trader", help="the working folder (default ./trader)")
    ap.add_argument("--now", help='pin the clock, "YYYY-MM-DD HH:MM" in IST')
    ap.add_argument("--offline", help="read saved data from this file or folder, never the network")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")


class Ctx:
    def __init__(self, a):
        self.dir = a.dir
        self.now = market.now_ist(a.now)
        self.offline = a.offline
        self.json = a.json
        self.cfg = config.load(a.dir)
        self.fetcher = data.Fetcher(cache_dir=None if a.offline else os.path.join(a.dir, "cache"),
                                    offline=a.offline)
        self._nse = None

    @property
    def nse(self) -> NseSource:
        if self._nse is None:
            self._nse = NseSource(os.path.join(self.dir, "cache"), offline=self.offline)
        return self._nse

    def nse_notice(self):
        msg = soft_notice(self.nse)
        if msg and not self.json:
            print(msg, file=sys.stderr)
        return msg

    def path(self, name: str) -> str:
        return config.trader_path(self.dir, name)

    def read(self, name: str, default=None):
        return config.read_json(os.path.join(self.dir, name), default)

    def write(self, name: str, doc) -> str:
        p = self.path(name)
        config.write_json(p, doc)
        return p

    def emit(self, doc, text: str) -> None:
        print(json.dumps(doc, indent=1, ensure_ascii=False) if self.json else text)
