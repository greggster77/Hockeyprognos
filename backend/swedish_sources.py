"""Swedish hockey schedule adapters. Finished scores refer to 60 minutes only."""
import json
import logging
import os
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin

import httpx

SHL_SCHEDULE = 'https://www.shl.se/api/sports-v2/game-schedule'
SHL_CATALOG = 'https://www.shl.se/api/statistics-v2/layout-info'
HA_PAGE = 'https://www.hockeyallsvenskan.se/pages/matcher'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; Hockeyprognos/1.0)', 'Accept': 'application/json, text/html;q=0.9, */*;q=0.8'}


def pick(obj, *keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if obj.get(key) is not None:
            return obj[key]
    return None


def integer(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def period_goals(obj):
    if not isinstance(obj, dict):
        return None
    flat = [(integer(obj.get(f'home_score_p{i}')), integer(obj.get(f'away_score_p{i}'))) for i in (1, 2, 3)]
    if all(h is not None and a is not None for h, a in flat):
        return sum(h for h, _ in flat), sum(a for _, a in flat)
    periods = pick(obj, 'periods', 'periodScores', 'period_scores')
    if not isinstance(periods, list):
        return None
    found = {}
    for index, period in enumerate(periods):
        if not isinstance(period, dict):
            continue
        number = integer(pick(period, 'period', 'periodNumber', 'number'))
        if number is None:
            number = index + 1
        home = integer(pick(period, 'home', 'homeScore', 'homeGoals'))
        away = integer(pick(period, 'away', 'awayScore', 'awayGoals'))
        if number in (1, 2, 3) and home is not None and away is not None:
            found[number] = (home, away)
    if set(found) == {1, 2, 3}:
        return sum(found[i][0] for i in (1, 2, 3)), sum(found[i][1] for i in (1, 2, 3))
    return None


def regulation_score(obj, home=None, away=None):
    score = period_goals(obj)
    if score is not None:
        return score
    explicit = pick(obj, 'regulationScore', 'regulation_score')
    if isinstance(explicit, dict):
        h = integer(pick(explicit, 'home', 'homeScore', 'homeGoals'))
        a = integer(pick(explicit, 'away', 'awayScore', 'awayGoals'))
        if h is not None and a is not None:
            return h, a
    # SHL game-schedule provides final scores and OT/SO flags, not period scores.
    # In an OT/SO game, regulation ended level. The winner's final tally
    # includes one deciding goal; the losing team's tally is the 60-min score.
    if obj.get('overtime') is True or obj.get('shootout') is True:
        h = integer(pick(home, 'score', 'goals')) if isinstance(home, dict) else None
        a = integer(pick(away, 'score', 'goals')) if isinstance(away, dict) else None
        if h is not None and a is not None and abs(h - a) == 1:
            return min(h, a), min(h, a)
        return None
    # Completed SHL games without OT/SO have regulation final scores.
    if str(obj.get('state', '')).lower() == 'post-game':
        h = integer(pick(home, 'score', 'goals')) if isinstance(home, dict) else None
        a = integer(pick(away, 'score', 'goals')) if isinstance(away, dict) else None
        if h is not None and a is not None:
            return h, a
    decided = str(pick(obj, 'decided_in', 'decidedIn', 'decision') or '').lower()
    overtime = pick(obj, 'overtime', 'hasOvertime', 'shootout', 'hasShootout')
    regulation_only = decided in ('regulation', 'regular', '60', '60min') or obj.get('regulationOnly') is True or obj.get('decidedInRegulation') is True
    if regulation_only and overtime is not True:
        h = integer(pick(obj, 'home_goals', 'home_score', 'homeScore'))
        a = integer(pick(obj, 'away_goals', 'away_score', 'awayScore'))
        if h is None and isinstance(home, dict):
            h = integer(pick(home, 'score', 'goals'))
        if a is None and isinstance(away, dict):
            a = integer(pick(away, 'score', 'goals'))
        if h is not None and a is not None:
            return h, a
    return None


def normalize_flat(league, data):
    if isinstance(data, dict):
        data = pick(data, 'games', 'matches', 'data', 'items')
    if not isinstance(data, list):
        raise ValueError(f'{league}: datakällan returnerade inte en matchlista')
    result = []
    for obj in data:
        if not isinstance(obj, dict):
            continue
        ident = pick(obj, 'id', 'game_uuid', 'game_cms_id', 'slug', 'uuid', 'gameId')
        when = pick(obj, 'date', 'scheduled_date_time', 'raw_start_date_time', 'start_date_time', 'rawStartDateTime', 'startDateTime', 'startTime')
        home = pick(obj, 'homeTeam', 'home_team', 'homeTeamInfo') or {}
        away = pick(obj, 'awayTeam', 'away_team', 'awayTeamInfo') or {}
        hid = pick(obj, 'home_id', 'home_statnet_id', 'home_team_code', 'home_team_uuid') or pick(home, 'uuid', 'id', 'code')
        aid = pick(obj, 'away_id', 'away_statnet_id', 'away_team_code', 'away_team_uuid') or pick(away, 'uuid', 'id', 'code')
        hn = pick(obj, 'home_name', 'home_team_name', 'home_team_names_short', 'home_team_code') or pick(home, 'names', 'name', 'shortName', 'teamName', 'code')
        an = pick(obj, 'away_name', 'away_team_name', 'away_team_names_short', 'away_team_code') or pick(away, 'names', 'name', 'shortName', 'teamName', 'code')
        if isinstance(hn, dict):
            hn = pick(hn, 'shortSite', 'short', 'full', 'long', 'name')
        if isinstance(an, dict):
            an = pick(an, 'shortSite', 'short', 'full', 'long', 'name')
        if not all((ident, when, hid, aid, hn, an)):
            continue
        state = str(pick(obj, 'status', 'state', 'gameState') or '').lower()
        finished = obj.get('is_completed') is True or state in ('finished', 'final', 'ft', 'ot', 'so', 'post-game', 'completed')
        row = dict(id=f'{league}:{ident}', date=when, home_id=f'{league}:{hid}', away_id=f'{league}:{aid}', home_name=hn, away_name=an, home_goals=None, away_goals=None, status='SCHEDULED')
        if finished:
            score = regulation_score(obj, home, away)
            if score is None:
                continue
            row.update(home_goals=score[0], away_goals=score[1], status='FINISHED')
        result.append(row)
    if not result:
        raise ValueError(f'{league}: inga giltiga matcher kunde tolkas')
    return result


def find_shl_season(payload, end_year):
    candidates = []

    def visit(node):
        if isinstance(node, list):
            for value in node:
                visit(value)
        elif isinstance(node, dict):
            if pick(node, 'seasonUuid', 'season_uuid', 'ssgtUuid', 'ssgt_uuid') or isinstance(pick(node, 'seasonInfo', 'season'), dict):
                candidates.append(node)
            for child in node.values():
                if isinstance(child, (list, dict)):
                    visit(child)

    visit(payload)
    for candidate in candidates:
        info = pick(candidate, 'seasonInfo', 'season')
        label = ' '.join(str(v) for v in (pick(candidate, 'seasonName', 'name', 'label'), pick(info, 'name', 'seasonName')) if v)
        if (f'{end_year - 1}/{end_year}' in label or str(end_year) in label) and pick(pick(candidate, 'gameType', 'gameTypeInfo'), 'code') == 'regular' and pick(pick(candidate, 'series', 'seriesInfo'), 'code') == 'SHL':
            return candidate
    raise ValueError(f'SHL: hittade ingen säsong för {end_year} i katalogen')


def parse_shl_schedule(payload):
    if isinstance(payload, list):
        return normalize_flat('SHL', payload)
    if isinstance(payload, dict):
        for key in ('gameInfo', 'games', 'matches', 'items', 'data'):
            node = payload.get(key)
            if isinstance(node, list):
                return normalize_flat('SHL', node)
            if isinstance(node, dict):
                try:
                    return parse_shl_schedule(node)
                except ValueError:
                    pass
    raise ValueError('SHL: matchlistan kunde inte hittas i API-svaret')


def _ha_embedded_payload(html):
    match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.I | re.S)
    if match:
        return json.loads(unescape(match.group(1)))
    raise ValueError('HA: ingen verifierbar JSON-matchlista i sidans HTML; kontrollera HA_FEED_URL')


def _find_match_lists(node):
    if isinstance(node, dict):
        for key in ('games', 'matches', 'items'):
            value = node.get(key)
            if isinstance(value, list) and value and any(isinstance(x, dict) and pick(x, 'homeTeam', 'home_team', 'home_name') for x in value):
                yield value
        for value in node.values():
            yield from _find_match_lists(value)
    elif isinstance(node, list):
        for value in node:
            yield from _find_match_lists(value)


def _ha_response_shape(value, depth=0):
    """Log only JSON field names and types, never raw response values."""
    if depth >= 4:
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k)[:64]: _ha_response_shape(v, depth + 1) for k, v in list(value.items())[:16]}
    if isinstance(value, list):
        return {'type': 'list', 'count': len(value),
                'first': _ha_response_shape(value[0], depth + 1) if value else None}
    return type(value).__name__


# HA publishes short match codes while its directory contains canonical team codes.
# Explicit aliases prevent LIF/Leksand and MORA/MoDo from being confused.
HA_ALIASES = {
    'LIF': 'Leksands IF', 'VIS': 'Visby/Roma HK', 'AIK': 'AIK',
    'SSK': 'Södertälje SK', 'KHC': 'Kalmar HC', 'AIS': 'Almtuna IS',
    'MORA': 'Mora IK', 'MODO': 'MoDo Hockey', 'MO DO': 'MoDo Hockey',
    'BIK': 'BIK Karlskoga', 'IKO': 'IK Oskarshamn',
    'NYB': 'Nybro Vikings IF', 'VIK': 'Västerås IK',
    'VHC': 'Vimmerby HC', 'OIK': 'Östersunds IK',
}


def _ha_key(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').casefold().translate(
        str.maketrans({'å': 'a', 'ä': 'a', 'ö': 'o'})))


def _ha_team_index(teams):
    index = {}
    for team in teams:
        for name in (team['name'], team['fullName'], team['code']):
            if name:
                index[_ha_key(name)] = team
    for alias, canonical in HA_ALIASES.items():
        team = index.get(_ha_key(canonical))
        if team:
            index[_ha_key(alias)] = team
    return index


def _ha_teams(payload):
    """Official club names and logos from the same HA response."""
    teams = []
    for team in payload.get('teams', []) if isinstance(payload, dict) else []:
        if not isinstance(team, dict):
            continue
        logos = team.get('logos') or {}
        icon = next((logos.get(k) for k in ('medium', 'small', 'large', 'icon', 'xlarge') if isinstance(logos.get(k), str) and logos.get(k)), '') if isinstance(logos, dict) else ''
        if icon:
            icon = urljoin('https://hockeyallsvenskan.se/', icon)
        if not icon.startswith('https://'):
            icon = ''
        teams.append({'name': team.get('name') or team.get('fullName') or team.get('teamCode') or '',
                      'fullName': team.get('fullName') or '', 'code': team.get('teamCode') or '', 'icon': icon})
    return teams


def _ha_date(game):
    """Date and Time are separate fields in the actual HA API response."""
    day = pick(game, 'Date', 'date', 'scheduled_date_time', 'start_date_time')
    if not day:
        return None
    day = str(day).strip()
    if 'T' in day or ' ' in day:
        return day
    clock = str(pick(game, 'Time', 'time') or '00:00').strip()
    return day + 'T' + clock if clock else day + 'T00:00'


def _ha_period_score(game):
    """Require all three regulation periods; never count overtime/shootout."""
    periods = pick(game, 'PeriodScores', 'periodScores', 'periods')
    if not isinstance(periods, list):
        return None
    scores = []
    for i, period in enumerate(periods):
        if not isinstance(period, dict):
            continue
        number = integer(pick(period, 'Period', 'period', 'PeriodNumber', 'periodNumber', 'number'))
        if number is None:
            number = i + 1
        if number not in (1, 2, 3):
            continue
        nested = pick(period, 'Score', 'score', 'GameResult', 'gameResult', 'result')
        source = nested if isinstance(nested, dict) else period
        h = integer(pick(source, 'Home', 'home', 'HomeScore', 'homeScore', 'homeGoals', 'home_score'))
        a = integer(pick(source, 'Away', 'away', 'AwayScore', 'awayScore', 'awayGoals', 'away_score'))
        if (h is None or a is None) and isinstance(nested, str):
            found = re.fullmatch(r'\s*(\d+)\s*[-:]\s*(\d+)\s*', nested)
            if found:
                h, a = int(found.group(1)), int(found.group(2))
        if h is not None and a is not None:
            scores.append((number, h, a))
    by_period = {n: (h, a) for n, h, a in scores}
    if set(by_period) != {1, 2, 3}:
        return None
    return (sum(by_period[n][0] for n in (1, 2, 3)), sum(by_period[n][1] for n in (1, 2, 3)))


def parse_ha_stats(payload):
    """Parse the observed HA JSON envelope: results, Date, HomeTeam, PeriodScores."""
    games = payload.get('results') if isinstance(payload, dict) else None
    if not isinstance(games, list):
        legacy = payload.get('data', {}).get('rows') if isinstance(payload, dict) and isinstance(payload.get('data'), dict) else None
        if isinstance(legacy, list):
            normalized = []
            for game in legacy:
                home = pick(game, 'home_team_code', 'homeTeamCode')
                away = pick(game, 'away_team_code', 'awayTeamCode')
                when = pick(game, 'date', 'scheduled_date_time')
                if not (home and away and when):
                    continue
                item = dict(id=f'HA:{when}-{home}-{away}', date=when, home_id='HA:'+str(home),
                            away_id='HA:'+str(away), home_name=str(home), away_name=str(away), status='SCHEDULED')
                decided = str(pick(game, 'decided_in', 'decidedIn') or '').lower()
                if decided:
                    score = period_goals(game)
                    if score is None and decided in ('ft', 'regulation'):
                        h = integer(pick(game, 'home_score', 'home_goals'))
                        a = integer(pick(game, 'away_score', 'away_goals'))
                        if h is not None and a is not None:
                            score = (h, a)
                    if score is None:
                        continue
                    item.update(home_goals=score[0], away_goals=score[1], status='FINISHED')
                normalized.append(item)
            if normalized:
                return normalized
        raise ValueError('HA: statistik-API saknar verifierbar results-lista')
    teams = _ha_teams(payload)
    team_index = _ha_team_index(teams)
    normalized = []
    unverified_finished = 0
    period_example = None
    for game in games:
        if not isinstance(game, dict):
            continue
        home = pick(game, 'HomeTeam', 'homeTeam', 'home_team_name')
        away = pick(game, 'AwayTeam', 'awayTeam', 'away_team_name')
        when = _ha_date(game)
        if not (home and away and when):
            continue
        home = str(home); away = str(away)
        ht = team_index.get(_ha_key(home), {})
        at = team_index.get(_ha_key(away), {})
        # Stable per-team IDs across imports, using official team code when available.
        home_id = str(ht.get('code') or home)
        away_id = str(at.get('code') or away)
        ident = pick(game, 'GameId', 'gameId', 'id', 'statnet_game_number') or f'{when}-{home_id}-{away_id}'
        item = {'id': 'HA:' + str(ident), 'date': when,
                'home_id': 'HA:' + home_id, 'away_id': 'HA:' + away_id,
                'home_name': ht.get('fullName') or ht.get('name') or HA_ALIASES.get(home.upper(), home),
                'away_name': at.get('fullName') or at.get('name') or HA_ALIASES.get(away.upper(), away),
                'status': 'SCHEDULED'}
        final = pick(game, 'GameResult', 'gameResult')
        if isinstance(final, dict) and integer(pick(final, 'Home', 'home')) is not None and integer(pick(final, 'Away', 'away')) is not None:
            score = _ha_period_score(game)
            decided = str(pick(game, 'decided_in', 'decidedIn') or '').casefold()
            if score is None and decided in ('ft', 'regulation', 'regular', '60', '60min'):
                score = (integer(pick(final, 'Home', 'home')), integer(pick(final, 'Away', 'away')))
            # If period shape is unknown, never use OT/SO final score as regulation score.
            if score is None:
                unverified_finished += 1
                if period_example is None:
                    periods = pick(game, 'PeriodScores', 'periodScores', 'periods')
                    period_example = _ha_response_shape({'periods': periods})
                # Never mislabel a played match as upcoming or use OT goals.
                continue
            item.update(home_goals=score[0], away_goals=score[1], status='FINISHED')
        normalized.append(item)
    if not normalized:
        logging.getLogger(__name__).warning('HA API diagnostic: shape=%s', json.dumps(_ha_response_shape(payload), ensure_ascii=False)[:2400])
        raise ValueError('HA: results innehöll inga verifierbara matcher')
    if unverified_finished:
        logging.getLogger(__name__).warning('HA regulation scores unverified: %d games; period structure=%s', unverified_finished, json.dumps(period_example, ensure_ascii=False)[:1000])
    logging.getLogger(__name__).info('HA parsed: %d matches, %d finished (60 min), %d scheduled, %d registered teams',
        len(normalized), sum(g['status'] == 'FINISHED' for g in normalized),
        sum(g['status'] == 'SCHEDULED' for g in normalized), len(teams))
    return normalized


def ha_stats_payload(client, season_start):
    url = 'https://hockeyallsvenskan.se/api/all-time-games-stats'
    body = dict(league='HA', phase='HA', team_side='all', team='all',
                against_team='all', all_results='all', game_status='all',
                decided_in='all', categories='all', page=1, page_size=1000,
                season=str(season_start))
    response = client.post(url, json=body, headers={**HEADERS, 'Accept': 'application/json'})
    response.raise_for_status()
    return response.json()


def ha_stats_fallback(client, season_start):
    return parse_ha_stats(ha_stats_payload(client, season_start))


def swedish_schedule(league):
    now = datetime.now(timezone.utc)
    end_year = now.year + (now.month >= 7)
    with httpx.Client(timeout=25, follow_redirects=True, headers=HEADERS) as client:
        if league == 'SHL':
            catalog = client.get(SHL_CATALOG)
            catalog.raise_for_status()
            season = find_shl_season(catalog.json(), end_year)
            season_info = pick(season, 'seasonInfo', 'season')
            game_type = pick(season, 'gameTypeInfo', 'gameType')
            series = pick(season, 'seriesInfo', 'series')
            season_uuid = pick(season, 'seasonUuid') or pick(season_info, 'uuid')
            game_type_uuid = pick(season, 'gameTypeUuid') or pick(game_type, 'uuid')
            series_uuid = pick(season, 'seriesUuid') or pick(series, 'uuid')
            if not all((season_uuid, game_type_uuid, series_uuid)):
                raise ValueError('SHL: katalogen saknar seasonUuid, gameTypeUuid eller seriesUuid')
            response = client.get(SHL_SCHEDULE, params={'seasonUuid': season_uuid, 'gameTypeUuid': game_type_uuid, 'seriesUuid': series_uuid})
            response.raise_for_status()
            return parse_shl_schedule(response.json())
        if league == 'HA':
            response = client.get(HA_PAGE)
            response.raise_for_status()
            try:
                payload = _ha_embedded_payload(response.text)
                for matches in _find_match_lists(payload):
                    try:
                        return normalize_flat('HA', matches)
                    except ValueError:
                        continue
            except (ValueError, json.JSONDecodeError):
                pass
            return ha_stats_fallback(client, end_year - 1)
    raise ValueError(f'Okänd svensk liga: {league}')


def fetch(league):
    if league not in ('SHL', 'HA'):
        raise ValueError(f'Okänd liga: {league}')
    feed_url = os.getenv(f'{league}_FEED_URL')
    if feed_url:
        with httpx.Client(timeout=25, follow_redirects=True, headers=HEADERS) as client:
            response = client.get(feed_url)
            response.raise_for_status()
            return normalize_flat(league, response.json())
    return swedish_schedule(league)
