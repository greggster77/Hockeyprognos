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


def find_shl_season(payload, end_year):
    """Resolve the official season/series/game-type UUIDs, never guess numeric IDs."""
    candidates = []
    def visit(value):
        if isinstance(value, list):
            for item in value: visit(item)
        elif isinstance(value, dict):
            if ('ssgtUuid' in value or 'ssgt_uuid' in value) and ('season' in value or 'seasonInfo' in value or 'seasonName' in value):
                candidates.append(value)
            for child in value.values():
                if isinstance(child, (list, dict)): visit(child)
    visit(payload)
    for row in candidates:
        season = row.get('seasonInfo') or row.get('season') or {}
        if not isinstance(season, dict): season = {'name':str(season)}
        label = ' '.join(str(x) for x in (season.get('name'), season.get('code'), row.get('seasonName')) if x)
        series = row.get('seriesInfo') or row.get('series') or {}
        if not isinstance(series, dict): series = {'code':str(series)}
        game_type = row.get('gameTypeInfo') or row.get('gameType') or {}
        if not isinstance(game_type, dict): game_type = {'code':str(game_type)}
        series_label = ' '.join(str(x) for x in series.values())
        type_label = ' '.join(str(x) for x in game_type.values())
        if (str(end_year) in label or str(end_year-1) in label) and 'SHL' in series_label.upper() and ('REGULAR' in type_label.upper() or 'GRUNDSERIE' in type_label.upper()):
            return row
    raise ValueError(f'SHL: säsongen {end_year-1}/{end_year} saknas i ligans säsongskatalog eller har ett okänt format')


def parse_shl_schedule(payload):
    """Official schedule is an envelope with gameInfo entries."""
    if isinstance(payload, dict):
        games = pick(payload, 'gameInfo', 'games', 'gameSchedule', 'data')
        if isinstance(games, dict): games = pick(games, 'gameInfo', 'games', 'items')
    else:
        games = payload
    if not isinstance(games, list):
        raise ValueError('SHL: okänt svar från spelschema-API:t')
    rows = []
    for game in games:
        if not isinstance(game, dict): continue
        info = pick(game, 'gameInfo') or game
        if not isinstance(info, dict): continue
        home = pick(game, 'homeTeamInfo', 'homeTeam') or pick(info, 'homeTeamInfo', 'homeTeam') or {}
        away = pick(game, 'awayTeamInfo', 'awayTeam') or pick(info, 'awayTeamInfo', 'awayTeam') or {}
        if not isinstance(home, dict) or not isinstance(away, dict): continue
        ident = pick(info, 'uuid', 'id') or pick(game, 'uuid', 'id')
        when = pick(info, 'startDateTime', 'startTime', 'date') or pick(game, 'startDateTime', 'startTime')
        hid, aid = pick(home, 'uuid', 'id', 'code'), pick(away, 'uuid', 'id', 'code')
        hn, an = pick(home, 'names', 'name', 'shortName', 'teamName'), pick(away, 'names', 'name', 'shortName', 'teamName')
        if isinstance(hn, dict): hn = pick(hn, 'shortSite', 'short', 'full', 'long', 'name')
        if isinstance(an, dict): an = pick(an, 'shortSite', 'short', 'full', 'long', 'name')
        if not all((ident, when, hid, aid, hn, an)): continue
        state = str(pick(info, 'state', 'gameState', 'status') or '').lower()
        row = dict(id=f'SHL:{ident}', date=when, home_id=f'SHL:{hid}', away_id=f'SHL:{aid}', home_name=hn, away_name=an, home_goals=None, away_goals=None, status='SCHEDULED')
        if state in ('post-game', 'final', 'finished'):
            scores = period_goals(game) or period_goals(info)
            overtime = pick(info, 'overtime', 'shootout') or pick(game, 'overtime', 'shootout')
            if scores is None and not overtime:
                h, a = integer(pick(home, 'score', 'goals')), integer(pick(away, 'score', 'goals'))
                if h is not None and a is not None: scores = (h, a)
            if scores is None: continue
            row.update(status='FINISHED', home_goals=scores[0], away_goals=scores[1])
        rows.append(row)
    if not rows: raise ValueError('SHL: kunde inte tolka spelschemat')
    return rows


def swedish_schedule(league):
    year = datetime.now(timezone.utc).year
    end_year = year + 1 if datetime.now(timezone.utc).month >= 7 else year
    if league == 'HA':
        raise ValueError('HA: tidigare sports-v2-adress returnerar inte JSON. En verifierad HA-källa behövs; ange HA_FEED_URL med matchlista i JSON-format.')
    with httpx.Client(timeout=25, follow_redirects=True, headers={'User-Agent':'Mozilla/5.0', 'Accept':'application/json'}) as client:
        directory = client.get('https://www.shl.se/api/statistics-v2/layout-info')
        directory.raise_for_status()
        season = find_shl_season(directory.json(), end_year)
        season_info = season.get('seasonInfo') or season.get('season') or {}
        game_type = season.get('gameTypeInfo') or season.get('gameType') or {}
        season_uuid = pick(season, 'seasonUuid') or (pick(season_info, 'uuid') if isinstance(season_info, dict) else None)
        game_type_uuid = pick(season, 'gameTypeUuid') or (pick(game_type, 'uuid') if isinstance(game_type, dict) else None)
        if not season_uuid or not game_type_uuid:
            raise ValueError('SHL: säsongskatalogen saknar seasonUuid/gameTypeUuid')
        response = client.get(SHL_SCHEDULE, params={'seasonUuid':season_uuid, 'gameTypeUuid':game_type_uuid})
        response.raise_for_status()
        return parse_shl_schedule(response.json())


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
