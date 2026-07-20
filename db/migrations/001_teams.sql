-- Canonical list of Premier League teams. One row per real-world club,
-- regardless of how many different spellings appear across data sources —
-- name normalization happens via team_aliases (002), not here.

CREATE TABLE teams (
    team_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    football_data_org_id INTEGER UNIQUE
);
