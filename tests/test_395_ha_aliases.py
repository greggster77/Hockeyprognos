import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from swedish_sources import parse_ha_stats


def test_short_codes_use_directory_names_and_stable_ids():
    payload = {
        'teams': [
            {'teamCode': 'LIF', 'name': 'Leksands IF', 'fullName': 'Leksands IF', 'logos': {'medium': 'https://example.org/lif.png'}},
            {'teamCode': 'MODO', 'name': 'MoDo Hockey', 'fullName': 'MoDo Hockey', 'logos': {'medium': 'https://example.org/modo.png'}},
        ],
        'results': [
            {'Date': '2026-11-18', 'Time': '19:00', 'HomeTeam': 'LIF', 'AwayTeam': 'MoDo Hockey',
             'GameResult': {'Home': 2, 'Away': 1}, 'decided_in': 'regulation',
             'PeriodScores': [{'Home': 1, 'Away': 0}, {'Home': 1, 'Away': 0}, {'Home': 0, 'Away': 1}]},
            {'Date': '2026-11-20', 'Time': '19:00', 'HomeTeam': 'LIF', 'AwayTeam': 'MODO',
             'GameResult': None, 'PeriodScores': []},
        ]
    }
    rows = parse_ha_stats(payload)
    assert rows[0]['home_name'] == rows[1]['home_name'] == 'Leksands IF'
    assert rows[0]['away_name'] == rows[1]['away_name'] == 'MoDo Hockey'
    assert rows[0]['home_id'] == rows[1]['home_id'] == 'HA:LIF'
    assert rows[0]['away_id'] == rows[1]['away_id'] == 'HA:MODO'
    assert rows[0]['status'] == 'FINISHED'
    assert rows[1]['status'] == 'SCHEDULED'
