import json
import os
import tempfile
import unittest

from _load import FIX, load

card = load("trader-news", "card")
NOW = card.news.parse_time("2026-10-19T14:15:00Z")


class AnalysisCard(unittest.TestCase):
    def test_offline_card_reports_scanner_news_and_move(self):
        scanner = os.path.join(FIX, "trader-scanner", "wall5m-2026-10-19.json.gz")
        news_dir = os.path.join(FIX, "trader-news")
        with tempfile.TemporaryDirectory() as out:
            code = card.main([
                "TSLA", "--now", "2026-10-19T14:53:00Z", "--at", "10:15",
                "--offline-scanner", scanner, "--offline-news", news_dir,
                "--no-sec", "--output-dir", out,
            ])
            self.assertEqual(code, 0)
            base = "TSLA-20261019T145300Z"
            png = os.path.join(out, base + ".png")
            js = os.path.join(out, base + ".json")
            self.assertTrue(os.path.isfile(png))
            self.assertGreater(os.path.getsize(png), 1000)
            with open(png, "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
            with open(js, encoding="utf-8") as fh:
                doc = json.load(fh)
            self.assertEqual(doc["symbol"], "TSLA")
            self.assertEqual(doc["scanner"]["orb"]["status"], "available")
            matches = doc["scanner"]["orb"]["matches"]
            self.assertTrue(matches)
            self.assertEqual(matches[0]["price"], 364.18)
            self.assertTrue(doc["news"]["moves"])
            self.assertEqual(doc["news"]["moves"][0]["ticker"], "TSLA")
            self.assertTrue(doc["news"]["items"])
            self.assertIn("SHOWING", doc["card_sections"]["news"][0])
            self.assertIn("FULL SET IN JSON", doc["card_sections"]["news"][0])
            self.assertIn("UTC ISO 8601", doc["timestamp_timezone"])
            self.assertTrue(doc["data_as_of"].endswith("+00:00"))
            self.assertIn("T", doc["data_as_of"])
            self.assertIn("no buy or sell recommendation", doc["disclaimer"].lower())

    def test_iso_timestamp_formatting_uses_eastern_timezone(self):
        rendered = card.format_et("2026-10-19T14:52:13+00:00")
        self.assertTrue(rendered.endswith(" ET"))
        self.assertIn("2026-10-19", rendered)

    def test_mixed_timestamps_are_compared_as_datetime(self):
        latest = max(
            card.parse_data_timestamp("2026-10-19 10:15 ET"),
            card.parse_data_timestamp("2026-10-19T14:52:13+00:00"),
            card.parse_data_timestamp("2026-10-16"),
        )
        self.assertEqual(latest.isoformat(), "2026-10-19T14:52:13+00:00")

    def test_missing_data_is_explicit_and_not_invented(self):
        with tempfile.TemporaryDirectory() as scanner, tempfile.TemporaryDirectory() as news_dir:
            doc = card.build_document("ZZZZ", NOW, scanner, None, news_dir,
                                      "10:15", 48, True, 3.0)
            self.assertEqual(doc["scanner"]["orb"]["status"], "unavailable")
            self.assertTrue(doc["news"]["notes"] or doc["card_sections"]["price"][0].startswith("PRICE MOVEMENT"))

    def test_ticker_validation(self):
        with self.assertRaises(SystemExit):
            card.main(["bad ticker"])


if __name__ == "__main__":
    unittest.main()
