from pathlib import Path
import ast
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "backend" / "main.py"
class WeeklySyncTests(unittest.TestCase):
    def test_backend_parses(self):
        ast.parse(SOURCE.read_text(encoding="utf-8"))
    def test_swedish_timezone(self):
        self.assertIn('Europe/Stockholm', SOURCE.read_text(encoding="utf-8"))
    def test_weekly_and_results_jobs(self):
        s = SOURCE.read_text(encoding="utf-8")
        self.assertIn('id="weekly-schedule"', s)
        self.assertIn('id="nhl-results"', s)
    def test_incremental_upserts(self):
        self.assertIn('def store_if_changed(', SOURCE.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
