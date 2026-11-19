import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from model import parse_match_datetime, predict

class Game:
    def __init__(self, date, h, a, hg, ag):
        self.date=date; self.home_id=h; self.away_id=a; self.home_goals=hg; self.away_goals=ag

def test_mixed_timestamp_formats_are_safe():
    assert parse_match_datetime('2026-11-01T19:00:00').tzinfo is not None
    assert parse_match_datetime('2026-11-01T18:00:00Z').tzinfo is not None
    games=[]
    for i in range(60):
        dt=datetime(2026,9,1,tzinfo=timezone.utc)+timedelta(days=i)
        when=dt.isoformat() if i%2 else dt.replace(tzinfo=None).isoformat()
        games.append(Game(when, 'A' if i%2 else 'B', 'B' if i%2 else 'A', 3, 2))
    result=predict(games,'A','B',league='HA')
    assert abs(sum(result[k] for k in ('home_win','draw','away_win'))-100)<0.01
