"""Swedish hockey schedule adapters. Finished scores refer to 60 minutes only."""
import json
import os
import re
from datetime import datetime, timezone
from html import unescape

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


def ha_stats_fallback(client, season_start):
    """HA's documented keyless POST statistics route; avoid scraping Next.js HTML.

    Only regulation period totals are used for finished matches. Never silently
    treat OT/SO final scores as 60-minute results.
    """
    url = 'https://hockeyallsvenskan.se/api/all-time-games-stats'
    body = dict(league='HA', phase='HA', team_side='all', team='all',
                against_team='all', all_results='all', game_status='all',
                decided_in='all', categories='all', page=1, page_size=1000,
                season=str(season_start))
    response = client.post(url, json=body, headers={**HEADERS, 'Accept': 'application/json'})
    response.raise_for_status()
    payload = response.json()
    candidates = list(_find_ha_stats_lists(payload))
    for games in candidates:
        normalized = []
        for game in games:
            home = pick(game, 'home_team_code', 'homeTeamCode', 'home_team_name', 'homeTeamName')
            away = pick(game, 'away_team_code', 'awayTeamCode', 'away_team_name', 'awayTeamName')
            when = pick(game, 'scheduled_date_time', 'start_date_time', 'date', 'game_date', 'gameDate')
            if not (home and away and when):
                continue
            decided = str(pick(game, 'decided_in', 'decidedIn') or '').lower()
            is_played = decided in ('ft', 'ot', 'so', 'wo', 'regulation')
            if decided == 'wo':
                continue
            item = dict(id='HA:' + str(pick(game, 'statnet_game_number', 'game_cms_id', 'game_id', 'id') or f'{when}-{home}-{away}'),
                        date=when, home_id='HA:' + str(home), away_id='HA:' + str(away),
                        home_name=str(pick(game, 'home_team_name', 'homeTeamName') or home),
                        away_name=str(pick(game, 'away_team_name', 'awayTeamName') or away),
                        status='FINISHED' if is_played else 'SCHEDULED')
            if is_played:
                score = period_goals(game)
                if score is None:
                    # For FT only, a verified regulation decision makes final goals safe.
                    if decided in ('ft', 'regulation'):
                        h = integer(pick(game, 'home_score', 'home_goals', 'homeScore'))
                        a = integer(pick(game, 'away_score', 'away_goals', 'awayScore'))
                        score = (h, a) if h is not None and a is not None else None
                if score is None:
                    continue
                item.update(home_goals=score[0], away_goals=score[1])
            normalized.append(item)
        if normalized:
            return normalized
    raise ValueError('HA: statistik-API svarade men ingen verifierbar matchlista kunde tolkas')


def _find_ha_stats_lists(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _find_ha_stats_lists(value)
    elif isinstance(node, list):
        if node and all(isinstance(x, dict) for x in node) and any(
                pick(x, 'home_team_code', 'homeTeamCode', 'home_team_name', 'homeTeamName') for x in node):
            yield node
        else:
            for value in node:
                yield from _find_ha_stats_lists(value)


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
