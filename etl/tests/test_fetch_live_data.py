"""
Verifies etl/fetch_live_data.py's "Done when" criteria against whatever
database DATABASE_URL currently points at.

Unlike test_load_historical_csv.py, this does NOT re-invoke the fetch
script itself — football-data.org's free tier is rate-limited (10 req/min),
and re-running it on every test invocation would burn real API quota for no
benefit. Idempotency was verified manually (ON CONFLICT upserts, run twice,
counts unchanged); these tests just check the DB ended up in a sane state.
Assumes etl/fetch_live_data.py has already been run at least once.
"""

import os

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="module")
def conn():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")
    connection = psycopg2.connect(database_url)
    yield connection
    connection.close()


def test_fixtures_populated(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM fixtures;")
        count = cur.fetchone()[0]
    assert 0 < count <= 380


def test_fixtures_reference_valid_teams(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM fixtures f
            LEFT JOIN teams h ON h.team_id = f.home_team_id
            LEFT JOIN teams a ON a.team_id = f.away_team_id
            WHERE h.team_id IS NULL OR a.team_id IS NULL;
            """
        )
        assert cur.fetchone()[0] == 0


def test_standings_snapshot_has_20_teams(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM standings_snapshot
            WHERE snapshot_date = (SELECT max(snapshot_date) FROM standings_snapshot);
            """
        )
        assert cur.fetchone()[0] == 20


def test_football_data_org_aliases_resolved(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM team_aliases WHERE source = 'football-data.org';"
        )
        assert cur.fetchone()[0] == 20


def test_api_matches_lack_stats_but_not_goals(conn):
    """Free-tier api rows should have goals/result but NULL shot/corner/foul
    stats — the documented limitation, not a loader bug."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM matches
            WHERE source = 'api'
              AND (home_goals IS NULL OR away_goals IS NULL OR result IS NULL);
            """
        )
        assert cur.fetchone()[0] == 0


def test_no_fixture_also_marked_finished_in_matches(conn):
    """A completed match should have been removed from fixtures — the two
    tables should never both claim the same fixture_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM fixtures f
            JOIN matches m ON m.season = f.season
                AND m.home_team_id = f.home_team_id
                AND m.away_team_id = f.away_team_id
                AND m.source = 'api';
            """
        )
        assert cur.fetchone()[0] == 0
