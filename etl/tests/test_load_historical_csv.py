"""
Verifies etl/load_historical_csv.py's "Done when" criteria from PLAN.md
against whatever database DATABASE_URL currently points at:
  - expected row counts (380 matches/season x 10 seasons)
  - zero NULLs in required columns for historical_csv rows
  - re-running the loader is idempotent (0 newly inserted the second time)

Assumes the loader has already been run at least once — this test doesn't
run it itself, since a full 3,800-row network-bound load is slow enough
that it shouldn't happen on every test invocation.
"""

import os
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest
from dotenv import load_dotenv

load_dotenv()

EXPECTED_SEASONS = [
    "2010-2011", "2011-2012", "2012-2013", "2013-2014", "2014-2015",
    "2015-2016", "2016-2017", "2017-2018", "2018-2019", "2019-2020",
]


@pytest.fixture(scope="module")
def conn():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")
    connection = psycopg2.connect(database_url)
    yield connection
    connection.close()


def test_total_row_count(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM matches WHERE source = 'historical_csv';"
        )
        assert cur.fetchone()[0] == 380 * len(EXPECTED_SEASONS)


def test_each_season_has_380_matches(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT season, count(*)
            FROM matches
            WHERE source = 'historical_csv'
            GROUP BY season;
            """
        )
        counts = dict(cur.fetchall())
    assert set(counts) == set(EXPECTED_SEASONS)
    assert all(count == 380 for count in counts.values())


def test_no_nulls_in_required_columns(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM matches
            WHERE source = 'historical_csv'
              AND (home_goals IS NULL OR away_goals IS NULL
                   OR home_shots IS NULL OR away_shots IS NULL
                   OR home_shots_on_target IS NULL OR away_shots_on_target IS NULL
                   OR home_corners IS NULL OR away_corners IS NULL
                   OR home_fouls IS NULL OR away_fouls IS NULL
                   OR home_yellow IS NULL OR away_yellow IS NULL
                   OR home_red IS NULL OR away_red IS NULL);
            """
        )
        assert cur.fetchone()[0] == 0


def test_result_matches_scoreline(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM matches
            WHERE source = 'historical_csv' AND (
                (result = 'H' AND home_goals <= away_goals) OR
                (result = 'A' AND home_goals >= away_goals) OR
                (result = 'D' AND home_goals != away_goals)
            );
            """
        )
        assert cur.fetchone()[0] == 0


def test_rerunning_loader_is_idempotent(conn):
    script = Path(__file__).parent.parent / "load_historical_csv.py"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM matches WHERE source = 'historical_csv';"
        )
        before = cur.fetchone()[0]

    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=600
    )
    assert result.returncode == 0, result.stderr

    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM matches WHERE source = 'historical_csv';"
        )
        after = cur.fetchone()[0]

    assert after == before
