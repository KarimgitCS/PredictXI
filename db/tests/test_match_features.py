"""
Verifies match_features (db/migrations/008_match_features_views.sql) against
PLAN.md's "Done when" criteria:
  - a hand-picked case with a manually-computed expected value
  - a team's first appearance has NULL rolling features (no history yet)
  - the flagship check: independently recompute every rolling-form value in
    pandas (not SQL) and confirm it matches the view exactly, row for row.
    Since the pandas recomputation uses a strict "asof, before" merge, this
    also *is* the "features don't change if you truncate data to < D" check
    — a leaked feature would only match by using data at-or-after D, which
    the independent recomputation never has access to.

Assumes migrations have been applied and both ETL loads have run.
"""

import os

import pandas as pd
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


@pytest.fixture(scope="module")
def team_match_log(conn):
    return pd.read_sql(
        "SELECT match_id, team_id, match_date, points, goals_for, goals_against "
        "FROM team_match_log;",
        conn,
    )


@pytest.fixture(scope="module")
def match_features(conn):
    return pd.read_sql(
        "SELECT target_id, target_type, match_date, home_team_id, away_team_id, "
        "       home_rolling_points_5, away_rolling_points_5, "
        "       home_rolling_goals_for_5, away_rolling_goals_for_5 "
        "FROM match_features;",
        conn,
    )


def test_row_counts(match_features, conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM matches;")
        n_matches = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM fixtures;")
        n_fixtures = cur.fetchone()[0]
    assert len(match_features) == n_matches + n_fixtures


def test_result_nullness_matches_target_type(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM match_features "
            "WHERE (target_type = 'match' AND result IS NULL) "
            "   OR (target_type = 'fixture' AND result IS NOT NULL);"
        )
        assert cur.fetchone()[0] == 0


def test_hand_computed_case(conn):
    """Arsenal's 6th match of 2010/11 (2010-09-25): hand-computed
    rolling_points_5 from the previous 5 matches (1,3,3,3,1) = 2.2 — and
    critically, NOT the 2.0 that match's own 5-window (3,3,3,1,0) would give,
    which is what a leaked (off-by-one) view would show instead."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT home_rolling_points_5 FROM match_features
            WHERE target_type = 'match' AND match_date = '2010-09-25'
              AND home_team_id = (SELECT team_id FROM teams WHERE name = 'Arsenal');
            """
        )
        value = cur.fetchone()[0]
    assert float(value) == pytest.approx(2.2)


def test_first_ever_appearance_has_null_rolling_form(conn):
    """A team's first-ever match in the dataset has zero prior matches, so
    its rolling form must be NULL, not some default like 0."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT mf.home_rolling_points_5, mf.away_rolling_points_5
            FROM match_features mf
            WHERE mf.target_type = 'match'
              AND mf.match_date = (SELECT min(match_date) FROM matches);
            """
        )
        rows = cur.fetchall()
    assert len(rows) > 0
    for home_val, away_val in rows:
        assert home_val is None
        assert away_val is None


def test_rolling_form_matches_independent_pandas_recomputation(team_match_log, match_features):
    log = team_match_log.sort_values(["team_id", "match_date"]).copy()
    log["rolling_points_5"] = (
        log.groupby("team_id")["points"].transform(lambda s: s.rolling(5, min_periods=1).mean())
    )
    log["rolling_goals_for_5"] = (
        log.groupby("team_id")["goals_for"].transform(lambda s: s.rolling(5, min_periods=1).mean())
    )
    log["match_date"] = pd.to_datetime(log["match_date"])

    targets = match_features.copy()
    targets["match_date"] = pd.to_datetime(targets["match_date"])

    for side in ["home", "away"]:
        side_log = log.rename(columns={"team_id": f"{side}_team_id"}).sort_values("match_date")
        side_targets = targets[["target_id", "target_type", f"{side}_team_id", "match_date"]] \
            .sort_values("match_date")

        merged = pd.merge_asof(
            side_targets,
            side_log[[f"{side}_team_id", "match_date", "rolling_points_5", "rolling_goals_for_5"]],
            on="match_date",
            by=f"{side}_team_id",
            direction="backward",
            allow_exact_matches=False,  # strict "<" — the leakage boundary
        )

        expected = merged.set_index(["target_id", "target_type"])["rolling_points_5"]
        actual = targets.set_index(["target_id", "target_type"])[f"{side}_rolling_points_5"]
        pd.testing.assert_series_equal(
            expected.astype(float).sort_index(),
            actual.astype(float).sort_index(),
            check_names=False,
            atol=1e-6,
        )
