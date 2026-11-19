import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from swedish_sources import parse_ha_stats, _ha_teams

def test_nested_period_score_and_relative_logo():
    payload = {'teams':[{'teamCode':'LIF','name':'Leksands IF','logos':{'medium':'/assets/lif.png'}}, {'teamCode':'MODO','name':'MoDo Hockey','logos':{'medium':'https://example.org/modo.png'}}], 'results':[{'Date':'2026-11-18','Time':'19:00','HomeTeam':'LIF','AwayTeam':'MODO','GameResult':{'Home':4,'Away':3},'decided_in':'overtime','PeriodScores':[{'Score':{'Home':1,'Away':0}},{'Score':{'Home':1,'Away':2}},{'Score':{'Home':1,'Away':1}}]}]}
    rows=parse_ha_stats(payload)
    assert rows[0]['status']=='FINISHED'
    assert (rows[0]['home_goals'],rows[0]['away_goals'])==(3,3)
    assert _ha_teams(payload)[0]['icon']=='https://hockeyallsvenskan.se/assets/lif.png'

def test_unverified_result_never_marked_scheduled():
    payload={'results':[{'Date':'2026-11-18','Time':'19:00','HomeTeam':'LIF','AwayTeam':'MODO','GameResult':{'Home':4,'Away':3},'decided_in':'overtime','PeriodScores':[{'unknown':1}]}]}
    try:
        parse_ha_stats(payload)
    except ValueError:
        pass
    else:
        raise AssertionError('Unverified completed match should not be stored as upcoming')
