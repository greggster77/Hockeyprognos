import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from model import predict, weighted_form

@dataclass
class Match:
    home_id: str
    away_id: str
    home_goals: int
    away_goals: int

class NHLModelTests(unittest.TestCase):
    def setUp(self):
        self.games = []
        for i in range(100):
            self.games.append(Match('A' if i%2 else 'C', 'B' if i%2 else 'A', 3 + (i%3), 2 + (i%2)))

    def test_recent_weight_70_percent(self):
        games = [Match('A','B',1,0) for _ in range(15)] + [Match('A','B',5,0) for _ in range(5)]
        f = weighted_form(games, 'A')
        self.assertAlmostEqual(f['gf'], 3.8)
        self.assertEqual(f['played'], 20)

    def test_only_last_20(self):
        games = [Match('A','B',9,0)]*5 + [Match('A','B',1,0)]*20
        self.assertAlmostEqual(weighted_form(games, 'A')['gf'], 1.0)

    def test_predictions_sum_to_100(self):
        p = predict(self.games,'A','B')
        self.assertAlmostEqual(p['home_win']+p['draw']+p['away_win'],100,places=2)
        self.assertEqual(p['details']['window_matches'],20)
        self.assertEqual(p['details']['recent_weight_pct'],70)

    def test_home_away_changes_prediction(self):
        base = [Match('A','B',4,1), Match('C','A',1,2), Match('B','C',1,3)]*35
        p = predict(base,'A','B')
        self.assertTrue(p['expected_home']>0)
        self.assertGreater(p['details']['home_venue_games'], 0)
        self.assertGreater(p['details']['away_venue_games'], 0)

if __name__=='__main__': unittest.main()
