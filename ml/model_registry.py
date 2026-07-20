"""
Persists trained models: saves the artifact to ml/artifacts/, inserts a row
into `models` (algorithm, metrics, feature set version, artifact path), and
flips `is_active` on whichever model wins by log loss — the standard proper
scoring rule for calibrated probabilities, and what api/routers/predict.py
(Phase 7) will load to serve predictions.

Usage:
    python ml/model_registry.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from evaluate import evaluate_model
from train import run_training_pipeline

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"

# Bump this manually if FEATURE_COLUMNS in train.py ever changes shape —
# a stored model's feature list must match what it was trained on.
FEATURE_SET_VERSION = "v1"


def save_artifact(name: str, model) -> Path:
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = ARTIFACTS_DIR / f"{name}_{timestamp}.joblib"
    joblib.dump(model, path)
    return path


def register_model(cur, name: str, algorithm: str, artifact_path: Path,
                    feature_set_version: str, metrics: dict) -> int:
    cur.execute(
        """
        INSERT INTO models (name, algorithm, feature_set_version, metrics, artifact_path)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING model_id;
        """,
        (name, algorithm, feature_set_version, json.dumps(metrics), str(artifact_path)),
    )
    return cur.fetchone()[0]


def activate_model(cur, model_id: int) -> None:
    """Deactivates whatever's currently active before activating the new
    one — required so the partial unique index (at most one active model,
    from 006_models.sql) is never violated mid-transaction."""
    cur.execute("UPDATE models SET is_active = false WHERE is_active = true;")
    cur.execute("UPDATE models SET is_active = true WHERE model_id = %s;", (model_id,))


def load_model(artifact_path: str):
    return joblib.load(artifact_path)


def main() -> None:
    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set — check your .env file.")

    conn = psycopg2.connect(database_url)
    try:
        pipeline = run_training_pipeline(conn)
        X_test, y_test = pipeline["splits"]["test"]
        result_classes = pipeline["result_classes"]

        registered = {}
        with conn:
            with conn.cursor() as cur:
                for name, model in pipeline["models"].items():
                    eval_result = evaluate_model(model, X_test, y_test, result_classes)
                    artifact_path = save_artifact(name, model)
                    model_id = register_model(
                        cur, name=name, algorithm=name, artifact_path=artifact_path,
                        feature_set_version=FEATURE_SET_VERSION, metrics=eval_result["metrics"],
                    )
                    registered[name] = {"model_id": model_id, "metrics": eval_result["metrics"]}

                best_name = min(registered, key=lambda n: registered[n]["metrics"]["log_loss"])
                activate_model(cur, registered[best_name]["model_id"])
    finally:
        conn.close()

    for name, info in registered.items():
        marker = " (active)" if name == best_name else ""
        print(f"{name}: model_id={info['model_id']} log_loss={info['metrics']['log_loss']}{marker}")


if __name__ == "__main__":
    main()
