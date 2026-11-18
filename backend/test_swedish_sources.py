from swedish_sources import period_goals, normalize_flat

def test_regulation_periods():
    assert period_goals({'periods': [
        {'period': 1, 'homeScore': 1, 'awayScore': 0},
        {'period': 2, 'homeScore': 0, 'awayScore': 2},
        {'period': 3, 'homeScore': 1, 'awayScore': 0},
        {'period': 4, 'homeScore': 1, 'awayScore': 0},
    ]}) == (2, 2)

def test_overtime_without_period_scores_is_not_finished():
    sample = [{'id':'42','date':'2026-11-18T18:00:00Z',
               'home_id':'A','away_id':'B','home_name':'A','away_name':'B',
               'status':'ot','home_goals':3,'away_goals':2}]
    try:
        result = normalize_flat('HA', sample)
    except ValueError:
        return
    assert all(row['status'] != 'FINISHED' for row in result)
