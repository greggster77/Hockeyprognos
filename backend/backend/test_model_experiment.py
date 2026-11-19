import unittest
from dataclasses import dataclass
from model import predict, dixon_coles_factor

@dataclass
class Match:
    home_id: str
    away_id: str
    home_goals: int
    away_goals: int

class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.history = [Match('A' if i % 2 else 'C', 'B' if i % 2 else 'A',
                              2 + (i % 3), 1 + (i % 2)) for i in range(100)]

    def test_low_score_adjustment(self):
        self.assertGreater(dixon_coles_factor(0, 0, 2.5, 2.3), 1)
        self.assertGreater(dixon_coles_factor(1, 1, 2.5, 2.3), 1)

    def test_candidate_normalizes(self):
        for variant in ('current', 'experimental'):
            p = predict(self.history, 'A', 'B', league='SHL', variant=variant)
            self.assertAlmostEqual(p['home_win'] + p['draw'] + p['away_win'], 100, places=2)
            self.assertEqual(p['details']['window_matches'], 10)

    def test_current_still_default(self):
        a = predict(self.history, 'A', 'B', league='SHL')
        b = predict(self.history, 'A', 'B', league='SHL', variant='current')
        self.assertEqual(a, b)
