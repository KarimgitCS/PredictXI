"""
Smoke test for ml/train.py's model-fitting functions on a tiny synthetic
dataset — no database needed. Catches sklearn/xgboost API breakage cheaply,
before ever touching the real ~3,800-row dataset.
"""

import numpy as np
import pandas as pd
import pytest

from ml.train import FEATURE_COLUMNS, RESULT_CLASSES, calibrate, train_logreg, train_xgboost


@pytest.fixture
def synthetic_data():
    rng = np.random.default_rng(seed=0)
    n = 300
    X = pd.DataFrame(
        rng.normal(size=(n, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS
    )
    # Sprinkle in some NaNs — both models need to tolerate this, per the
    # documented free-tier-stats-gap / new-team NULL-feature situations.
    X.iloc[0:5, 0] = np.nan
    # Balanced classes, well above CalibratedClassifierCV's default 5-fold
    # minimum per class — an imbalanced tiny sample here would trigger a
    # sklearn UserWarning that's specific to this synthetic data, not a real
    # concern (see PLAN.md/commit notes on FrozenEstimator's behavior).
    y = np.tile(np.arange(len(RESULT_CLASSES)), n // len(RESULT_CLASSES) + 1)[:n]
    rng.shuffle(y)
    return X, y


def test_logreg_trains_and_predicts(synthetic_data):
    X, y = synthetic_data
    model = train_logreg(X, y)
    probs = model.predict_proba(X)
    assert probs.shape == (len(X), len(RESULT_CLASSES))
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-6)


def test_xgboost_trains_and_predicts(synthetic_data):
    X, y = synthetic_data
    model = train_xgboost(X, y)
    probs = model.predict_proba(X)
    assert probs.shape == (len(X), len(RESULT_CLASSES))
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-6)


def test_calibration_runs_end_to_end(synthetic_data):
    X, y = synthetic_data
    X_train, y_train = X.iloc[:200], y[:200]
    X_val, y_val = X.iloc[200:], y[200:]

    for train_fn in (train_logreg, train_xgboost):
        fitted = train_fn(X_train, y_train)
        calibrated = calibrate(fitted, X_val, y_val)
        probs = calibrated.predict_proba(X_val)
        assert probs.shape == (len(X_val), len(RESULT_CLASSES))
        assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-6)
