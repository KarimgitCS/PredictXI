"""GET /standings — current Premier League table."""

import psycopg2.extras
from fastapi import APIRouter, Depends

from api.db import get_db
from api.schemas import StandingOut

router = APIRouter()


@router.get("/standings", response_model=list[StandingOut])
def list_standings(conn=Depends(get_db)):
    """The most recent snapshot only (etl/fetch_live_data.py inserts a new
    dated row each time it runs, so history accumulates in the table even
    though this endpoint always serves the latest one)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT t.name AS team, t.crest_url,
                   s.position, s.played, s.points, s.wins, s.draws, s.losses, s.goal_diff
            FROM standings_snapshot s
            JOIN teams t ON t.team_id = s.team_id
            WHERE s.snapshot_date = (SELECT max(snapshot_date) FROM standings_snapshot)
            ORDER BY s.position, t.name;
            """
        )
        return cur.fetchall()
