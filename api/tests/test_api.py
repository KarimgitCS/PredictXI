"""
FastAPI TestClient suite. Runs against the real hosted database (not a
disposable test schema — this project uses a single hosted free-tier
instance for everything, dev included, matching every other phase's test
approach in this repo; see PLAN.md). Any prediction row this suite inserts
is deleted afterward so repeated test runs don't clutter real data.
"""

import os

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
