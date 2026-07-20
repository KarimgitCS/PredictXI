-- Unified table for both historical (football-data.co.uk, 2010-2020) and
-- current-season completed matches (football-data.org, backfilled by
-- etl/fetch_live_data.py in Phase 3). One row per finished match.
--
-- `source` distinguishes provenance. Stat columns (shots/corners/fouls/cards)
-- are nullable because football-data.org's free tier does not provide them —
-- source='api' rows will legitimately have NULLs there. This is expected,
-- not a data-quality bug (see PLAN.md's "free-tier stat gap" note).
--
-- `result` is a generated column, not set by application code, so it can
-- never drift out of sync with the actual scoreline.

CREATE TABLE matches (
    match_id SERIAL PRIMARY KEY,
    season TEXT NOT NULL,
    match_date DATE NOT NULL,
    home_team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE RESTRICT,
    away_team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE RESTRICT,

    home_goals SMALLINT NOT NULL CHECK (home_goals >= 0),
    away_goals SMALLINT NOT NULL CHECK (away_goals >= 0),
    result CHAR(1) GENERATED ALWAYS AS (
        CASE
            WHEN home_goals > away_goals THEN 'H'
            WHEN home_goals < away_goals THEN 'A'
            ELSE 'D'
        END
    ) STORED,

    home_shots SMALLINT,
    away_shots SMALLINT,
    home_shots_on_target SMALLINT,
    away_shots_on_target SMALLINT,
    home_corners SMALLINT,
    away_corners SMALLINT,
    home_fouls SMALLINT,
    away_fouls SMALLINT,
    home_yellow SMALLINT,
    away_yellow SMALLINT,
    home_red SMALLINT,
    away_red SMALLINT,

    source TEXT NOT NULL CHECK (source IN ('historical_csv', 'api')),

    CHECK (home_team_id <> away_team_id),
    UNIQUE (season, match_date, home_team_id, away_team_id)
);

-- Every rolling-window feature query in Phase 4 filters by team_id and orders
-- by match_date, from both the home and away side — these indexes are what
-- keep those window functions fast as the table grows.
CREATE INDEX idx_matches_home_team_date ON matches (home_team_id, match_date);
CREATE INDEX idx_matches_away_team_date ON matches (away_team_id, match_date);
