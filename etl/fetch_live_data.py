"""
Pulls current-season Premier League data from football-data.org (free tier)
and upserts it into fixtures, matches (source='api'), and standings_snapshot.

Usage:
    python etl/fetch_live_data.py

Safe to re-run: fixtures are upserted on fixture_id, completed matches are
upserted on the same (season, match_date, home_team_id, away_team_id) key
historical loads use, and standings_snapshot is upserted on
(snapshot_date, team_id).

Free tier gives scores/fixtures/schedules/tables but not shots/corners/
fouls/cards — matches inserted here (source='api') will have those stat
columns as NULL, which is expected (see PLAN.md's "free-tier stat gap" note),
not a bug.
"""

import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from team_aliases import resolve_team_id

BASE_URL = "https://api.football-data.org/v4"
COMPETITION = "PL"
ALIAS_SOURCE = "football-data.org"
MATCH_SOURCE = "api"

# Free tier: 10 requests/minute. This script only ever makes a handful of
# calls per run, but this makes it safe even if that grows later.
MIN_SECONDS_BETWEEN_REQUESTS = 6.5
_last_request_at: float | None = None


def _get(session: requests.Session, path: str, params: dict | None = None) -> dict:
    global _last_request_at
    if _last_request_at is not None:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)

    response = session.get(f"{BASE_URL}{path}", params=params, timeout=30)
    _last_request_at = time.monotonic()
    response.raise_for_status()
    return response.json()


def season_label(season: dict) -> str:
    return f"{season['startDate'][:4]}-{season['endDate'][:4]}"


def _caching_resolver():
    """resolve_team_id costs several round trips to the hosted database per
    call, and the same ~20 teams show up in hundreds of fixtures — so each
    refresh looks each team up once and reuses it."""
    cache: dict[str, int] = {}

    def resolve(cur, team: dict) -> int:
        name = team["name"]
        if name not in cache:
            cache[name] = resolve_team_id(cur, ALIAS_SOURCE, name, team.get("crest"))
        return cache[name]

    return resolve


def upsert_standings(cur, standings_payload: dict, resolve) -> int:
    snapshot_date = date.today()
    season = season_label(standings_payload["season"])
    table = standings_payload["standings"][0]["table"]  # "TOTAL" standings

    for row in table:
        team_id = resolve(cur, row["team"])
        cur.execute(
            """
            INSERT INTO standings_snapshot
                (snapshot_date, season, team_id, position, played, points,
                 goal_diff, wins, draws, losses)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_date, team_id) DO UPDATE SET
                season = EXCLUDED.season,
                position = EXCLUDED.position,
                played = EXCLUDED.played,
                points = EXCLUDED.points,
                goal_diff = EXCLUDED.goal_diff,
                wins = EXCLUDED.wins,
                draws = EXCLUDED.draws,
                losses = EXCLUDED.losses;
            """,
            (snapshot_date, season, team_id, row["position"], row["playedGames"],
             row["points"], row["goalDifference"], row["won"], row["draw"], row["lost"]),
        )
    return len(table)


def upsert_fixtures(cur, matches: list[dict], resolve) -> int:
    rows = [
        (
            match["id"], season_label(match["season"]), match["matchday"],
            datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00")),
            resolve(cur, match["homeTeam"]), resolve(cur, match["awayTeam"]), match["status"],
        )
        for match in matches
    ]
    # One batched statement instead of a round trip per fixture.
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO fixtures
            (fixture_id, season, matchday, kickoff_at, home_team_id, away_team_id, status)
        VALUES %s
        ON CONFLICT (fixture_id) DO UPDATE SET
            matchday = EXCLUDED.matchday,
            kickoff_at = EXCLUDED.kickoff_at,
            status = EXCLUDED.status;
        """,
        rows,
    )
    return len(rows)


def backfill_finished_matches(cur, matches: list[dict], resolve) -> int:
    rows = []
    for match in matches:
        match_date = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00")).date()
        full_time = match["score"]["fullTime"]
        rows.append((
            season_label(match["season"]), match_date,
            resolve(cur, match["homeTeam"]), resolve(cur, match["awayTeam"]),
            full_time["home"], full_time["away"], MATCH_SOURCE,
        ))

    inserted = psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO matches
            (season, match_date, home_team_id, away_team_id,
             home_goals, away_goals, source)
        VALUES %s
        ON CONFLICT (season, match_date, home_team_id, away_team_id) DO NOTHING
        RETURNING match_id;
        """,
        rows,
        fetch=True,
    )

    # A finished match is no longer "upcoming" — drop it from fixtures so
    # that table always reflects only not-yet-played matches.
    cur.execute("DELETE FROM fixtures WHERE fixture_id = ANY(%s);", ([m["id"] for m in matches],))

    return len(inserted)


def refresh(database_url: str, api_key: str) -> dict:
    """One full pull: standings, upcoming fixtures, and newly finished
    matches. Importable so the API can call it on a timer (see
    api/main.py) — the CLI below is just a thin wrapper around this."""
    session = requests.Session()
    session.headers["X-Auth-Token"] = api_key

    standings_payload = _get(session, f"/competitions/{COMPETITION}/standings")
    scheduled_payload = _get(session, f"/competitions/{COMPETITION}/matches",
                              params={"status": "SCHEDULED"})
    finished_payload = _get(session, f"/competitions/{COMPETITION}/matches",
                             params={"status": "FINISHED"})

    conn = psycopg2.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                resolve = _caching_resolver()
                standings_count = upsert_standings(cur, standings_payload, resolve)
                fixtures_count = upsert_fixtures(cur, scheduled_payload["matches"], resolve)
                inserted_count = backfill_finished_matches(cur, finished_payload["matches"], resolve)
    finally:
        conn.close()

    return {
        "standings": standings_count,
        "fixtures": fixtures_count,
        "finished_seen": len(finished_payload["matches"]),
        "finished_inserted": inserted_count,
    }


def main() -> None:
    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    api_key = os.environ.get("FOOTBALL_DATA_ORG_API_KEY")
    if not database_url:
        sys.exit("DATABASE_URL is not set — check your .env file.")
    if not api_key:
        sys.exit("FOOTBALL_DATA_ORG_API_KEY is not set — check your .env file.")

    counts = refresh(database_url, api_key)

    print(f"standings_snapshot: {counts['standings']} teams")
    print(f"fixtures: {counts['fixtures']} upcoming matches upserted")
    print(f"matches: {counts['finished_seen']} finished matches seen, "
          f"{counts['finished_inserted']} newly inserted")


if __name__ == "__main__":
    main()
