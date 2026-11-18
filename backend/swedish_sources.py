"""Swedish league adapters. Fail closed if a regulation score cannot be verified."""
import os
from datetime import datetime, timezone
import httpx

SHL_SCHEDULE = 'https://www.shl.se/api/sports-v2/game-schedule'
HA_SCHEDULE = 'https://www.hockeyallsvenskan.se/api/sports-v2/game-schedule'


def pick(obj, *keys):
    for key in keys:
        if isinstance(obj, dict) and obj.get(key) is not None:
            return obj[key]
    return None


def integer(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def period_goals(obj):
    """Accept explicitly labelled 1/2/3 period scores only."""
    if all(pick(obj, f'home_score_p{i}') is not None and pick(obj, f'away_score_p{i}') is not None for i in (1,2,3)):
        return (sum(integer(obj[f'home_score_p{i}']) for i in (1,2,3)),
                sum(integer(obj[f'away_score_p{i}']) for i in (1,2,3)))
    periods = pick(obj, 'periods', 'periodScores', 'period_scores')
    if isinstance(periods, list):
        values = []
        for i, period in enumerate(periods):
            if not isinstance(period, dict):
                continue
            number = integer(pick(period, 'period', 'periodNumber', 'number'))
            if number is None:
                number = i + 1
            if number not in (1,2,3):
                continue
            home = integer(pick(period, 'home', 'homeScore', 'homeGoals'))
            away = integer(pick(period, 'away', 'awayScore', 'awayGoals'))
            if home is not None and away is not None:
                values.append((number, home, away))
        if {p[0] for p in values} == {1,2,3}:
            return sum(p[1] for p in values), sum(p[2] for p in values)
    return None


def normalize_flat(league, data):
    """Parse flat normalized feeds, including HA schedule-style rows."""
    if isinstance(data, dict):
        data = pick(data, 'games', 'matches', 'data', 'items')
    if not isinstance(data, list):
        raise ValueError(f'{league}: datakällan returnerade inte en matchlista')
    result = []
    for obj in data:
        if not isinstance(obj, dict):
            continue
        game_type = pick(obj, 'game_type', 'gameType')
        if league == 'HA' and game_type not in (None, 'HA', 'regular'):
            continue
        identifier = pick(obj, 'id', 'game_uuid', 'game_cms_id', 'slug')
        timestamp = pick(obj, 'date', 'scheduled_date_time', 'raw_start_date_time', 'start_date_time')
        home_id = pick(obj, 'home_id', 'home_statnet_id', 'home_team_code', 'home_team_uuid')
        away_id = pick(obj, 'away_id', 'away_statnet_id', 'away_team_code', 'away_team_uuid')
        home_name = pick(obj, 'home_name', 'home_team_name', 'home_team_names_short', 'home_team_code')
        away_name = pick(obj, 'away_name', 'away_team_name', 'away_team_names_short', 'away_team_code')
        if not all((identifier, timestamp, home_id, away_id, home_name, away_name)):
            continue
        decided = str(pick(obj, 'decided_in', 'status', 'state') or '').lower()
        finished = obj.get('is_completed') is True or decided in ('finished', 'final', 'ft', 'ot', 'so', 'post-game')
        row = dict(id=f'{league}:{identifier}', date=timestamp,
                   home_id=f'{league}:{home_id}', away_id=f'{league}:{away_id}',
                   home_name=home_name, away_name=away_name,
                   home_goals=None, away_goals=None, status='SCHEDULED')
        if finished:
            scores = period_goals(obj)
            if scores is None and decided in ('ft', 'finished', 'final'):
                h = integer(pick(obj, 'home_goals', 'home_score'))
                a = integer(pick(obj, 'away_goals', 'away_score'))
                if h is not None and a is not None:
                    scores = (h, a)
            if scores is None:
                continue
            row.update(home_goals=scores[0], away_goals=scores[1], status='FINISHED')
        result.append(row)
    if not result:
        raise ValueError(f'{league}: inga giltiga matcher i datakällans svar')
    return result


def swedish_schedule(league):
    """Official SHL public site schedule; API schema may change."""
    year = datetime.now(timezone.utc).year
    season_end = year + 1 if datetime.now(timezone.utc).month >= 7 else year
    with httpx.Client(timeout=25, follow_redirects=True,
                      headers={'User-Agent':'Hockeyprognos/1.0 (match statistics)'}) as client:
        response = client.get(SHL_SCHEDULE if league == 'SHL' else HA_SCHEDULE, params={'season':season_end,'gameType':'regular'})
        response.raise_for_status()
        payload = response.json()
    if isinstance(payload, dict):
        games = pick(payload, 'gameInfo', 'games', 'gameSchedule', 'data')
        if isinstance(games, dict):
            games = pick(games, 'gameInfo', 'games', 'items')
    else:
        games = payload
    if not isinstance(games, list):
        raise ValueError(f'{league}: okänt svar från officiella spelschema-API:t')
    rows = []
    for game in games:
        if not isinstance(game, dict):
            continue
        info = pick(game, 'gameInfo') or game
        if not isinstance(info, dict):
            continue
        home = pick(game, 'homeTeamInfo', 'homeTeam') or pick(info, 'homeTeamInfo', 'homeTeam') or {}
        away = pick(game, 'awayTeamInfo', 'awayTeam') or pick(info, 'awayTeamInfo', 'awayTeam') or {}
        if not isinstance(home, dict) or not isinstance(away, dict):
            continue
        ident = pick(info, 'uuid', 'id') or pick(game, 'uuid', 'id')
        when = pick(info, 'startDateTime', 'startTime', 'date') or pick(game, 'startDateTime', 'startTime')
        hid = pick(home, 'uuid', 'id', 'code')
        aid = pick(away, 'uuid', 'id', 'code')
        hn = pick(home, 'names', 'name', 'shortName', 'teamName')
        an = pick(away, 'names', 'name', 'shortName', 'teamName')
        if isinstance(hn, dict):
            hn = pick(hn, 'shortSite', 'short', 'full', 'long', 'name')
        if isinstance(an, dict):
            an = pick(an, 'shortSite', 'short', 'full', 'long', 'name')
        if not all((ident, when, hid, aid, hn, an)):
            continue
        state = str(pick(info, 'state', 'gameState', 'status') or '').lower()
        row = dict(id=f'{league}:{ident}', date=when, home_id=f'{league}:{hid}', away_id=f'{league}:{aid}',
                   home_name=hn, away_name=an, home_goals=None, away_goals=None, status='SCHEDULED')
        if state in ('post-game', 'final', 'finished'):
            scores = period_goals(game) or period_goals(info)
            overtime = pick(info, 'overtime', 'shootout') or pick(game, 'overtime', 'shootout')
            if scores is None and not overtime:
                h = integer(pick(home, 'score', 'goals'))
                a = integer(pick(away, 'score', 'goals'))
                if h is not None and a is not None:
                    scores = (h,a)
            if scores is None:
                continue
            row.update(status='FINISHED', home_goals=scores[0], away_goals=scores[1])
        rows.append(row)
    if not rows:
        raise ValueError(f'{league}: kunde inte tolka spelschemat; kontrollera API-formatet')
    return rows


def fetch(league):
    url = os.getenv(f'{league}_FEED_URL')
    if league in ('SHL', 'HA') and not url:
        return swedish_schedule(league)
    if not url:
        raise ValueError(f'{league}: saknar verifierad direktanslutning. Konfigurera {league}_FEED_URL till en matchlista i JSON-format.')
    headers = {}
    if os.getenv(f'{league}_FEED_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ[f'{league}_FEED_TOKEN']
    with httpx.Client(timeout=25, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        return normalize_flat(league, response.json())
