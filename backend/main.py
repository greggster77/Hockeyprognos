
import os
import json
import logging
import sqlite3
import threading

from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from contextlib import asynccontextmanager

import httpx

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler

from model import predict


ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.getenv("DB_PATH", str(ROOT / "hockey.db")))

LEAGUES = {
    "SHL": "SHL",
    "HA": "HockeyAllsvenskan",
    "NHL": "NHL",
}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")
sync_lock = threading.Lock()


def db():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


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

        CREATE TABLE IF NOT EXISTS prediction_results (
            match_id TEXT PRIMARY KEY,
            actual TEXT NOT NULL,
            brier REAL NOT NULL,
            evaluated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_status (
            league TEXT PRIMARY KEY,
            updated_at TEXT,
            error TEXT
        );
        """)


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


def fetch_nhl():
    """
    Fetch NHL schedule and completed games.
    Use only official NHL API data.
    """

    start = date.today() - timedelta(days=35)
    end = date.today() + timedelta(days=21)

    games = {}

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
    url = os.getenv(f"{league}_FEED_URL")

    if not url:
        raise ValueError(
            "Ingen datakälla är konfigurerad för "
            + LEAGUES[league]
        )

    headers = {}

    token = os.getenv(f"{league}_FEED_TOKEN")

    if token:
        headers["Authorization"] = "Bearer " + token

    with httpx.Client(timeout=25) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        items = response.json()

    if not isinstance(items, list):
        raise ValueError(
            "Datakällan måste returnera en JSON-lista"
        )

    output = []

    for item in items:
        required = (
            "id",
            "date",
            "home_id",
            "away_id",
            "home_name",
            "away_name",
            "status",
        )

        for key in required:
            if key not in item:
                raise ValueError("Saknat fält: " + key)

        if item["status"] == "FINISHED":
            if (
                item.get("home_goals") is None
                or item.get("away_goals") is None
            ):
                raise ValueError(
                    "Resultat efter 60 minuter saknas"
                )

        output.append({
            **item,
            "id": league + ":" + str(item["id"]),
            "home_id": (
                league + ":" + str(item["home_id"])
            ),
            "away_id": (
                league + ":" + str(item["away_id"])
            ),
        })

    return output


class HistoricalMatch:
    def __init__(self, row):
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
            existing = c.execute(
                """
                SELECT 1 FROM predictions
                WHERE match_id=?
                """,
                (match["id"],),
            ).fetchone()

            if existing:
                continue

            history = c.execute(
                """
                SELECT * FROM matches
                WHERE league=?
                  AND status='FINISHED'
                  AND date<?
                ORDER BY date
                """,
                (
                    match["league"],
                    match["date"],
                ),
            ).fetchall()

            try:
                prediction = predict(
                    [
                        HistoricalMatch(row)
                        for row in history
                    ],
                    match["home_id"],
                    match["away_id"],
                )

            except ValueError:
                continue

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
            JOIN predictions p
              ON p.match_id=m.id
            WHERE m.status='FINISHED'
              AND m.home_goals IS NOT NULL
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


def sync():
    if not sync_lock.acquire(blocking=False):
        log.info("Sync already running")
        return

    try:
        for league in LEAGUES:
            try:
                games = (
                    fetch_nhl()
                    if league == "NHL"
                    else fetch_swedish(league)
                )

                store(league, games)

            except Exception as exc:
                log.exception(
                    "Sync failed %s",
                    league,
                )

                error(league, exc)

        recompute()

    finally:
        sync_lock.release()


@asynccontextmanager
async def lifespan(app):
    init()

    scheduler.add_job(
        sync,
        "interval",
        hours=3,
        id="sync",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.start()

    threading.Thread(
        target=sync,
        name="initial-hockey-sync",
        daemon=True,
    ).start()

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Hockeyprognos",
    lifespan=lifespan,
)


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


def serialize(c, match):
    prediction = c.execute(
        """
        SELECT * FROM predictions
        WHERE match_id=?
        """,
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

    return {
        "id": match["id"],
        "date": match["date"],
        "league": match["league"],
        "home": match["home_name"],
        "away": match["away_name"],
        "status": match["status"],
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

    day = day or date.today()

    end = (
        day + timedelta(days=days)
    ).isoformat()

    sql = """
        SELECT * FROM matches
        WHERE substr(date,1,10)>=?
          AND substr(date,1,10)<?
    """

    params = [
        day.isoformat(),
        end,
    ]

    if league:
        sql += " AND league=?"
        params.append(league)

    sql += " ORDER BY date"

    with db() as c:
        rows = c.execute(
            sql,
            params,
        ).fetchall()

        return [
            serialize(c, match)
            for match in rows
        ]


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
def performance():
    with db() as c:
        result = c.execute(
            """
            SELECT
                COUNT(*) n,
                AVG(brier) b
            FROM prediction_results
            """
        ).fetchone()

        return {
            "evaluated": result["n"],
            "mean_brier": result["b"],
        }


@app.get("/health")
def health():
    return {"status": "ok"}


app.mount(
    "/",
    StaticFiles(
        directory=str(ROOT / "web"),
        html=True,
    ),
    name="web",
)