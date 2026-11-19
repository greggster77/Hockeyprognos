import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from swehockey_stats import parse_standings, parse_scorers, parse_goalies, inspect_tables, SOURCES

def nested(headers, values):
    inner = '<table><tr>' + ''.join(f'<th>{v}</th>' for v in headers) + '</tr><tr>' + ''.join(f'<td>{v}</td>' for v in values) + '</tr></table>'
    return '<table><tr><td>Section</td></tr><tr><td>' + inner + '</td></tr></table>'

def test_standings_nested():
    rows = parse_standings(nested(['RK','Team','GP','W','T','L','GD','TP'],['1','Färjestad BK','16','14','2','0','45','45']))
    assert len(rows) == 1 and rows[0]['team'] == 'Färjestad BK'

def test_scorers_nested():
    rows = parse_scorers(nested(['Rk','Name','Team','Pos','GP','G','A','TP'],['1','Test, A','FBK','CE','16','4','8','12']))
    assert len(rows) == 1 and rows[0]['points'] == 12

def test_goalies_nested():
    rows = parse_goalies(nested(['Rk','Name','Team','GPI','SOG','GA','GAA','SVS%'],['1','Test, B','FBK','10','300','20','2.00','93.33']))
    assert len(rows) == 1 and rows[0]['save_pct'] == 93.33

def test_tables_diagnostics():
    assert inspect_tables(nested(['RK','Team','GP','TP'],['1','FBK','16','45']))['table_count'] == 2

def test_standings_source():
    assert '/Standings/' in SOURCES['standings']
