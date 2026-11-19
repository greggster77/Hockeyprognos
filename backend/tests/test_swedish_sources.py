import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from swedish_sources import normalize_flat, period_goals

class SwedishSourceTests(unittest.TestCase):
    def test_overtime_excluded(self):
        game = {'id':'1','date':'2026-11-20T18:00:00Z','home_id':'A','away_id':'B','home_name':'A','away_name':'B','status':'OT',
                'home_score_p1':1,'home_score_p2':0,'home_score_p3':1,
                'away_score_p1':0,'away_score_p2':1,'away_score_p3':1,
                'home_score':3,'away_score':2}
        result = normalize_flat('HA',[game])[0]
        self.assertEqual((result['home_goals'], result['away_goals']), (2,2))
    def test_missing_periods_skipped(self):
        game = {'id':'1','date':'2026-11-20T18:00:00Z','home_id':'A','away_id':'B','home_name':'A','away_name':'B','status':'OT','home_score':3,'away_score':2}
        with self.assertRaises(ValueError): normalize_flat('HA',[game])
    def test_scheduled(self):
        game = {'id':'1','date':'2026-11-20T18:00:00Z','home_id':'A','away_id':'B','home_name':'A','away_name':'B','status':'SCHEDULED'}
        self.assertEqual(normalize_flat('HA',[game])[0]['status'], 'SCHEDULED')

if __name__ == '__main__': unittest.main()
