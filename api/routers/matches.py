"""GET /matches — list upcoming fixtures. GET /result — check whether a
specific match has been played yet, and if so, what happened."""

import psycopg2.extras
from fastapi import APIRouter, Depends, Query

from api.db import get_db
from api.schemas import FixtureOut, MatchResultOut, ResultOut

router = APIRouter()


@router.get("/matches", response_model=list[FixtureOut])
def list_matches(limit: int = Query(default=10, ge=1, le=100), conn=Depends(get_db)):
    """Defaults to the next 10 fixtures, not all of them — the frontend
    calls /predict once per fixture shown, and every /predict call both
    hits the database and logs a row in `predictions`; fetching all ~380
    preseason fixtures on every page load would be wasteful and would
    spam that table for no benefit."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT f.fixture_id, f.season, f.matchday, f.kickoff_at,
                   ht.name AS home_team, at.name AS away_team,
                   ht.crest_url AS home_crest_url, at.crest_url AS away_crest_url,
                   f.status
            FROM fixtures f
            JOIN teams ht ON ht.team_id = f.home_team_id
            JOIN teams at ON at.team_id = f.away_team_id
            ORDER BY f.kickoff_at
            LIMIT %s;
            """,
            (limit,),
        )
        return cur.fetchall()


@router.get("/result", response_model=ResultOut)
def get_result(season: str, home_team: str, away_team: str, conn=Depends(get_db)):
    """Looks up a completed match by (season, home team, away team) — not by
    fixture_id, since football-data.org's fixture id isn't stored once a
    fixture is played and moved into `matches` (see etl/fetch_live_data.py).
    A given ordered (home, away) pair is unique within a season in a
    standard round-robin, so this is a reliable lookup key. Returns
    played=false (not a 404) if the match hasn't happened yet — that's an
    expected, common case for a saved prediction, not an error."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT m.result, m.home_goals, m.away_goals
            FROM matches m
            JOIN teams ht ON ht.team_id = m.home_team_id
            JOIN teams at ON at.team_id = m.away_team_id
            WHERE m.season = %s AND ht.name = %s AND at.name = %s;
            """,
            (season, home_team, away_team),
        )
        row = cur.fetchone()

    if row is None:
        return ResultOut(played=False, result=None, home_goals=None, away_goals=None)
    return ResultOut(played=True, result=row["result"], home_goals=row["home_goals"], away_goals=row["away_goals"])


@router.get("/results", response_model=list[MatchResultOut])
def list_results(season: str, conn=Depends(get_db)):
    """Every played match in a season, in one call. The saved-predictions
    page matches its picks against this locally instead of calling /result
    once per pick — a season of picks would otherwise be up to 380
    concurrent requests against a 20-connection pool."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT ht.name AS home_team, at.name AS away_team,
                   m.result, m.home_goals, m.away_goals
            FROM matches m
            JOIN teams ht ON ht.team_id = m.home_team_id
            JOIN teams at ON at.team_id = m.away_team_id
            WHERE m.season = %s AND m.result IS NOT NULL;
            """,
            (season,),
        )
        return cur.fetchall()
