-- One row per prediction made, tied to exactly one of a fixture (a future
-- match, for live serving) or a match (a historical match, for backtesting).
-- actual_outcome starts NULL and is backfilled once the match completes —
-- comparing it against prob_home/prob_draw/prob_away over many rows is what
-- the frontend's calibration chart (Phase 8) is built from.

CREATE TABLE predictions (
    prediction_id SERIAL PRIMARY KEY,
    fixture_id INTEGER REFERENCES fixtures(fixture_id) ON DELETE CASCADE,
    match_id INTEGER REFERENCES matches(match_id) ON DELETE CASCADE,
    model_id INTEGER NOT NULL REFERENCES models(model_id) ON DELETE RESTRICT,
    predicted_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    prob_home NUMERIC(5, 4) NOT NULL CHECK (prob_home BETWEEN 0 AND 1),
    prob_draw NUMERIC(5, 4) NOT NULL CHECK (prob_draw BETWEEN 0 AND 1),
    prob_away NUMERIC(5, 4) NOT NULL CHECK (prob_away BETWEEN 0 AND 1),
    predicted_outcome CHAR(1) NOT NULL CHECK (predicted_outcome IN ('H', 'D', 'A')),
    actual_outcome CHAR(1) CHECK (actual_outcome IN ('H', 'D', 'A')),

    CHECK (abs(prob_home + prob_draw + prob_away - 1) < 0.01),
    CHECK ((fixture_id IS NOT NULL)::int + (match_id IS NOT NULL)::int = 1)
);

CREATE INDEX idx_predictions_fixture ON predictions (fixture_id);
CREATE INDEX idx_predictions_match ON predictions (match_id);
