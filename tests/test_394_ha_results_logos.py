import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from swedish_sources import parse_ha_stats, _ha_teams


def test_regulation_and_official_logos():
    payload = {'teams': [
        {'teamCode': 'AIK', 'name': 'AIK', 'fullName': 'AIK Hockey', 'logos': {'medium': 'https://example.com/aik.png'}},
        {'teamCode': 'MODO', 'name': 'MoDo Hockey', 'logos': {'medium': 'https://example.com/modo.png'}}],
        'results': [
            {'Date': '2026-11-19', 'Time': '19:00', 'HomeTeam': 'AIK', 'AwayTeam': 'MoDo Hockey',
             'GameResult': {'Home': 3, 'Away': 2}, 'decided_in': 'ot',
             'PeriodScores': [{'Home': 1, 'Away': 1}, {'Home': 1, 'Away': 0}, {'Home': 0, 'Away': 1}, {'Home': 1, 'Away': 0}]},
            {'Date': '2026-11-20', 'Time': '19:00', 'HomeTeam': 'AIK', 'AwayTeam': 'MoDo Hockey',
             'GameResult': None, 'decided_in': '', 'PeriodScores': []}
        ]}
    rows = parse_ha_stats(payload)
    assert len(rows) == 2
    assert rows[0]['home_goals'] == rows[0]['away_goals'] == 2
    assert rows[0]['status'] == 'FINISHED'
    assert rows[1]['status'] == 'SCHEDULED'
    assert rows[0]['home_id'] == 'HA:AIK'
    assert _ha_teams(payload)[0]['icon'] == 'https://example.com/aik.png'


def test_ot_without_periods_is_not_assumed_regulation():
    payload = {'results': [{'Date': '2026-11-19', 'Time': '19:00', 'HomeTeam': 'AIK',
                            'AwayTeam': 'MoDo Hockey', 'GameResult': {'Home': 3, 'Away': 2},
                            'decided_in': 'ot', 'PeriodScores': []}]}
    try:
        parse_ha_stats(payload)
    except ValueError:
        pass
    else:
        raise AssertionError('Overtime score was accepted without regulation proof')
