"""Swedish hockey schedules. Only confirmed regulation scores become FINISHED."""
import json
import os
import re
from datetime import datetime, timezone
from html import unescape

import httpx

SHL_SCHEDULE = "https://www.shl.se/api/sports-v2/game-schedule"
SHL_CATALOG = "https://www.shl.se/api/statistics-v2/layout-info"
HA_PAGE = "https://www.hockeyallsvenskan.se/pages/matcher"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Hockeyprognos/1.0)", "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}


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
    flat = [(integer(obj.get(f"home_score_p{i}")), integer(obj.get(f"away_score_p{i}"))) for i in (1, 2, 3)]
    if all(h is not None and a is not None for h, a in flat):
        return sum(h for h, _ in flat), sum(a for _, a in flat)
    periods = pick(obj, "periods", "periodScores", "period_scores")
    if not isinstance(periods, list):
        return None
    found = {}
    for index, period in enumerate(periods):
        if not isinstance(period, dict):
            continue
        number = integer(pick(period, "period", "periodNumber", "number"))
        if number is None:
            number = index + 1
        home = integer(pick(period, "home", "homeScore", "homeGoals"))
        away = integer(pick(period, "away", "awayScore", "awayGoals"))
        if number in (1, 2, 3) and home is not None and away is not None:
            found[number] = (home, away)
    if set(found) == {1, 2, 3}:
        return sum(found[i][0] for i in (1, 2, 3)), sum(found[i][1] for i in (1, 2, 3))
    return None


def regulation_score(obj, home=None, away=None):
    """Never infer regulation score from a final OT/SO score."""
    score = period_goals(obj)
    if score is not None:
        return score
    explicit = pick(obj, "regulationScore", "regulation_score")
    if isinstance(explicit, dict):
        h = integer(pick(explicit, "home", "homeScore", "homeGoals"))
        a = integer(pick(explicit, "away", "awayScore", "awayGoals"))
        if h is not None and a is not None:
            return h, a
    decided = str(pick(obj, "decided_in", "decidedIn", "decision", "status", "state") or "").lower()
    overtime = pick(obj, "overtime", "hasOvertime", "shootout", "hasShootout")
    # Explicitly confirmed regulation-only final, not merely a generic 'final' status.
    regulation_only = (decided in ("regulation", "regular", "60", "60min") or
                       obj.get("regulationOnly") is True or obj.get("decidedInRegulation") is True)
    if regulation_only and overtime is not True:
        h = integer(pick(obj, "home_goals", "home_score", "homeScore"))
        a = integer(pick(obj, "away_goals", "away_score", "awayScore"))
        if h is None and isinstance(home, dict):
            h = integer(pick(home, "score", "goals"))
        if a is None and isinstance(away, dict):
            a = integer(pick(away, "score", "goals"))
        if h is not None and a is not None:
            return h, a
    return None


def normalize_flat(league, data):
    if isinstance(data, dict):
        data = pick(data, "games", "matches", "data", "items")
    if not isinstance(data, list):
        raise ValueError(f"{league}: datakällan returnerade inte en matchlista")
    result = []
    for obj in data:
        if not isinstance(obj, dict):
            continue
        ident = pick(obj, "id", "game_uuid", "game_cms_id", "slug", "uuid", "gameId")
        when = pick(obj, "date", "scheduled_date_time", "raw_start_date_time", "start_date_time", "startDateTime", "startTime")
        home = pick(obj, "homeTeam", "home_team", "homeTeamInfo") or {}
        away = pick(obj, "awayTeam", "away_team", "awayTeamInfo") or {}
        hid = pick(obj, "home_id", "home_statnet_id", "home_team_code", "home_team_uuid") or pick(home, "uuid", "id", "code")
        aid = pick(obj, "away_id", "away_statnet_id", "away_team_code", "away_team_uuid") or pick(away, "uuid", "id", "code")
        hn = pick(obj, "home_name", "home_team_name", "home_team_names_short", "home_team_code") or pick(home, "name", "shortName", "teamName", "code")
        an = pick(obj, "away_name", "away_team_name", "away_team_names_short", "away_team_code") or pick(away, "name", "shortName", "teamName", "code")
        if isinstance(hn, dict):
            hn = pick(hn, "shortSite", "short", "full", "long", "name")
        if isinstance(an, dict):
            an = pick(an, "shortSite", "short", "full", "long", "name")
        if not all((ident, when, hid, aid, hn, an)):
            continue
        state = str(pick(obj, "status", "state", "gameState") or "").lower()
        finished = obj.get("is_completed") is True or state in ("finished", "final", "ft", "ot", "so", "post-game", "completed")
        row = dict(id=f"{league}:{ident}", date=when, home_id=f"{league}:{hid}", away_id=f"{league}:{aid}", home_name=hn, away_name=an, home_goals=None, away_goals=None, status="SCHEDULED")
        if finished:
            score = regulation_score(obj, home, away)
            if score is None:
                continue
            row.update(home_goals=score[0], away_goals=score[1], status="FINISHED")
        result.append(row)
    if not result:
        raise ValueError(f"{league}: inga giltiga matcher kunde tolkas")
    return result


