-- Maps every raw team-name spelling seen in either data source to a single
-- canonical team_id. Needed because football-data.co.uk and football-data.org
-- disagree on names (e.g. "Man United" vs "Manchester United"), and because
-- teams get renamed/promoted/relegated across the 10 historical seasons.

CREATE TABLE team_aliases (
    source TEXT NOT NULL CHECK (source IN ('football-data.co.uk', 'football-data.org')),
    alias TEXT NOT NULL,
    team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE RESTRICT,
    PRIMARY KEY (source, alias)
);
