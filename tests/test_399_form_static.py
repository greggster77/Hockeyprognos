from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_ha_recent_endpoint_is_bound_to_ids_and_pre_match_date():
    code = (ROOT / 'backend/main.py').read_text()
    section = code.split('@app.get("/api/match-form/{match_id:path}")')[1].split('@app.get("/api/matches/{match_id:path}")')[0]
    assert 'home_id=? OR away_id=?' in section
    assert 'date < ?' in section
    assert "status='FINISHED'" in section
    assert 'perspective_home' in section
    assert 'serialize(c, r)' in section

def test_ha_form_renders_below_analysis_and_supports_expand():
    code = (ROOT / 'web/app.js').read_text()
    assert 'Senaste spelade matcher' in code
    assert '/api/match-form/' in code
    assert 'data-form-team' in code
    assert 'Visa färre matcher' in code
    assert 'perspective_home' in code
