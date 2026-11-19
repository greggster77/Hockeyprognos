import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from swedish_sources import ha_stats_fallback

class Response:
    def raise_for_status(self): pass
    def json(self):
        return {'data': {'rows': [
            {'date':'2026-11-20T18:00:00Z','home_team_code':'AIK','away_team_code':'MODO','decided_in':'OT',
             'home_score':3,'away_score':2,'home_score_p1':1,'home_score_p2':1,'home_score_p3':0,
             'away_score_p1':0,'away_score_p2':1,'away_score_p3':1},
            {'date':'2026-11-21T18:00:00Z','home_team_code':'MODO','away_team_code':'AIK','decided_in':''},
            {'date':'2026-11-22T18:00:00Z','home_team_code':'AIK','away_team_code':'MODO','decided_in':'SO',
             'home_score':3,'away_score':2}
        ]}}
class Client:
    def post(self, url, json, headers):
        assert json['season'] == '2026'
        return Response()
class Tests(unittest.TestCase):
    def test_ha_fallback_regulation_and_schedule(self):
        rows = ha_stats_fallback(Client(), 2026)
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[0]['home_goals'],rows[0]['away_goals']), (2,2))
        self.assertEqual(rows[1]['status'], 'SCHEDULED')
        self.assertEqual(rows[0]['home_id'], 'HA:AIK')
if __name__ == '__main__': unittest.main()
