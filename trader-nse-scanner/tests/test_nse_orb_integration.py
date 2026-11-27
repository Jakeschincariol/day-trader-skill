
import unittest
import sys
import io

from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from contextlib import redirect_stdout

import nse_orb

IST = ZoneInfo("Asia/Kolkata")


class TestNSEORBIntegration(unittest.TestCase):

    def setUp(self):
        self.now = datetime(2026, 11, 23, 10, 0, tzinfo=IST)

        self.candidate = {
            "status": "PAPER BUY CANDIDATE",
            "time": "09:55",
            "signal_date": "2026-11-23",
            "entry": 107,
            "stop": 98,
            "target1": 116,
            "target2": 125,
            "target3": 134,
            "range_high": 106,
            "range_low": 98,
            "average_volume": 1000,
            "breakout_volume": 2000,
            "volume_ratio": 2.0,
        }

        # Fresh candle: 5 minutes before the mocked current time.
        self.mock_candles = [
            {
                "time": datetime(2026, 11, 23, 9, 55, tzinfo=IST),
                "open": 104,
                "high": 108,
                "low": 103,
                "close": 107,
                "volume": 2000,
            }
        ]

    def run_scanner(self, claim_result):
        output = io.StringIO()

        with patch.object(
            sys, "argv",
            ["nse_orb.py", "--symbols", "TEST.NS"]
        ):
            with patch.object(nse_orb, "datetime") as mock_datetime:
                mock_datetime.now.return_value = self.now

                with patch.object(
                    nse_orb,
                    "fetch_candles",
                    return_value=self.mock_candles
                ):
                    with patch.object(
                        nse_orb,
                        "analyse",
                        return_value=self.candidate
                    ):
                        with patch.object(
                            nse_orb,
                            "claim_signal",
                            return_value=claim_result
                        ) as mock_claim:

                            with redirect_stdout(output):
                                nse_orb.main()

        return output.getvalue(), mock_claim

    def test_new_signal_recorded(self):
        output, mock_claim = self.run_scanner(True)

        self.assertIn("NEW PAPER SIGNAL RECORDED", output)
        self.assertNotIn("DUPLICATE SIGNAL BLOCKED", output)

        mock_claim.assert_called_once_with(
            "TEST.NS", "2026-11-23"
        )

    def test_duplicate_signal_blocked(self):
        output, mock_claim = self.run_scanner(False)

        self.assertIn("DUPLICATE SIGNAL BLOCKED", output)
        self.assertNotIn("NEW PAPER SIGNAL RECORDED", output)

        mock_claim.assert_called_once_with(
            "TEST.NS", "2026-11-23"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
