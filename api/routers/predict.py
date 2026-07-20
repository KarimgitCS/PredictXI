"""
GET /predict?fixture_id=... — compute features for that fixture from
match_features, run them through the active model (loaded once at app
startup, cached in app.state — not re-read from disk on every request),
return calibrated probabilities, and log the prediction.
"""

import sys
from pathlib import Path

import pandas as pd
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Request

from api.db import get_db
from api.schemas import PredictionOut

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "ml"))
from train import FEATURE_COLUMNS, RESULT_CLASSES

router = APIRouter()


def _to_float_or_nan(value):
    """Postgres NUMERIC columns arrive via psycopg2 as Decimal; sklearn/
    xgboost want plain floats, with NaN (not None) for missing values."""
    return float(value) if value is not None else float("nan")


@router.get("/predict", response_model=PredictionOut)
def predict(fixture_id: int, request: Request, conn=Depends(get_db)):
    model = request.app.state.active_model
    model_info = request.app.state.active_model_info
    if model is None:
        raise HTTPException(status_code=503, detail="No active model registered.")

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT mf.*, ht.name AS home_team, at.name AS away_team
            FROM match_features mf
            JOIN teams ht ON ht.team_id = mf.home_team_id
            JOIN teams at ON at.team_id = mf.away_team_id
            WHERE mf.target_type = 'fixture' AND mf.target_id = %s;
            """,
            (fixture_id,),
        )
        feature_row = cur.fetchone()
    if feature_row is None:
        raise HTTPException(status_code=404, detail=f"No upcoming fixture with id {fixture_id}.")

    X = pd.DataFrame([{col: _to_float_or_nan(feature_row[col]) for col in FEATURE_COLUMNS}])
    probs = model.predict_proba(X)[0]
    predicted_outcome = RESULT_CLASSES[probs.argmax()]

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO predictions
                (fixture_id, model_id, prob_home, prob_draw, prob_away, predicted_outcome)
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            (fixture_id, model_info["model_id"],
             float(probs[0]), float(probs[1]), float(probs[2]), predicted_outcome),
        )

    return PredictionOut(
        fixture_id=fixture_id,
        home_team=feature_row["home_team"],
        away_team=feature_row["away_team"],
        prob_home=round(float(probs[0]), 4),
        prob_draw=round(float(probs[1]), 4),
        prob_away=round(float(probs[2]), 4),
        predicted_outcome=predicted_outcome,
        model_name=model_info["name"],
    )
