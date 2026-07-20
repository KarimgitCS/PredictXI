# Model comparison — logistic regression vs. XGBoost

Evaluated on the held-out test season (2019-2020), never seen during training or calibration.

| Metric | Logistic Regression | XGBoost |
|---|---|---|
| Accuracy | 0.5316 | 0.5158 |
| Log loss | 1.0341 | 1.0243 |
| Brier score (multiclass) | 0.6101 | 0.6103 |
| Test samples | 380 | 380 |

Lower is better for log loss and Brier score. Full calibration-curve data (predicted probability vs. actual outcome frequency, per class, per model) is in `calibration_data.json` in this directory — that's what the frontend's calibration chart (Phase 8) plots.
