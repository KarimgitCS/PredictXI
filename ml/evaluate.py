"""
Evaluates the logreg and xgboost models trained by ml/train.py on the held-out
test season (2019-2020, never touched during training or calibration),
writing a comparison report and the underlying calibration-curve data for
the frontend's calibration chart.

Usage:
    python ml/evaluate.py
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from sklearn.metrics import accuracy_score, log_loss
import psycopg2

sys.path.insert(0, str(Path(__file__).parent))
from train import run_training_pipeline

REPORTS_DIR = Path(__file__).parent.parent / "reports"
N_CALIBRATION_BINS = 10


def brier_score_multiclass(y_true: np.ndarray, y_proba: np.ndarray, n_classes: int) -> float:
    """Multiclass generalization of the Brier score: mean squared error
    between predicted probabilities and one-hot true labels, summed across
    classes. 0 is perfect, higher is worse (max 2 for this formulation)."""
    one_hot = np.eye(n_classes)[y_true]
    return float(np.mean(np.sum((y_proba - one_hot) ** 2, axis=1)))


def calibration_bins(y_true_binary: np.ndarray, y_proba: np.ndarray, n_bins: int) -> list[dict]:
    """Buckets predictions into n_bins equal-width probability ranges and
    reports, per bin, the mean predicted probability vs. the actual
    frequency of the outcome — the data a calibration chart plots."""
    bin_edges = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(y_proba, bin_edges[1:-1])

    bins = []
    for b in range(n_bins):
        mask = bin_indices == b
        count = int(mask.sum())
        if count == 0:
            continue
        bins.append({
            "bin_range": [round(float(bin_edges[b]), 2), round(float(bin_edges[b + 1]), 2)],
            "predicted_mean": round(float(y_proba[mask].mean()), 4),
            "observed_frequency": round(float(y_true_binary[mask].mean()), 4),
            "count": count,
        })
    return bins


def evaluate_model(model, X_test, y_test, result_classes: list[str]) -> dict:
    y_proba = model.predict_proba(X_test)
    y_pred = np.argmax(y_proba, axis=1)

    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "log_loss": round(float(log_loss(y_test, y_proba, labels=list(range(len(result_classes))))), 4),
        "brier_score": round(brier_score_multiclass(y_test, y_proba, len(result_classes)), 4),
        "n_test_samples": len(y_test),
    }

    calibration = {}
    for i, cls in enumerate(result_classes):
        y_true_binary = (y_test == i).astype(int)
        calibration[cls] = calibration_bins(y_true_binary, y_proba[:, i], N_CALIBRATION_BINS)

    return {"metrics": metrics, "calibration": calibration}


def render_report(results: dict, result_classes: list[str]) -> str:
    lines = [
        "# Model comparison — logistic regression vs. XGBoost",
        "",
        "Evaluated on the held-out test season (2019-2020), never seen during "
        "training or calibration.",
        "",
        "| Metric | Logistic Regression | XGBoost |",
        "|---|---|---|",
    ]
    for key, label in [("accuracy", "Accuracy"), ("log_loss", "Log loss"),
                        ("brier_score", "Brier score (multiclass)")]:
        lines.append(
            f"| {label} | {results['logreg']['metrics'][key]} | {results['xgboost']['metrics'][key]} |"
        )
    lines.append(f"| Test samples | {results['logreg']['metrics']['n_test_samples']} | "
                 f"{results['xgboost']['metrics']['n_test_samples']} |")
    lines += [
        "",
        "Lower is better for log loss and Brier score. Full calibration-curve "
        "data (predicted probability vs. actual outcome frequency, per class, "
        "per model) is in `calibration_data.json` in this directory — that's "
        "what the frontend's calibration chart plots.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set — check your .env file.")

    conn = psycopg2.connect(database_url)
    try:
        pipeline = run_training_pipeline(conn)
    finally:
        conn.close()

    X_test, y_test = pipeline["splits"]["test"]
    result_classes = pipeline["result_classes"]

    results = {
        name: evaluate_model(model, X_test, y_test, result_classes)
        for name, model in pipeline["models"].items()
    }

    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "model_comparison.md").write_text(render_report(results, result_classes))
    (REPORTS_DIR / "calibration_data.json").write_text(
        json.dumps({name: r["calibration"] for name, r in results.items()}, indent=2)
    )

    for name, r in results.items():
        print(f"{name}: {r['metrics']}")
    print(f"\nWrote reports/model_comparison.md and reports/calibration_data.json")


if __name__ == "__main__":
    main()
