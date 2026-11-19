import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class NightGameTests(unittest.TestCase):
    def test_python_syntax(self):
        ast.parse((ROOT / "backend/main.py").read_text())
    def test_swedish_day_bounds(self):
        s = (ROOT / "backend/main.py").read_text()
        self.assertIn("datetime.combine(day, datetime.min.time(), sweden)", s)
        self.assertIn("astimezone(timezone.utc)", s)
    def test_pre_game_forecast_archive(self):
        s = (ROOT / "backend/main.py").read_text()
        self.assertIn("forecast_archive WHERE match_id=? AND created_at < ?", s)
    def test_finished_game_is_not_downgraded(self):
        s = (ROOT / "backend/main.py").read_text()
        self.assertIn('existing[g["id"]]["status"] == "FINISHED"', s)
    def test_ui_statuses(self):
        s = (ROOT / "web/app.js").read_text()
        self.assertIn("STARTAD · resultat inväntas", s)
        self.assertIn("SLUT · 60 min:", s)

if __name__ == "__main__":
    unittest.main()
