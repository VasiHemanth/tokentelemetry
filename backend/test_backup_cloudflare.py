"""Unit tests for scripts/backup_cloudflare_to_gdrive.py."""
import csv
import json
import pathlib
import tempfile
import unittest

from scripts.backup_cloudflare_to_gdrive import write_rollup


class TestBackupCloudflare(unittest.TestCase):
    def test_write_rollup_aggregation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            raw_dir = pathlib.Path(tmp_dir) / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            rollup_file = pathlib.Path(tmp_dir) / "daily.csv"

            day1_records = [
                {
                    "timestamp": "2026-10-01 10:00:00",
                    "blob1": "app.active",
                    "blob2": "sess-1",
                    "blob3": "mac",
                    "blob15": "US",
                    "blob20": "cli",
                    "_sample_interval": 1,
                },
                {
                    "timestamp": "2026-10-01 11:00:00",
                    "blob1": "app.active",
                    "blob2": "sess-1",
                    "blob3": "mac",
                    "blob15": "US",
                    "blob20": "cli",
                    "_sample_interval": 1,
                },
                {
                    "timestamp": "2026-10-01 12:00:00",
                    "blob1": "app.active",
                    "blob2": "sess-2",
                    "blob3": "mac",
                    "blob15": "US",
                    "blob20": "cli",
                    "_sample_interval": 2,
                },
            ]

            day1_file = raw_dir / "2026-10-01.ndjson"
            with day1_file.open("w", encoding="utf-8") as f:
                for rec in day1_records:
                    f.write(json.dumps(rec) + "\n")

            buckets_count = write_rollup(raw_dir, rollup_file)
            self.assertEqual(buckets_count, 1)

            with rollup_file.open("r", encoding="utf-8") as f:
                reader = list(csv.DictReader(f))
                self.assertEqual(len(reader), 1)
                row = reader[0]
                self.assertEqual(row["day"], "2026-10-01")
                self.assertEqual(row["event"], "app.active")
                self.assertEqual(row["os"], "mac")
                self.assertEqual(row["country"], "US")
                self.assertEqual(row["surface"], "cli")
                # events = 1 + 1 + 2 = 4
                self.assertEqual(int(row["events"]), 4)
                # stored_rows = 3
                self.assertEqual(int(row["stored_rows"]), 3)
                # distinct_sessions = sess-1, sess-2 = 2
                self.assertEqual(int(row["distinct_sessions"]), 2)


if __name__ == "__main__":
    unittest.main()
