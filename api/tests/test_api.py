"""
FastAPI TestClient suite. Runs against the real hosted database (not a
disposable test schema — this project uses a single hosted free-tier
instance for everything, dev included, matching every other test suite's
approach in this repo; see PLAN.md). Any prediction row this suite inserts
is deleted afterward so repeated test runs don't clutter real data.
"""

import concurrent.futures
import os
import time

import psycopg2
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from api.main import app

load_dotenv()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # triggers the lifespan (pool + model load)
        yield c


@pytest.fixture(scope="module")
def db_conn():
    connection = psycopg2.connect(os.environ["DATABASE_URL"])
    yield connection
    connection.close()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_matches_returns_upcoming_fixtures(client):
    response = client.get("/matches")
    assert response.status_code == 200
    fixtures = response.json()
    assert len(fixtures) > 0
    assert {"fixture_id", "home_team", "away_team", "kickoff_at"} <= fixtures[0].keys()


def test_matches_default_limit_is_10(client):
    response = client.get("/matches")
    assert len(response.json()) == 10


def test_matches_respects_limit_param(client):
    response = client.get("/matches", params={"limit": 3})
    assert len(response.json()) == 3


def test_calibration_returns_both_models(client):
    response = client.get("/calibration")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"logreg", "xgboost"}
    assert set(body["logreg"].keys()) == {"H", "D", "A"}


def test_predict_unknown_fixture_returns_404(client):
    response = client.get("/predict", params={"fixture_id": 999999999})
    assert response.status_code == 404


def test_predict_returns_calibrated_probabilities_and_logs_prediction(client, db_conn):
    fixtures = client.get("/matches").json()
    fixture_id = fixtures[0]["fixture_id"]

    response = client.get("/predict", params={"fixture_id": fixture_id})
    assert response.status_code == 200
    body = response.json()

    assert body["fixture_id"] == fixture_id
    assert body["predicted_outcome"] in ("H", "D", "A")
    total = body["prob_home"] + body["prob_draw"] + body["prob_away"]
    assert total == pytest.approx(1.0, abs=0.01)
    assert isinstance(body["predicted_home_goals"], int)
    assert isinstance(body["predicted_away_goals"], int)
    assert body["predicted_home_goals"] >= 0
    assert body["predicted_away_goals"] >= 0

    try:
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM predictions WHERE fixture_id = %s;", (fixture_id,)
            )
            assert cur.fetchone()[0] >= 1
        db_conn.commit()
    finally:
        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM predictions WHERE fixture_id = %s;", (fixture_id,))
        db_conn.commit()


def test_concurrent_predict_calls_all_succeed_quickly(client, db_conn):
    """Regression test for two real bugs found while building the frontend:
    (1) SimpleConnectionPool corrupting under concurrent access from
    FastAPI's worker threads (fixed: ThreadedConnectionPool), and (2)
    team_standing_by_date precomputing position for every team at every
    date before filtering to the one row needed — 21,700 loop iterations
    and 6-7s for a single fixture (fixed: compute position on demand, only
    for the two teams in the match being featured). This mirrors the
    frontend's actual load pattern: one /predict call per fixture shown,
    fired in parallel via Promise.all."""
    fixtures = client.get("/matches").json()
    fixture_ids = [f["fixture_id"] for f in fixtures]

    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(fixture_ids)) as pool:
        responses = list(
            pool.map(lambda fid: client.get("/predict", params={"fixture_id": fid}), fixture_ids)
        )
    elapsed = time.time() - start

    try:
        assert all(r.status_code == 200 for r in responses)
        # Generous bound for a hosted free-tier DB — the original bug meant
        # some of these requests timed out entirely (>15s) rather than just
        # being slow.
        assert elapsed < 15, f"{len(fixture_ids)} concurrent /predict calls took {elapsed:.1f}s"
    finally:
        with db_conn.cursor() as cur:
            cur.execute(
                "DELETE FROM predictions WHERE fixture_id = ANY(%s);", (fixture_ids,)
            )
        db_conn.commit()
