
import unittest
import sys
import io

from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from contextlib import redirect_stdout

import nse_orb

IST = ZoneInfo("Asia/Kolkata")


class TestNSEORBHoliday(unittest.TestCase):

    def test_holiday_stops_scanner_before_fetching_data(self):
        holiday_time = datetime(
            2026, 11, 24, 10, 0, tzinfo=IST
        )

        output = io.StringIO()

        with patch.object(
            sys, "argv", ["nse_orb.py", "--symbols", "TEST.NS"]
        ):
            with patch.object(nse_orb, "datetime") as mock_datetime:
                mock_datetime.now.return_value = holiday_time

                with patch.object(
                    nse_orb,
                    "fetch_candles"
                ) as mock_fetch:

                    with redirect_stdout(output):
                        nse_orb.main()

                    mock_fetch.assert_not_called()

        result = output.getvalue()

        self.assertIn("MARKET HOLIDAY", result)
        self.assertIn(
            "Prakash Gurpurb Sri Guru Nanak Dev", result
        )
        self.assertIn("2026-11-25", result)

    def test_holiday_does_not_generate_paper_signal(self):
        holiday_time = datetime(
            2026, 11, 24, 10, 0, tzinfo=IST
        )

        output = io.StringIO()

        with patch.object(
            sys, "argv", ["nse_orb.py", "--symbols", "TEST.NS"]
        ):
            with patch.object(nse_orb, "datetime") as mock_datetime:
                mock_datetime.now.return_value = holiday_time

                with patch.object(
                    nse_orb, "claim_signal"
                ) as mock_claim:

                    with redirect_stdout(output):
                        nse_orb.main()

                    mock_claim.assert_not_called()

        self.assertNotIn(
            "NEW PAPER SIGNAL RECORDED", output.getvalue()
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

