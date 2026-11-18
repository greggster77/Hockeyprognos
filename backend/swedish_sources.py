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
