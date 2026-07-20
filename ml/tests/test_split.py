"""
Verifies ml/train.py's chronological split never lets a test/validation
season's data leak into training — the one thing that would silently
invalidate the whole "no data leakage" design even though the SQL views
themselves are leakage-safe (see PLAN.md's risk list).
"""

import pandas as pd

from ml.train import TEST_SEASON, TRAIN_SEASONS, VALIDATION_SEASON, chronological_split


def test_train_val_test_seasons_are_disjoint():
    train_set = set(TRAIN_SEASONS)
    assert VALIDATION_SEASON not in train_set
    assert TEST_SEASON not in train_set
    assert VALIDATION_SEASON != TEST_SEASON


def test_split_assigns_rows_to_the_correct_season_only():
    seasons = TRAIN_SEASONS + [VALIDATION_SEASON, TEST_SEASON]
    df = pd.DataFrame({
        "season": seasons,
        "match_date": pd.date_range("2010-01-01", periods=len(seasons), freq="365D"),
        "result": ["H"] * len(seasons),
    })

    train_df, val_df, test_df = chronological_split(df)

    assert set(train_df["season"]) == set(TRAIN_SEASONS)
    assert set(val_df["season"]) == {VALIDATION_SEASON}
    assert set(test_df["season"]) == {TEST_SEASON}


def test_no_match_date_from_test_or_val_season_appears_in_train():
    seasons = TRAIN_SEASONS + [VALIDATION_SEASON, TEST_SEASON]
    dates = pd.date_range("2010-08-01", periods=len(seasons), freq="365D")
    df = pd.DataFrame({"season": seasons, "match_date": dates, "result": ["H"] * len(seasons)})

    train_df, val_df, test_df = chronological_split(df)

    train_dates = set(train_df["match_date"])
    assert train_dates.isdisjoint(set(val_df["match_date"]))
    assert train_dates.isdisjoint(set(test_df["match_date"]))
