import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from model import predict

def game(i, season, home='A', away='B'):
    dt = datetime(season, 10, 5, tzinfo=timezone.utc) + timedelta(days=i)
    return SimpleNamespace(date=dt.isoformat(), home_id=home, away_id=away,
                           home_goals=2 + i % 3, away_goals=1 + i % 2)

class HistoricalModelTests(unittest.TestCase):
    def test_previous_season_changes_probability(self):
        recent = [game(i, 2026) for i in range(30)]
        older = [game(i, 2025, 'B', 'A') for i in range(30)]
        for m in older:
            m.home_goals, m.away_goals = 1, 1
        a = predict(recent, 'A', 'B')
        b = predict(older + recent, 'A', 'B')
        self.assertEqual(b['details']['historical_matches_used'], 60)
        self.assertNotEqual((a['home_win'], a['away_win']), (b['home_win'], b['away_win']))
        self.assertAlmostEqual(sum((b['home_win'], b['draw'], b['away_win'])), 100, places=2)
if __name__ == '__main__': unittest.main()
