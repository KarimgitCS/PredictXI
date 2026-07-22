"""
Pulls match_features from the database, splits chronologically by season —
never a random shuffle, which would leak future seasons into training even
though the SQL views themselves are leakage-safe — and trains + calibrates
logistic regression and XGBoost.

Usage:
    python ml/train.py     # trains both models, prints row counts per split

Importable as a library by ml/evaluate.py and ml/model_registry.py, which
both need the exact same split and fitted models without duplicating this
logic.
"""

import os
import sys

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

# 8 seasons train / 1 validate / 1 test, per PLAN.md. "Validate" here means
# the calibration set (CalibratedClassifierCV fits on it), not hyperparameter
# tuning — this project deliberately doesn't chase hyperparameter search.
TRAIN_SEASONS = [
    "2010-2011", "2011-2012", "2012-2013", "2013-2014",
    "2014-2015", "2015-2016", "2016-2017", "2017-2018",
]
VALIDATION_SEASON = "2018-2019"
TEST_SEASON = "2019-2020"

# Fixed class order used everywhere a model outputs a probability triple —
# the API and the evaluation report both rely on this exact order, so it
# lives here once rather than being re-derived anywhere else.
RESULT_CLASSES = ["H", "D", "A"]

FEATURE_COLUMNS = [
    "home_rolling_points_5", "home_rolling_goals_for_5", "home_rolling_goals_against_5",
    "home_rolling_shots_on_target_5", "home_rolling_corners_5", "home_rolling_fouls_5",
    "home_rolling_cards_5",
    "away_rolling_points_5", "away_rolling_goals_for_5", "away_rolling_goals_against_5",
    "away_rolling_shots_on_target_5", "away_rolling_corners_5", "away_rolling_fouls_5",
    "away_rolling_cards_5",
    "position_differential", "ppg_differential",
    "home_team_home_win_rate", "away_team_away_win_rate",
    "h2h_home_win_rate", "h2h_draw_rate", "h2h_away_win_rate",
]


def load_feature_data(conn) -> pd.DataFrame:
    columns = ", ".join(["season", "match_date", "result"] + FEATURE_COLUMNS)
    return pd.read_sql(
        f"SELECT {columns} FROM match_features WHERE target_type = 'match';", conn
    )


def chronological_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train_df = df[df["season"].isin(TRAIN_SEASONS)]
    val_df = df[df["season"] == VALIDATION_SEASON]
    test_df = df[df["season"] == TEST_SEASON]
    return train_df, val_df, test_df


def build_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    X = df[FEATURE_COLUMNS]
    y = df["result"].map(RESULT_CLASSES.index).to_numpy()
    return X, y


def train_logreg(X_train, y_train) -> Pipeline:
    """NaN-tolerant via an explicit imputer — unlike XGBoost, sklearn's
    LogisticRegression cannot take NaN directly."""
    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("classify", LogisticRegression(max_iter=1000)),
    ])
    pipeline.fit(X_train, y_train)
    return pipeline


def train_xgboost(X_train, y_train) -> XGBClassifier:
    """No imputer needed — XGBoost handles NaN natively and can use
    missingness itself as a signal."""
    model = XGBClassifier(
        objective="multi:softprob",
        num_class=len(RESULT_CLASSES),
        eval_metric="mlogloss",
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
    )
    model.fit(X_train, y_train)
    return model


def calibrate(fitted_model, X_val, y_val) -> CalibratedClassifierCV:
    """Platt scaling (sigmoid), not isotonic: sklearn's own docs advise
    against isotonic below ~1000 calibration samples (it tends to overfit),
    and our validation season is 380 matches. FrozenEstimator wraps the
    already-fitted model so calibration fits only on X_val/y_val, never
    touching X_train again."""
    calibrated = CalibratedClassifierCV(estimator=FrozenEstimator(fitted_model), method="sigmoid")
    calibrated.fit(X_val, y_val)
    return calibrated


def run_training_pipeline(conn) -> dict:
    df = load_feature_data(conn)
    train_df, val_df, test_df = chronological_split(df)

    X_train, y_train = build_xy(train_df)
    X_val, y_val = build_xy(val_df)
    X_test, y_test = build_xy(test_df)

    logreg = calibrate(train_logreg(X_train, y_train), X_val, y_val)
    xgb = calibrate(train_xgboost(X_train, y_train), X_val, y_val)

    return {
        "models": {"logreg": logreg, "xgboost": xgb},
        "feature_columns": FEATURE_COLUMNS,
        "result_classes": RESULT_CLASSES,
        "splits": {
            "train": (X_train, y_train),
            "val": (X_val, y_val),
            "test": (X_test, y_test),
        },
    }


def main() -> None:
    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set — check your .env file.")

    conn = psycopg2.connect(database_url)
    try:
        result = run_training_pipeline(conn)
    finally:
        conn.close()

    for name in ("train", "val", "test"):
        X, _ = result["splits"][name]
        print(f"{name}: {len(X)} rows")
    print(f"Trained and calibrated: {', '.join(result['models'])}")


if __name__ == "__main__":
    main()
