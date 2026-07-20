"""GET /matches — list upcoming fixtures."""

import psycopg2.extras
from fastapi import APIRouter, Depends, Query

from api.db import get_db
from api.schemas import FixtureOut

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
                   ht.name AS home_team, at.name AS away_team, f.status
            FROM fixtures f
            JOIN teams ht ON ht.team_id = f.home_team_id
            JOIN teams at ON at.team_id = f.away_team_id
            ORDER BY f.kickoff_at
            LIMIT %s;
            """,
            (limit,),
        )
        return cur.fetchall()
