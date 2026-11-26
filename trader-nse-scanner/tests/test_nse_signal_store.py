
import tempfile
import unittest
from pathlib import Path

from nse_signal_store import claim_signal


class TestSignalStore(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history_file = Path(self.temp_dir.name) / "history.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_first_signal_allowed(self):
        result = claim_signal("RELIANCE.NS", "2026-11-23", self.history_file)
        self.assertTrue(result)

    def test_duplicate_same_day_blocked(self):
        claim_signal("RELIANCE.NS", "2026-11-23", self.history_file)

        result = claim_signal("RELIANCE.NS", "2026-11-23", self.history_file)

        self.assertFalse(result)

    def test_next_day_signal_allowed(self):
        claim_signal("RELIANCE.NS", "2026-11-23", self.history_file)

        result = claim_signal("RELIANCE.NS", "2026-11-24", self.history_file)

        self.assertTrue(result)

    def test_different_stock_allowed(self):
        claim_signal("RELIANCE.NS", "2026-11-23", self.history_file)

        result = claim_signal("TCS.NS", "2026-11-23", self.history_file)

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