def find_shl_season(payload, end_year):
    candidates = []
    def visit(node):
        if isinstance(node, list):
            for value in node:
                visit(value)
        elif isinstance(node, dict):
            if any(key in node for key in ("ssgtUuid", "ssgt_uuid", "seasonUuid")):
                candidates.append(node)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value)
    visit(payload)
    for row in candidates:
        season = pick(row, "seasonInfo", "season") or {}
        series = pick(row, "seriesInfo", "series") or {}
        game_type = pick(row, "gameTypeInfo", "gameType") or {}
        season_label = " ".join(str(x) for x in ((season.values() if isinstance(season, dict) else [season])))
        series_label = " ".join(str(x) for x in ((series.values() if isinstance(series, dict) else [series])))
        type_label = " ".join(str(x) for x in ((game_type.values() if isinstance(game_type, dict) else [game_type])))
        season_label += " " + str(pick(row, "seasonName", "seasonLabel") or "")
        if (str(end_year) in season_label or f"{end_year-1}/{str(end_year)[-2:]}" in season_label) and "SHL" in series_label.upper() and any(x in type_label.upper() for x in ("REGULAR", "GRUNDSERIE")):
            return row
    raise ValueError(f"SHL: hittade inte grundserien {end_year-1}/{end_year} i säsongskatalogen")


def parse_shl_schedule(payload):
    if isinstance(payload, dict):
        games = pick(payload, "gameInfo", "games", "gameSchedule", "data")
        if isinstance(games, dict):
            games = pick(games, "gameInfo", "games", "items")
    else:
        games = payload
    if not isinstance(games, list):
        raise ValueError("SHL: okänt format på spelschemat")
    rows = []
    for game in games:
        if not isinstance(game, dict):
            continue
        info = pick(game, "gameInfo") or game
        if not isinstance(info, dict):
            continue
        home = pick(game, "homeTeamInfo", "homeTeam") or pick(info, "homeTeamInfo", "homeTeam") or {}
        away = pick(game, "awayTeamInfo", "awayTeam") or pick(info, "awayTeamInfo", "awayTeam") or {}
        if not isinstance(home, dict) or not isinstance(away, dict):
            continue
        ident = pick(info, "uuid", "id") or pick(game, "uuid", "id")
        when = pick(info, "startDateTime", "startTime", "date") or pick(game, "startDateTime", "startTime")
        hid, aid = pick(home, "uuid", "id", "code"), pick(away, "uuid", "id", "code")
        hn, an = pick(home, "names", "name", "shortName", "teamName"), pick(away, "names", "name", "shortName", "teamName")
        if isinstance(hn, dict):
            hn = pick(hn, "shortSite", "short", "full", "long", "name")
        if isinstance(an, dict):
            an = pick(an, "shortSite", "short", "full", "long", "name")
        if not all((ident, when, hid, aid, hn, an)):
            continue
        state = str(pick(info, "state", "gameState", "status") or "").lower()
        finished = state in ("post-game", "final", "finished", "completed")
        row = dict(id=f"SHL:{ident}", date=when, home_id=f"SHL:{hid}", away_id=f"SHL:{aid}", home_name=hn, away_name=an, home_goals=None, away_goals=None, status="SCHEDULED")
        if finished:
            score = regulation_score(info, home, away) or regulation_score(game, home, away)
            if score is None:
                continue
            row.update(status="FINISHED", home_goals=score[0], away_goals=score[1])
        rows.append(row)
    if not rows:
        raise ValueError("SHL: kunde inte tolka någon match från spelschemat")
    return rows


