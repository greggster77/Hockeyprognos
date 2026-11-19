
import os
import json
import logging
import threading
import time

from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
from pathlib import Path
from contextlib import asynccontextmanager

import httpx

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler

from model import predict
import odds
from storage import connect as storage_connect, USING_NEON


ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.getenv("DB_PATH", str(ROOT / "hockey.db")))

LEAGUES = {
    "SHL": "SHL",
    "HA": "HockeyAllsvenskan",
    "NHL": "NHL",
}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Europe/Stockholm")
sync_lock = threading.Lock()

# Small in-process read cache. It avoids repeated Neon connections and SQL
# queries when many users request the same league/date window.
MATCH_RESPONSE_TTL = 20
_match_response_cache = {}
_match_response_lock = threading.Lock()

def invalidate_match_response_cache():
    with _match_response_lock:
        _match_response_cache.clear()



def db():
    return storage_connect(DB)


def init():
    DB.parent.mkdir(parents=True, exist_ok=True)

    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS matches (
            id TEXT PRIMARY KEY,
            league TEXT NOT NULL,
            date TEXT NOT NULL,
            home_id TEXT NOT NULL,
            away_id TEXT NOT NULL,
            home_name TEXT NOT NULL,
            away_name TEXT NOT NULL,
            home_goals INTEGER,
            away_goals INTEGER,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS predictions (
            match_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            home_win REAL,
            draw REAL,
            away_win REAL,
            expected_home REAL,
            expected_away REAL,
            details TEXT NOT NULL,
            FOREIGN KEY(match_id) REFERENCES matches(id)
        );

        CREATE TABLE IF NOT EXISTS forecast_archive (
            match_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            home_win REAL NOT NULL,
            draw REAL NOT NULL,
            away_win REAL NOT NULL,
            expected_home REAL,
            expected_away REAL,
            details TEXT NOT NULL,
            FOREIGN KEY(match_id) REFERENCES matches(id)
        );

        CREATE TABLE IF NOT EXISTS prediction_results (
            match_id TEXT PRIMARY KEY,
            actual TEXT NOT NULL,
            brier REAL NOT NULL,
            evaluated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stats_snapshots (
            category TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            payload TEXT NOT NULL,
            record_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stats_fetch_status (
            category TEXT PRIMARY KEY,
            attempted_at TEXT NOT NULL,
            http_status INTEGER,
            record_count INTEGER NOT NULL,
            error TEXT
        );
        CREATE TABLE IF NOT EXISTS sync_status (
            league TEXT PRIMARY KEY,
            updated_at TEXT,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
        CREATE INDEX IF NOT EXISTS idx_matches_league_date ON matches(league, date);
        CREATE INDEX IF NOT EXISTS idx_matches_history ON matches(league, status, date);
        """)
        odds.setup(c)


def now():
    return datetime.now(timezone.utc).isoformat()


def store(league, games):
    with db() as c:
        for g in games:
            c.execute(
                """
                INSERT INTO matches
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    date=excluded.date,
                    home_name=excluded.home_name,
                    away_name=excluded.away_name,
                    home_goals=excluded.home_goals,
                    away_goals=excluded.away_goals,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    g["id"],
                    league,
                    g["date"],
                    g["home_id"],
                    g["away_id"],
                    g["home_name"],
                    g["away_name"],
                    g.get("home_goals"),
                    g.get("away_goals"),
                    g["status"],
                    now(),
                ),
            )

        c.execute(
            """
            INSERT INTO sync_status VALUES (?,?,NULL)
            ON CONFLICT(league) DO UPDATE SET
                updated_at=excluded.updated_at,
                error=NULL
            """,
            (league, now()),
        )

    invalidate_match_response_cache()
    log.info("Stored %s matches for %s", len(games), league)


def error(league, message):
    with db() as c:
        c.execute(
            """
            INSERT INTO sync_status VALUES (?,?,?)
            ON CONFLICT(league) DO UPDATE SET
                updated_at=excluded.updated_at,
                error=excluded.error
            """,
            (league, now(), str(message)[:500]),
        )


def team_name(team):
    place = team.get("placeName", {})
    common = team.get("commonName", {})

    if isinstance(place, dict):
        place = place.get("default", "")

    if isinstance(common, dict):
        common = common.get("default", "")

    name = f"{place} {common}".strip()
    return name or team.get("abbrev", "Okänt lag")


def normalize_nhl(game):
    gid = str(game["id"])
    home = game["homeTeam"]
    away = game["awayTeam"]

    return {
        "id": "NHL:" + gid,
        "date": game["startTimeUTC"],
        "home_id": "NHL:" + str(home["id"]),
        "away_id": "NHL:" + str(away["id"]),
        "home_name": team_name(home),
        "away_name": team_name(away),
        "home_goals": None,
        "away_goals": None,
        "status": "SCHEDULED",
    }


def nhl_final(game, landing):
    """
    Calculate regulation result from periods 1, 2 and 3.
    Overtime and shootout goals are excluded.
    """

    scoring = landing.get("summary", {}).get("scoring", [])

    home = game["homeTeam"]
    away = game["awayTeam"]

    home_abbrev = home.get("abbrev")
    away_abbrev = away.get("abbrev")

    if not home_abbrev or not away_abbrev:
        raise ValueError("Team abbreviations missing")

    home_goals = 0
    away_goals = 0

    periods_found = set()

    for period in scoring:
        descriptor = period.get("periodDescriptor", {})
        number = descriptor.get("number")

        if number not in (1, 2, 3):
            continue

        periods_found.add(number)

        goals = period.get("goals", [])

        for goal in goals:
            team = goal.get("teamAbbrev")

            if isinstance(team, dict):
                team = team.get("default")

            if team == home_abbrev:
                home_goals += 1

            elif team == away_abbrev:
                away_goals += 1

            else:
                raise ValueError(
                    f"Unknown scoring team: {team}"
                )

    if periods_found != {1, 2, 3}:
        raise ValueError(
            "Incomplete regulation scoring data"
        )

    return {
        "id": "NHL:" + str(game["id"]),
        "date": game["startTimeUTC"],
        "home_id": "NHL:" + str(home["id"]),
        "away_id": "NHL:" + str(away["id"]),
        "home_name": team_name(home),
        "away_name": team_name(away),
        "home_goals": home_goals,
        "away_goals": away_goals,
        "status": "FINISHED",
    }


def fetch_nhl(start=None, end=None):
    """
    Fetch NHL schedule and completed games.
    Use only official NHL API data.
    """

    today = datetime.now(ZoneInfo("Europe/Stockholm")).date()
    # Current NHL season starts in autumn. Include all its regular-season
    # games, so every team can build a 20-game form window.
    season_year = today.year if today.month >= 9 else today.year - 1
    if start is None:
        start = date(season_year, 10, 1)
    if end is None:
        end = today + timedelta(days=21)

    games = {}
    # Avoid repeatedly downloading detailed scoring for completed games.
    with db() as c:
        cached_final = {row["id"]: dict(row) for row in c.execute(
            "SELECT * FROM matches WHERE league='NHL' AND status='FINISHED'"
        )}

    with httpx.Client(
        timeout=20,
        follow_redirects=True
    ) as client:

        d = start

        while d <= end:
            url = (
                "https://api-web.nhle.com/v1/schedule/"
                + d.isoformat()
            )

            response = client.get(url)
            response.raise_for_status()

            for week in response.json().get("gameWeek", []):
                for game in week.get("games", []):
                    games[str(game["id"])] = game

            d += timedelta(days=7)

        output = []

        finished = 0
        scheduled = 0
        skipped = 0

        for game in games.values():
            if game.get("gameType") != 2:
                continue

            state = game.get("gameState")

            if state in ("FINAL", "OFF"):
                try:
                    cached = cached_final.get("NHL:" + str(game["id"]))
                    if cached and cached["home_goals"] is not None and cached["away_goals"] is not None:
                        output.append({key: cached[key] for key in (
                            "id", "date", "home_id", "away_id", "home_name", "away_name",
                            "home_goals", "away_goals", "status")})
                        finished += 1
                        continue
                    url = (
                        "https://api-web.nhle.com/v1/"
                        f"gamecenter/{game['id']}/landing"
                    )

                    response = client.get(url)
                    response.raise_for_status()

                    row = nhl_final(
                        game,
                        response.json()
                    )

                    output.append(row)
                    finished += 1

                except (
                    KeyError,
                    ValueError,
                    TypeError,
                    httpx.HTTPError,
                ) as exc:
                    skipped += 1

                    log.warning(
                        "NHL game %s skipped: %s",
                        game.get("id"),
                        exc,
                    )

            else:
                row = normalize_nhl(game)
                # NHL LIVE/CRIT games are not upcoming. No unverified 60-minute score.
                if state in ("LIVE", "CRIT"):
                    row["status"] = "LIVE"
                elif state not in ("FUT", "PRE"):
                    row["status"] = "PENDING"
                output.append(row)
                scheduled += 1

    log.info(
        "NHL import completed: %s finished, "
        "%s scheduled, %s skipped",
        finished,
        scheduled,
        skipped,
    )

    return output


def fetch_swedish(league):
    """Import Swedish league schedules from public league endpoints.

    Results are used only when regulation scores are verifiable.
    Custom JSON feeds can still be configured with *_FEED_URL.
    """
    from swedish_sources import fetch
    return fetch(league)


class HistoricalMatch:
    def __init__(self, row):
        self.date = row["date"]
        self.home_id = row["home_id"]
        self.away_id = row["away_id"]
        self.home_goals = row["home_goals"]
        self.away_goals = row["away_goals"]


def recompute():
    with db() as c:

        upcoming = c.execute(
            """
            SELECT * FROM matches
            WHERE status='SCHEDULED'
              AND date>?
            ORDER BY date
            """,
            (now(),),
        ).fetchall()

        for match in upcoming:
            # Refresh upcoming forecasts after each import, so newly finished
            # matches affect probabilities. Historical predictions remain frozen.
            c.execute("DELETE FROM predictions WHERE match_id=?", (match["id"],))
            # Include all stored earlier seasons, never the fixture or future games.
            # The model discounts older results instead of discarding them.
            history = c.execute(
                """SELECT * FROM matches
                   WHERE league=? AND status='FINISHED' AND date<?
                     AND home_goals IS NOT NULL AND away_goals IS NOT NULL
                   ORDER BY date, id""",
                (match["league"], match["date"]),
            ).fetchall()

            try:
                prediction = predict(
                    [
                        HistoricalMatch(row)
                        for row in history
                    ],
                    match["home_id"],
                    match["away_id"],
                    league=match["league"],
                )

            except ValueError:
                continue

            # Archive the latest genuine pregame forecast for later evaluation.
            # No forecasts are generated for started/finished games.
            c.execute(
                """
                INSERT INTO forecast_archive
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(match_id) DO UPDATE SET
                    created_at=excluded.created_at,
                    home_win=excluded.home_win,
                    draw=excluded.draw,
                    away_win=excluded.away_win,
                    expected_home=excluded.expected_home,
                    expected_away=excluded.expected_away,
                    details=excluded.details
                """,
                (
                    match["id"], now(), prediction["home_win"],
                    prediction["draw"], prediction["away_win"],
                    prediction["expected_home"], prediction["expected_away"],
                    json.dumps(prediction["details"]),
                ),
            )

            c.execute(
                """
                INSERT INTO predictions
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    match["id"],
                    now(),
                    prediction["home_win"],
                    prediction["draw"],
                    prediction["away_win"],
                    prediction["expected_home"],
                    prediction["expected_away"],
                    json.dumps(prediction["details"]),
                ),
            )

        finished = c.execute(
            """
            SELECT
                m.*,
                p.home_win,
                p.draw,
                p.away_win
            FROM matches m
            JOIN forecast_archive p
              ON p.match_id=m.id
            WHERE m.status='FINISHED'
              AND m.home_goals IS NOT NULL
              AND m.away_goals IS NOT NULL
              AND p.created_at < m.date
              AND NOT EXISTS (
                  SELECT 1
                  FROM prediction_results r
                  WHERE r.match_id=m.id
              )
            """
        ).fetchall()

        for match in finished:

            if match["home_goals"] > match["away_goals"]:
                actual = "1"
            elif match["home_goals"] == match["away_goals"]:
                actual = "X"
            else:
                actual = "2"

            probabilities = [
                match["home_win"] / 100,
                match["draw"] / 100,
                match["away_win"] / 100,
            ]

            brier = sum(
                (
                    probability
                    - (1 if outcome == actual else 0)
                ) ** 2
                for outcome, probability in zip(
                    ["1", "X", "2"],
                    probabilities,
                )
            )

            c.execute(
                """
                INSERT INTO prediction_results
                VALUES (?,?,?,?)
                """,
                (
                    match["id"],
                    actual,
                    brier,
                    now(),
                ),
            )


def sync(mode="weekly"):
    """Weekly schedule refresh; lightweight NHL results polling between refreshes.

    Historical matches remain in Neon and are never deleted.
    """
    if not sync_lock.acquire(blocking=False):
        log.info("Sync already running")
        return
    try:
        today = datetime.now(ZoneInfo("Europe/Stockholm")).date()
        if mode == "results":
            # NHL results only. The regular weekly job refreshes all league schedules.
            leagues = ("NHL",)
        else:
            leagues = tuple(LEAGUES)

        changed = False
        for league in leagues:
            try:
                if league == "NHL":
                    games = fetch_nhl(
                        start=today - timedelta(days=2),
                        end=today + timedelta(days=7 if mode == "weekly" else 1),
                    )
                else:
                    games = fetch_swedish(league)
                    # Keep only current/next week; historical rows already live in Neon.
                    # The source may return no schedule for a league: never delete old data.
                    lower = (today - timedelta(days=2)).isoformat()
                    upper = (today + timedelta(days=8)).isoformat()
                    games = [g for g in games if lower <= str(g["date"])[:10] < upper]
                if games:
                    changed = store_if_changed(league, games) or changed
            except Exception as exc:
                log.exception("Sync failed %s", league)
                error(league, exc)
        if changed:
            recompute()
            invalidate_match_response_cache()
    finally:
        sync_lock.release()


def store_if_changed(league, games):
    """Avoid writes and forecast recalculation if the imported rows are unchanged."""
    ids = [g["id"] for g in games]
    with db() as c:
        existing = {}
        # Bounded batches also work with PostgreSQL parameter limits.
        for start in range(0, len(ids), 200):
            batch = ids[start:start + 200]
            if not batch:
                continue
            placeholders = ",".join("?" for _ in batch)
            for row in c.execute(
                f"SELECT id,date,home_name,away_name,home_goals,away_goals,status "
                f"FROM matches WHERE id IN ({placeholders})", batch
            ).fetchall():
                existing[row["id"]] = row
    keys = ("date", "home_name", "away_name", "home_goals", "away_goals", "status")
    updates = [
        g for g in games
        if not (g["id"] in existing and existing[g["id"]]["status"] == "FINISHED"
                and g.get("status") != "FINISHED")
        and (g["id"] not in existing or
             any(g.get(k) != existing[g["id"]][k] for k in keys))
    ]
    if updates:
        store(league, updates)
        log.info("%s: %s changes out of %s matches", league, len(updates), len(games))
        return True
    return False


@asynccontextmanager
async def lifespan(app):
    init()

    # Runs at local Swedish midnight on Sundays, provided Render is awake.
    scheduler.add_job(
        sync, "cron", day_of_week="sun", hour=0, minute=0,
        kwargs={"mode": "weekly"}, id="weekly-schedule",
        max_instances=1, coalesce=True, replace_existing=True,
    )
    # Lightweight NHL result checks; does not reload an entire season.
    scheduler.add_job(
        sync, "interval", minutes=15, kwargs={"mode": "results"},
        id="nhl-results", max_instances=1, coalesce=True, replace_existing=True,
    )
    scheduler.add_job(refresh_shl_stats, "interval", minutes=30,
                      id="shl-stats", max_instances=1, replace_existing=True)
    scheduler.add_job(refresh_model_evaluation, "interval", hours=24,
                      id="model-evaluation", max_instances=1, replace_existing=True)
    scheduler.add_job(refresh_odds, "cron", hour="7,17", minute=10,
                      id="free-market-odds", max_instances=1, coalesce=True, replace_existing=True)
    scheduler.start()
    threading.Thread(target=refresh_shl_stats, name="initial-shl-stats", daemon=True).start()
    # Short initial refresh, not the full NHL season.
    threading.Thread(target=sync, kwargs={"mode": "weekly"},
                     name="initial-week-sync", daemon=True).start()

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Hockeyprognos",
    lifespan=lifespan,
)



# SHL team directory is fetched server-side to avoid browser CORS restrictions.
# No guessed image URL is generated: only URLs actually supplied by the API are used.
_shl_logo_cache = {"expires": 0.0, "result": None}

# Statistics are fetched independently of browser traffic and stored as last-known-good
# snapshots. On Render's free /tmp filesystem this is NOT durable across restarts.
from swehockey_stats import SOURCES, parse_standings, parse_scorers, parse_goalies, inspect_tables

_STATS_PARSERS = {"standings": parse_standings, "scorers": parse_scorers, "goalies": parse_goalies}
_stats_lock = threading.Lock()

def refresh_shl_stats():
    if not _stats_lock.acquire(blocking=False):
        return
    try:
        with httpx.Client(timeout=18.0, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 Hockeyprognos/3.0"}) as client:
            for category, url in SOURCES.items():
                status, error, items = None, None, []
                try:
                    response = client.get(url)
                    status = response.status_code
                    response.raise_for_status()
                    items = _STATS_PARSERS[category](response.text)
                    if not items:
                        diag = inspect_tables(response.text)
                        error = "Inga matchande tabellrader: " + json.dumps(diag, ensure_ascii=False)[:1000]
                except Exception as exc:
                    error = f"{type(exc).__name__}: {str(exc)[:250]}"
                with db() as c:
                    timestamp = now()
                    c.execute("""INSERT INTO stats_fetch_status VALUES (?,?,?,?,?)
                        ON CONFLICT(category) DO UPDATE SET attempted_at=excluded.attempted_at,
                        http_status=excluded.http_status, record_count=excluded.record_count,
                        error=excluded.error""", (category, timestamp, status, len(items), error))
                    if items:
                        c.execute("""INSERT INTO stats_snapshots VALUES (?,?,?,?)
                            ON CONFLICT(category) DO UPDATE SET fetched_at=excluded.fetched_at,
                            payload=excluded.payload, record_count=excluded.record_count""",
                            (category, timestamp, json.dumps(items, ensure_ascii=False), len(items)))
                if error:
                    log.warning("SHL stats %s: %s", category, error)
    finally:
        _stats_lock.release()

@app.get("/api/shl/statistics")
def swehockey_statistics():
    with db() as c:
        snapshots = {r['category']: dict(r) for r in c.execute("SELECT * FROM stats_snapshots")}
        statuses = {r['category']: dict(r) for r in c.execute("SELECT * FROM stats_fetch_status")}
    result = {"season": "2026/27", "source": SOURCES,
              "updated_at": max((v['fetched_at'] for v in snapshots.values()), default=None),
              "note": "Säsongsstatistik. Ingen målvakt är bekräftad som starter.",
              "status": statuses, "storage_persistent": USING_NEON or not str(DB).startswith('/tmp/')}
    for category in SOURCES:
        result[category] = json.loads(snapshots[category]['payload']) if category in snapshots else []
    return result

@app.post("/api/shl/statistics/refresh", include_in_schema=False)
def manual_refresh_disabled():
    raise HTTPException(status_code=403, detail="Automatisk uppdatering är aktiverad")

@app.get("/api/shl/goalkeepers")
async def shl_goalkeepers():
    from shl_goalkeepers import SOURCE, parse_goalkeepers
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            response = await client.get(SOURCE, headers={"User-Agent": "Hockeyprognos/2.2 (public stats)"})
            response.raise_for_status()
        rows = parse_goalkeepers(response.text)
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("SHL goalkeeper statistics unavailable: %s", exc)
        rows = []
    return {"source": SOURCE, "goalkeepers": rows, "confirmed_starters": False,
            "note": "Public season statistics only. No verified starters."}


@app.get("/api/shl/logos")
def shl_logos():
    import time
    from urllib.parse import urljoin, urlparse
    current = time.monotonic()
    if _shl_logo_cache["result"] is not None and current < _shl_logo_cache["expires"]:
        return _shl_logo_cache["result"]
    url = "https://www.shl.se/api/sports-v2/all-sites/qa98unlbd6"
    try:
        with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 Hockeyprognos/1.0", "Accept": "application/json"}) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = next((payload[k] for k in ("sites", "siteList", "teams", "teamList", "data") if isinstance(payload.get(k), list)), [])
        else:
            records = []
        teams = []
        for entry in records:
            if not isinstance(entry, dict):
                continue
            names = entry.get("names") if isinstance(entry.get("names"), dict) else {}
            name = entry.get("name") or entry.get("displayName") or names.get("long") or names.get("short") or ""
            image = next((entry.get(k) for k in ("icon", "logo", "logoUrl", "imageUrl", "publicUrl", "public_url") if isinstance(entry.get(k), str) and entry.get(k)), "")
            if isinstance(image, dict):
                image = image.get("url", "")
            if image and isinstance(image, str):
                image = urljoin("https://www.shl.se", image)
                if urlparse(image).scheme != "https":
                    image = ""
            teams.append({"name": str(name), "logo": image})
        result = {"teams": teams, "source": "SHL all-sites", "count": len(teams), "logos_found": sum(bool(t["logo"]) for t in teams)}
        _shl_logo_cache.update(expires=current + 3600, result=result)
        return result
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        log.warning("SHL logo directory unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="SHL:s lagregister kunde inte hämtas från servern")

@app.get("/api/leagues")
def leagues():
    with db() as c:
        states = {
            row["league"]: {
                "updated_at": row["updated_at"],
                "error": row["error"],
            }
            for row in c.execute(
                "SELECT * FROM sync_status"
            )
        }

    return [
        {
            "code": code,
            "name": name,
            **states.get(
                code,
                {
                    "error": "Data har ännu inte hämtats",
                    "updated_at": None,
                },
            ),
        }
        for code, name in LEAGUES.items()
    ]


def serialize(c, match, prediction=None, preloaded=False):
    if not preloaded:
        prediction = c.execute(
            "SELECT * FROM predictions WHERE match_id=?",
            (match["id"],),
        ).fetchone()

    if prediction is None:
        prediction_data = None

    else:
        prediction_data = {
            "home_win": prediction["home_win"],
            "draw": prediction["draw"],
            "away_win": prediction["away_win"],
            "expected_home": prediction["expected_home"],
            "expected_away": prediction["expected_away"],
            "details": json.loads(
                prediction["details"]
            ),
            "created_at": prediction["created_at"],
        }

    # For finished games, use only the archived pre-match prediction.
    # This avoids accidentally presenting a recalculated post-match forecast.
    if match["status"] == "FINISHED":
        archived = c.execute(
            "SELECT * FROM forecast_archive WHERE match_id=? AND created_at < ?",
            (match["id"], match["date"]),
        ).fetchone()
        prediction_data = ({
            "home_win": archived["home_win"], "draw": archived["draw"],
            "away_win": archived["away_win"],
            "expected_home": archived["expected_home"],
            "expected_away": archived["expected_away"],
            "details": json.loads(archived["details"]),
            "created_at": archived["created_at"],
        } if archived else None)

    effective_status = match["status"]
    if effective_status == "SCHEDULED":
        kickoff = datetime.fromisoformat(match["date"].replace("Z", "+00:00"))
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)
        if kickoff <= datetime.now(timezone.utc):
            effective_status = "PENDING"  # Not a verified final result yet.
    actual_outcome = None
    predicted_outcome = None
    if effective_status == "FINISHED" and match["home_goals"] is not None and match["away_goals"] is not None:
        actual_outcome = ("1" if match["home_goals"] > match["away_goals"] else
                          "2" if match["home_goals"] < match["away_goals"] else "X")
        if prediction_data:
            predicted_outcome = max(("1", "X", "2"), key=lambda k: {
                "1": prediction_data["home_win"], "X": prediction_data["draw"],
                "2": prediction_data["away_win"]}[k])
    return {
        "actual_outcome": actual_outcome,
        "predicted_outcome": predicted_outcome,
        "id": match["id"],
        "date": match["date"],
        "league": match["league"],
        "home": match["home_name"],
        "away": match["away_name"],
        "status": effective_status,
        "score": {
            "home": match["home_goals"],
            "away": match["away_goals"],
        },
        "prediction": prediction_data,
    }


@app.get("/api/matches")
def matches(
    day: date | None = None,
    league: str | None = None,
    days: int = Query(1, ge=1, le=14),
):
    if league and league not in LEAGUES:
        raise HTTPException(
            400,
            "Okänd liga",
        )

    day = day or datetime.now(ZoneInfo("Europe/Stockholm")).date()
    cache_key = (day.isoformat(), days, league)
    with _match_response_lock:
        cached = _match_response_cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

    # API dates refer to Swedish calendar days; database dates are UTC ISO.
    # Correctly handles NHL games played after midnight in Sweden and DST.
    sweden = ZoneInfo("Europe/Stockholm")
    start_utc = datetime.combine(day, datetime.min.time(), sweden).astimezone(timezone.utc).isoformat()
    end_utc = datetime.combine(day + timedelta(days=days), datetime.min.time(), sweden).astimezone(timezone.utc).isoformat()
    sql = """
        SELECT * FROM matches
        WHERE date>=?
          AND date<?
    """
    params = [start_utc, end_utc]

    if league:
        sql += " AND league=?"
        params.append(league)

    sql += " ORDER BY date"

    with db() as c:
        rows = c.execute(
            sql,
            params,
        ).fetchall()

        # One joined/batched prediction lookup instead of N database round trips.
        predictions_by_id = {}
        if rows:
            ids = [match["id"] for match in rows]
            placeholders = ",".join("?" for _ in ids)
            prediction_rows = c.execute(
                f"SELECT * FROM predictions WHERE match_id IN ({placeholders})", ids
            ).fetchall()
            predictions_by_id = {p["match_id"]: p for p in prediction_rows}
        result = [
            serialize(c, match, predictions_by_id.get(match["id"]), preloaded=True)
            for match in rows
        ]
    with _match_response_lock:
        _match_response_cache[cache_key] = (time.monotonic() + MATCH_RESPONSE_TTL, result)
        if len(_match_response_cache) > 100:
            expired = [k for k, v in _match_response_cache.items() if v[0] <= time.monotonic()]
            for k in expired:
                _match_response_cache.pop(k, None)
            if len(_match_response_cache) > 100:
                _match_response_cache.pop(next(iter(_match_response_cache)))
    return result


@app.get("/api/history")
def history(
    league: str = "NHL",
    team: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Finished regulation-time matches from the current season.

    This is match history, not retroactively manufactured predictions.
    """
    if league not in LEAGUES:
        raise HTTPException(400, "Okänd liga")
    season_start = date.today().year if date.today().month >= 9 else date.today().year - 1
    filters = ["league=?", "status='FINISHED'", "home_goals IS NOT NULL", "away_goals IS NOT NULL", "substr(date,1,10)>=?"]
    args = [league, f"{season_start}-" + ("09-01" if league == "SHL" else "10-01")]
    if team:
        filters.append("(home_id=? OR away_id=?)")
        args.extend([team, team])
    where = " AND ".join(filters)
    with db() as c:
        total = c.execute("SELECT COUNT(*) FROM matches WHERE " + where, args).fetchone()[0]
        rows = c.execute("SELECT * FROM matches WHERE " + where + " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        teams = c.execute("""SELECT team_id, MAX(team_name) AS team_name FROM (
            SELECT home_id AS team_id, home_name AS team_name FROM matches WHERE league=? AND status='FINISHED'
            UNION ALL
            SELECT away_id AS team_id, away_name AS team_name FROM matches WHERE league=? AND status='FINISHED'
        ) GROUP BY team_id ORDER BY team_name""", (league, league)).fetchall()
        return {
            "league": league,
            "season": f"{season_start}/{str(season_start+1)[-2:]}",
            "total": total,
            "limit": limit,
            "offset": offset,
            "teams": [{"id": r["team_id"], "name": r["team_name"]} for r in teams],
            "matches": [serialize(c, r) for r in rows],
        }


@app.get("/api/matches/{match_id:path}")
def detail(match_id: str):
    with db() as c:
        match = c.execute(
            """
            SELECT * FROM matches
            WHERE id=?
            """,
            (match_id,),
        ).fetchone()

        if not match:
            raise HTTPException(
                404,
                "Matchen finns inte",
            )

        return serialize(c, match)


@app.get("/api/performance")
def performance(league: str = "NHL"):
    if league not in LEAGUES:
        raise HTTPException(status_code=400, detail="Okänd liga")
    with db() as c:
        rows = c.execute(
            """
            SELECT m.id, m.date, m.home_name, m.away_name,
                   m.home_goals, m.away_goals,
                   a.created_at, a.home_win, a.draw, a.away_win,
                   r.actual, r.brier
            FROM prediction_results r
            JOIN matches m ON m.id=r.match_id
            JOIN forecast_archive a ON a.match_id=r.match_id
            WHERE m.league=? AND a.created_at < m.date
            ORDER BY m.date DESC
            """, (league,)
        ).fetchall()
        pending = c.execute(
            """SELECT COUNT(*) AS n FROM forecast_archive a
               JOIN matches m ON m.id=a.match_id
               WHERE m.league=? AND m.status!='FINISHED'""", (league,)
        ).fetchone()["n"]

    total = len(rows)
    correct = 0
    confidence_bins = {"0-39": [0, 0], "40-49": [0, 0],
                       "50-59": [0, 0], "60-69": [0, 0], "70-100": [0, 0]}
    games = []
    for row in rows:
        probs = {"1": row["home_win"], "X": row["draw"], "2": row["away_win"]}
        pick = max(probs, key=probs.get)
        hit = pick == row["actual"]
        correct += int(hit)
        confidence = probs[pick]
        key = ("0-39" if confidence < 40 else "40-49" if confidence < 50
               else "50-59" if confidence < 60 else "60-69" if confidence < 70
               else "70-100")
        confidence_bins[key][0] += 1
        confidence_bins[key][1] += int(hit)
        games.append({
            "id": row["id"], "date": row["date"],
            "home": row["home_name"], "away": row["away_name"],
            "score": {"home": row["home_goals"], "away": row["away_goals"]},
            "prediction": probs, "predicted_outcome": pick,
            "actual_outcome": row["actual"], "correct": hit,
            "brier": round(row["brier"], 4),
            "forecast_created_at": row["created_at"],
        })
    return {
        "league": league, "evaluated": total,
        "correct": correct,
        "accuracy_pct": round(100 * correct / total, 1) if total else None,
        "mean_brier": round(sum(r["brier"] for r in rows) / total, 4) if total else None,
        "pending_forecasts": pending,
        "calibration": [
            {"range": k, "games": n, "hits": hits,
             "hit_rate_pct": round(100 * hits / n, 1) if n else None}
            for k, (n, hits) in confidence_bins.items()
        ],
        "recent": games[:20],
        "storage_warning": "Prognoshistoriken kan försvinna vid omstart eftersom DB_PATH använder temporär lagring." if str(DB).startswith('/tmp/') and not USING_NEON else None,
        "method": "1X2 efter 60 minuter. Favoritträff och Brier (lägre är bättre). Endast arkiverade prognoser före matchstart räknas.",
    }



@app.get("/api/backtest")
def backtest(league: str = "SHL", limit: int = Query(default=120, ge=20, le=300)):
    """Walk-forward comparison, strictly using earlier games across available seasons.

    Does NOT change live predictions. No archived forecasts are rewritten.
    This is a retrospective model test, not a record of real pregame picks.
    """
    if league not in LEAGUES:
        raise HTTPException(status_code=400, detail="Okänd liga")
    with db() as c:
        rows = c.execute("""
            SELECT * FROM matches
            WHERE league=? AND status='FINISHED'
              AND home_goals IS NOT NULL AND away_goals IS NOT NULL
            ORDER BY date, id
        """, (league,)).fetchall()

    def season_key(iso):
        d = datetime.fromisoformat(iso.replace('Z', '+00:00'))
        return d.year if d.month >= (9 if league == 'SHL' else 10) else d.year - 1

    # Walk forward across ALL available seasons. Never let matches starting
    # at the same instant influence each other's retrospective predictions.
    eligible = []
    for i, row in enumerate(rows):
        prior = [r for r in rows[:i] if r['date'] < row['date']]
        if len(prior) >= 20:
            eligible.append((row, prior))
    eligible = eligible[-limit:]
    results = {name: {"evaluated": 0, "correct": 0, "brier_sum": 0.0, "log_loss_sum": 0.0}
               for name in (('current', 'experimental', 'h2h') if league == 'SHL' else ('current', 'experimental'))}
    import math
    for match, prior in eligible:
        history = [HistoricalMatch(r) for r in prior]
        actual = ('1' if match['home_goals'] > match['away_goals']
                  else '2' if match['home_goals'] < match['away_goals'] else 'X')
        for name, stats in results.items():
            try:
                p = predict(history, match['home_id'], match['away_id'], league=league, variant=name)
            except ValueError:
                continue
            probs = {'1': p['home_win'] / 100, 'X': p['draw'] / 100, '2': p['away_win'] / 100}
            stats['evaluated'] += 1
            stats['correct'] += int(max(probs, key=probs.get) == actual)
            stats['brier_sum'] += sum((probs[k] - int(k == actual)) ** 2 for k in ('1', 'X', '2'))
            stats['log_loss_sum'] += -math.log(max(1e-12, probs[actual]))
    summary = {}
    for name, stats in results.items():
        n = stats['evaluated']
        summary[name] = {
            'evaluated': n,
            'accuracy_pct': round(100 * stats['correct'] / n, 2) if n else None,
            'mean_brier': round(stats['brier_sum'] / n, 5) if n else None,
            'mean_log_loss': round(stats['log_loss_sum'] / n, 5) if n else None,
        }
    return {
        'league': league, 'available_finished': len(rows),
        'eligible_sample': len(eligible), 'requested_limit': limit,
        'models': summary, 'live_model': 'current',
        'method': 'Walk-forward: bara matcher före nedsläpp, även från tidigare säsonger; 1X2 efter 60 minuter. Lägre Brier/log loss är bättre. Experimentet är inte aktiverat för liveprognoser.',
        'warning': 'Testet förutsätter att importerade resultat verkligen avser 60 minuter. En enda säsong eller få matcher ger osäkra slutsatser.'
    }

def refresh_odds():
    """Fetch only on schedule, never on page views or cold starts."""
    if not os.getenv('ODDS_API_KEY'):
        return
    for league in LEAGUES:
        try:
            with db() as c:
                odds.fetch_league(c, league)
        except Exception:
            log.exception('Odds refresh failed for %s', league)


@app.get('/api/odds/status')
def odds_status():
    with db() as c:
        odds.setup(c)
        quota=c.execute('SELECT * FROM odds_quota WHERE month=?',(odds.month_now(),)).fetchone()
        syncs=c.execute('SELECT * FROM odds_sync').fetchall()
    return {'configured':bool(os.getenv('ODDS_API_KEY')),
            'used':quota['used'] if quota else 0,
            'remaining':quota['remaining'] if quota else None,
            'monthly_local_cap':400,
            'leagues':{r['league']:{'attempted_at':r['attempted_at'],'saved':r['saved'],'error':r['error']} for r in syncs}}


@app.get('/api/odds/match/{match_id:path}')
def match_odds(match_id: str):
    with db() as c:
        match=c.execute('SELECT * FROM matches WHERE id=?',(match_id,)).fetchone()
        if not match:
            raise HTTPException(status_code=404,detail='Matchen finns inte')
        result=odds.for_match(c,match['league'],match['home_name'],match['away_name'],match['date'])
    return {'match_id':match_id,'market':result,
            'note':'Endast verifierade 1X2-marknader med oavgjort. Marknadsdata är separat från AI-prognosen.'}


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/storage/status")
def storage_status():
    try:
        with db() as c:
            count = c.execute("SELECT COUNT(*) AS total FROM matches").fetchone()["total"]
            snapshot_count = c.execute("SELECT COUNT(*) AS total FROM stats_snapshots").fetchone()["total"]
        return {"status": "ok", "engine": "neon-postgresql" if USING_NEON else "sqlite",
                "persistent": USING_NEON or not str(DB).startswith("/tmp/"),
                "matches": count, "stat_snapshots": snapshot_count}
    except Exception:
        log.exception("Database status check failed")
        raise HTTPException(status_code=503, detail="Database connection failed; see Render logs")


app.mount(
    "/",
    StaticFiles(
        directory=str(ROOT / "web"),
        html=True,
    ),
    name="web",
)
# Cached daily walk-forward evaluation, kept separate from live predictions.
def refresh_model_evaluation():
    try:
        report = backtest(league="SHL", limit=120)
        with db() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS model_evaluations
                (league TEXT PRIMARY KEY, updated_at TEXT NOT NULL, payload TEXT NOT NULL)""")
            c.execute("""INSERT INTO model_evaluations VALUES (?,?,?)
                ON CONFLICT(league) DO UPDATE SET updated_at=excluded.updated_at, payload=excluded.payload""",
                ("SHL", now(), json.dumps(report, ensure_ascii=False)))
    except Exception:
        log.exception("Daily model evaluation failed")

@app.get("/api/model-evaluation/latest")
def latest_model_evaluation():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS model_evaluations
            (league TEXT PRIMARY KEY, updated_at TEXT NOT NULL, payload TEXT NOT NULL)""")
        row = c.execute("SELECT * FROM model_evaluations WHERE league='SHL'").fetchone()
    return {"updated_at": row['updated_at'] if row else None,
            "report": json.loads(row['payload']) if row else None,
            "note": "Testmodell; liveprognoserna är oförändrade."}
