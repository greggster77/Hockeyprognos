import unittest
from backend.resultat_separat import extract_result

class ResultTests(unittest.TestCase):
    def test_reg(self):
        x = extract_result({'GameResult': {'Home': 4, 'Away': 1}, 'decided_in': 'regulation'})
        self.assertEqual((x.home_goals, x.away_goals, x.final_home_goals, x.final_away_goals, x.decided_in), (4,1,4,1,'REG'))
    def test_ot(self):
        x = extract_result({'homeTeam': {'score': 3}, 'awayTeam': {'score': 2}, 'overtime': True}, regulation=(2,2))
        self.assertEqual((x.final_home_goals, x.home_goals, x.decided_in), (3,2,'OT'))
    def test_unknown_never_guesses(self):
        x = extract_result({'homeTeam': {'score': 3}, 'awayTeam': {'score': 2}})
        self.assertIsNone(x.home_goals)
        self.assertIsNone(x.decided_in)
    def test_invalid_ot(self):
        with self.assertRaises(ValueError):
            extract_result({'overtime': True}, regulation=(2,1))

if __name__ == '__main__':
    unittest.main()
