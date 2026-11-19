import sqlite3
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import odds

class OddsTests(unittest.TestCase):
    def test_three_way_and_margin(self):
        event={'home_team':'Brynäs IF','away_team':'Luleå HF','bookmakers':[
            {'markets':[{'key':'h2h','outcomes':[{'name':'Brynäs IF','price':2.5},{'name':'Draw','price':4.0},{'name':'Luleå HF','price':2.8}]}]},
            {'markets':[{'key':'h2h','outcomes':[{'name':'Brynäs IF','price':1.5},{'name':'Luleå HF','price':2.5}]}]}]}
        result=odds.parse_event(event)
        self.assertEqual(result['bookmakers'],1)
        self.assertAlmostEqual(sum(result['market_probs'].values()),100,places=1)
    def test_two_way_rejected(self):
        self.assertIsNone(odds.parse_event({'home_team':'A','away_team':'B','bookmakers':[{'markets':[{'key':'h2h','outcomes':[{'name':'A','price':1.7},{'name':'B','price':2.1}]}]}]}))
    def test_saved_pre_match(self):
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;odds.setup(c)
        c.execute('INSERT INTO odds_snapshots VALUES(?,?,?,?,?,?,?,?,?)',('id','SHL','2026-11-20T18:00:00Z','Brynäs IF','Luleå HF','2026-11-19T10:00:00+00:00',1,'{"1":40,"X":25,"2":35}','{"1":2.5,"X":4,"2":2.8}'))
        self.assertIsNotNone(odds.for_match(c,'SHL','Brynäs IF','Luleå HF','2026-11-20T18:00:00Z'))
        self.assertIsNone(odds.for_match(c,'SHL','Brynäs IF','Frölunda HC','2026-11-20T18:00:00Z'))

if __name__=='__main__':unittest.main()
