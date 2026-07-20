"""
Verifies ml/model_registry.py's "Done when" criteria: after registering a
model, a row appears in `models`, and loading its artifact back reproduces
the same predictions. Uses a tiny synthetic model (not the real ~3,800-row
pipeline) for speed. All DB writes are rolled back and the artifact file is
deleted afterward — no test data left behind in the real database or on
disk.
"""

import os

import numpy as np
import psycopg2
import pytest
from dotenv import load_dotenv
from sklearn.linear_model import LogisticRegression

from ml.model_registry import activate_model, load_model, register_model, save_artifact

load_dotenv()


@pytest.fixture
def conn():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")
    connection = psycopg2.connect(database_url)
    yield connection
    connection.rollback()  # never commit test data
    connection.close()


def test_register_and_reload_reproduces_predictions(conn):
    rng = np.random.default_rng(0)
    X = rng.normal(size=(50, 3))
    y = rng.integers(0, 3, size=50)
    model = LogisticRegression(max_iter=200).fit(X, y)
    original_probs = model.predict_proba(X)

    artifact_path = save_artifact("test_model", model)
    try:
        with conn.cursor() as cur:
            model_id = register_model(
                cur, name="test_model", algorithm="test",
                artifact_path=artifact_path, feature_set_version="test",
                metrics={"accuracy": 1.0, "log_loss": 0.1, "brier_score": 0.1},
            )
            cur.execute("SELECT count(*) FROM models WHERE model_id = %s;", (model_id,))
            assert cur.fetchone()[0] == 1

        reloaded = load_model(str(artifact_path))
        reloaded_probs = reloaded.predict_proba(X)
        assert np.allclose(original_probs, reloaded_probs)
    finally:
        artifact_path.unlink(missing_ok=True)


def test_activate_model_enforces_single_active_model(conn):
    rng = np.random.default_rng(1)
    X = rng.normal(size=(50, 3))
    y = rng.integers(0, 3, size=50)
    model = LogisticRegression(max_iter=200).fit(X, y)

    paths = []
    try:
        with conn.cursor() as cur:
            path_a = save_artifact("test_model_a", model)
            paths.append(path_a)
            id_a = register_model(cur, "test_model_a", "test", path_a, "test", {"log_loss": 1.0})

            path_b = save_artifact("test_model_b", model)
            paths.append(path_b)
            id_b = register_model(cur, "test_model_b", "test", path_b, "test", {"log_loss": 0.5})

            activate_model(cur, id_a)
            activate_model(cur, id_b)  # should deactivate a, activate b

            cur.execute(
                "SELECT model_id FROM models WHERE is_active = true AND model_id IN (%s, %s);",
                (id_a, id_b),
            )
            active_ids = [row[0] for row in cur.fetchall()]
        assert active_ids == [id_b]
    finally:
        for path in paths:
            path.unlink(missing_ok=True)
