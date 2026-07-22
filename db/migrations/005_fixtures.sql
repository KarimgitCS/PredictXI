-- Upcoming (not-yet-played) current-season fixtures, from football-data.org.
-- fixture_id reuses football-data.org's own match id directly (not a local
-- SERIAL) so etl/fetch_live_data.py can upsert on it idempotently
-- (ON CONFLICT (fixture_id) DO UPDATE) without needing a separate lookup.
--
-- Once a fixture is actually played, etl/fetch_live_data.py inserts the
-- result into `matches` (source='api') — rows here stay purely "not played
-- yet" so match_features can tell at a glance which side of the
-- training/serving split a given match belongs to.

CREATE TABLE fixtures (
    fixture_id INTEGER PRIMARY KEY,
    season TEXT NOT NULL,
    matchday SMALLINT,
    kickoff_at TIMESTAMPTZ NOT NULL,
    home_team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE RESTRICT,
    away_team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE RESTRICT,
    status TEXT NOT NULL,
    CHECK (home_team_id <> away_team_id)
);

CREATE INDEX idx_fixtures_kickoff ON fixtures (kickoff_at);
