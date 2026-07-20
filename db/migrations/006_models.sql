-- Registry of trained model artifacts (Phase 6). The partial unique index
-- makes it structurally impossible for more than one model to be active at
-- once, so api/routers/predict.py (Phase 7) never has to decide *which*
-- active model to use — there can only ever be exactly one or zero.

CREATE TABLE models (
    model_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    trained_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    feature_set_version TEXT NOT NULL,
    metrics JSONB NOT NULL,
    artifact_path TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false
);

CREATE UNIQUE INDEX one_active_model ON models ((is_active)) WHERE is_active = true;
