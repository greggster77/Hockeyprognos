import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from main import HistoricalMatch
from model import predict
from odds import parse_event

def test_historical_match_date():
    m=HistoricalMatch({"date":"2026-10-01T18:00:00Z","home_id":"A","away_id":"B","home_goals":3,"away_goals":2})
    assert m.date=="2026-10-01T18:00:00Z"

def test_model_uses_historical_dates():
    from datetime import datetime,timedelta,timezone
    history=[]
    for i in range(60):
        dt=datetime(2026,9,1,tzinfo=timezone.utc)+timedelta(days=i)
        history.append(HistoricalMatch({"date":dt.isoformat(),"home_id":"A" if i%2 else "B","away_id":"B" if i%2 else "A","home_goals":3,"away_goals":2}))
    for league in ("SHL","HA","NHL"):
        p=predict(history,"A","B",league=league)
        assert abs(p["home_win"]+p["draw"]+p["away_win"]-100)<0.01

def test_only_three_way_market():
    e={"home_team":"A","away_team":"B","bookmakers":[{"markets":[{"key":"h2h","outcomes":[{"name":"A","price":2.1},{"name":"B","price":2.8}]}]}]}
    assert parse_event(e) is None
