"""
FastAPI TestClient suite. Runs against the real hosted database (not a
disposable test schema — this project uses a single hosted free-tier
instance for everything, dev included, matching every other test suite's
approach in this repo; see PLAN.md). Any prediction row this suite inserts
is deleted afterward so repeated test runs don't clutter real data.
"""

import asyncio
import concurrent.futures
import os
import time

import psycopg2
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from api import main as api_main
from api.main import app

load_dotenv()


@pytest.fixture(scope="module")
def client():
    # The lifespan would otherwise start the background football-data.org
    # refresh (when an API key is in .env) and mutate real data mid-suite.
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("LIVE_REFRESH_MINUTES", "0")
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


def test_standings_returns_20_teams_ranked(client):
    response = client.get("/standings")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 20
    assert {"team", "position", "played", "points", "wins", "draws", "losses", "goal_diff"} <= body[0].keys()
    positions = [row["position"] for row in body]
    assert positions == sorted(positions)


def test_result_unplayed_fixture_returns_not_played(client):
    fixtures = client.get("/matches").json()
    fixture = fixtures[0]

    response = client.get(
        "/result",
        params={
            "season": fixture["season"],
            "home_team": fixture["home_team"],
            "away_team": fixture["away_team"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"played": False, "result": None, "home_goals": None, "away_goals": None}


def test_result_played_match_returns_final_score(client):
    response = client.get(
        "/result",
        params={"season": "2019-2020", "home_team": "Liverpool", "away_team": "Norwich City"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"played": True, "result": "H", "home_goals": 4, "away_goals": 1}


def test_results_lists_played_matches_for_a_season(client):
    response = client.get("/results", params={"season": "2019-2020"})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 380
    assert {"home_team", "away_team", "result", "home_goals", "away_goals"} == rows[0].keys()
    liverpool_norwich = [r for r in rows if r["home_team"] == "Liverpool" and r["away_team"] == "Norwich City"]
    assert liverpool_norwich == [
        {"home_team": "Liverpool", "away_team": "Norwich City", "result": "H", "home_goals": 4, "away_goals": 1}
    ]


def test_results_unknown_season_is_empty(client):
    response = client.get("/results", params={"season": "1900-1901"})
    assert response.status_code == 200
    assert response.json() == []


def test_live_refresh_loop_runs_repeatedly_and_survives_failures(monkeypatch):
    calls = []

    def flaky_refresh(database_url, api_key):
        calls.append((database_url, api_key))
        if len(calls) == 1:
            raise RuntimeError("football-data.org is down")
        return {"finished_inserted": 0}

    monkeypatch.setattr(api_main, "refresh_live_data", flaky_refresh)

    async def run():
        task = asyncio.create_task(api_main.live_refresh_loop("db-url", "key", 0.01))
        await asyncio.sleep(0.2)
        task.cancel()

    asyncio.run(run())
    assert len(calls) >= 2  # ran again after the first call raised
    assert calls[0] == ("db-url", "key")


def test_connection_closed_by_server_while_idle_is_replaced(client, db_conn):
    """Regression: after sitting idle, the hosted DB closes pooled
    connections; the next request used to fail with "server closed the
    connection unexpectedly". The pool must notice and open a fresh one."""
    from api import db as api_db

    with api_db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_backend_pid();")
            pid = cur.fetchone()[0]

    with db_conn.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(%s);", (pid,))
    db_conn.commit()
    api_db._last_used.clear()  # as if it had sat idle long enough to need a check

    assert client.get("/matches").status_code == 200


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
