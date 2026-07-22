-- Periodic snapshots of the current-season league table, pulled from
-- football-data.org's standings endpoint. Used for display (a "league
-- table" view in the frontend) — match_features derives its own
-- position/PPG differential straight from matches, so that feature is
-- never dependent on this table being freshly fetched.

CREATE TABLE standings_snapshot (
    snapshot_id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    season TEXT NOT NULL,
    team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE RESTRICT,
    position SMALLINT NOT NULL,
    played SMALLINT NOT NULL,
    points SMALLINT NOT NULL,
    goal_diff SMALLINT NOT NULL,
    wins SMALLINT NOT NULL,
    draws SMALLINT NOT NULL,
    losses SMALLINT NOT NULL,
    UNIQUE (snapshot_date, team_id)
);