def get_checked(client, url, **kwargs):
    response = client.get(url, **kwargs)
    if response.status_code >= 400:
        raise ValueError(f"HTTP {response.status_code} {response.url}; Content-Type={response.headers.get('content-type', '?')}; svar={response.text[:300]!r}")
    return response


def json_checked(response):
    try:
        return response.json()
    except ValueError as exc:
        raise ValueError(f"Förväntade JSON från {response.url}; Content-Type={response.headers.get('content-type', '?')}; svar={response.text[:300]!r}") from exc


def shl_schedule(client):
    now = datetime.now(timezone.utc)
    end_year = now.year + 1 if now.month >= 7 else now.year
    season = find_shl_season(json_checked(get_checked(client, SHL_CATALOG)), end_year)
    season_info = pick(season, "seasonInfo", "season") or {}
    series_info = pick(season, "seriesInfo", "series") or {}
    type_info = pick(season, "gameTypeInfo", "gameType") or {}
    season_uuid = pick(season, "seasonUuid") or pick(season_info, "uuid")
    series_uuid = pick(season, "seriesUuid") or pick(series_info, "uuid")
    game_type_uuid = pick(season, "gameTypeUuid") or pick(type_info, "uuid")
    if not all((season_uuid, series_uuid, game_type_uuid)):
        raise ValueError("SHL: katalogen saknar seasonUuid, seriesUuid eller gameTypeUuid")
    response = get_checked(client, SHL_SCHEDULE, params={"seasonUuid": season_uuid, "seriesUuid": series_uuid, "gameTypeUuid": game_type_uuid})
    return parse_shl_schedule(json_checked(response))


def _candidate_lists(value):
    """Find plausible match arrays in Next.js page data, without guessing one fixed path."""
    if isinstance(value, dict):
        for child in value.values():
            yield from _candidate_lists(child)
    elif isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value[:min(3, len(value))]):
            yield value
        for child in value:
            if isinstance(child, (dict, list)):
                yield from _candidate_lists(child)


def ha_schedule(client):
    response = get_checked(client, HA_PAGE)
    html = response.text
    scripts = re.findall(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, flags=re.I | re.S)
    if not scripts:
        raise ValueError("HA: __NEXT_DATA__ saknas på /pages/matcher; sidan kan använda ett annat Next.js-format. Kontrollera HTML/Network.")
    try:
        data = json.loads(unescape(scripts[0]))
    except ValueError as exc:
        raise ValueError("HA: __NEXT_DATA__ innehåller inte giltig JSON") from exc
    for candidate in _candidate_lists(data):
        try:
            return normalize_flat("HA", candidate)
        except ValueError:
            pass
    raise ValueError("HA: hittade Next.js-data men ingen matchlista som passar vår parser; spara ett anonymiserat svar för felsökning")


def swedish_schedule(league):
    with httpx.Client(timeout=25, follow_redirects=True, headers=HEADERS) as client:
        if league == "SHL":
            return shl_schedule(client)
        if league == "HA":
            return ha_schedule(client)
    raise ValueError(f"Okänd liga: {league}")


def fetch(league):
    url = os.getenv(f"{league}_FEED_URL")
    if league in ("SHL", "HA") and not url:
        return swedish_schedule(league)
    if not url:
        raise ValueError(f"{league}: konfigurera {league}_FEED_URL")
    headers = dict(HEADERS)
    token = os.getenv(f"{league}_FEED_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=25, follow_redirects=True, headers=headers) as client:
        return normalize_flat(league, json_checked(get_checked(client, url)))
