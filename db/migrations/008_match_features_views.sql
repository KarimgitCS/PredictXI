-- Feature views. Every rolling/aggregate feature here follows one rule:
-- it may only use matches strictly BEFORE the match being featured.
--
-- Leakage-safety mechanism, used uniformly throughout this file: rolling
-- windows are computed as CURRENT-ROW-inclusive over each team's own
-- sequence of played matches (team_match_log), then read via a LATERAL join
-- that finds the most recent such row with match_date < the target's date
-- (strict). That single "<" is the leakage boundary. It works identically
-- for two different kinds of targets:
--   - a historical match: the team's own row for that exact match shares
--     its date, so "<" (not "<=") correctly skips it and lands on the
--     team's previous match instead.
--   - a fixture (not yet played, no row of its own): "<" simply finds the
--     team's last completed match before kickoff.
-- One boundary check, one code path for both training data and live serving
-- — not two separate rolling-window strategies for two kinds of targets.

-- 1. Unpivot matches into one row per team per match (home and away
-- perspective), so every rolling feature below can be a single
-- PARTITION BY team_id window instead of separate home/away logic.
CREATE OR REPLACE VIEW team_match_log AS
SELECT
    match_id, season, match_date,
    home_team_id AS team_id, away_team_id AS opponent_id, true AS is_home,
    CASE WHEN result = 'H' THEN 3 WHEN result = 'D' THEN 1 ELSE 0 END AS points,
    home_goals AS goals_for, away_goals AS goals_against,
    home_shots_on_target AS shots_on_target, home_corners AS corners,
    home_fouls AS fouls, home_yellow + home_red AS cards
FROM matches
UNION ALL
SELECT
    match_id, season, match_date,
    away_team_id AS team_id, home_team_id AS opponent_id, false AS is_home,
    CASE WHEN result = 'A' THEN 3 WHEN result = 'D' THEN 1 ELSE 0 END AS points,
    away_goals AS goals_for, home_goals AS goals_against,
    away_shots_on_target AS shots_on_target, away_corners AS corners,
    away_fouls AS fouls, away_yellow + away_red AS cards
FROM matches;

-- 2a. Rolling 5-match form (points, goals, shots on target, corners, fouls,
-- cards), carried over season boundaries (partitioned by team_id only, not
-- team_id+season — a team's first match of a new season uses its last
-- matches from the previous one). CURRENT ROW inclusive — see the note
-- above on why, and why that's still leakage-safe.
CREATE OR REPLACE VIEW team_rolling_form AS
SELECT
    match_id, team_id, opponent_id, match_date, is_home,
    AVG(points) OVER w AS rolling_points_5,
    AVG(goals_for) OVER w AS rolling_goals_for_5,
    AVG(goals_against) OVER w AS rolling_goals_against_5,
    AVG(shots_on_target) OVER w AS rolling_shots_on_target_5,
    AVG(corners) OVER w AS rolling_corners_5,
    AVG(fouls) OVER w AS rolling_fouls_5,
    AVG(cards) OVER w AS rolling_cards_5
FROM team_match_log
WINDOW w AS (
    PARTITION BY team_id ORDER BY match_date
    ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
);

-- 2b. Venue-specific win rate (home team's home win rate / away team's away
-- win rate), expanding over the team's entire history at that venue.
CREATE OR REPLACE VIEW team_venue_win_rate AS
SELECT
    match_id, team_id, match_date, is_home,
    AVG(CASE WHEN points = 3 THEN 1.0 ELSE 0 END) OVER w AS win_rate
FROM team_match_log
WINDOW w AS (
    PARTITION BY team_id, is_home ORDER BY match_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);

-- 3a. Season-cumulative points and games played, expanding within a season.
CREATE OR REPLACE VIEW team_season_progress AS
SELECT
    match_id, team_id, season, match_date,
    SUM(points) OVER w AS points_through_match,
    COUNT(*) OVER w AS games_through_match
FROM team_match_log
WINDOW w AS (
    PARTITION BY team_id, season ORDER BY match_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);

-- Unifies historical/live matches and upcoming fixtures into one set of
-- "things that need features computed" — training targets (result known)
-- and serving targets (result NULL) go through the exact same joins below.
CREATE OR REPLACE VIEW prediction_targets AS
SELECT match_id AS target_id, 'match' AS target_type, season, match_date,
       home_team_id, away_team_id, result
FROM matches
UNION ALL
SELECT fixture_id AS target_id, 'fixture' AS target_type, season,
       kickoff_at::date AS match_date, home_team_id, away_team_id,
       NULL::char(1) AS result
FROM fixtures;

-- Every team that appears in a season, whether from a played match or a
-- still-upcoming fixture — the full set "position" needs to rank against.
CREATE OR REPLACE VIEW season_teams AS
SELECT DISTINCT season, team_id FROM team_match_log
UNION
SELECT DISTINCT season, home_team_id AS team_id FROM fixtures
UNION
SELECT DISTINCT season, away_team_id AS team_id FROM fixtures;

-- 3b. League position, as of every date a feature will actually be needed
-- for. Simplification (documented in PLAN.md): ranks each team by its own
-- most recent prior cumulative points as of that date, rather than trying
-- to sync to a shared "matchday number" across teams that played on
-- different dates — still leakage-safe (every input is strictly prior),
-- just an approximation of a perfectly-synced league table snapshot.
CREATE OR REPLACE VIEW team_standing_by_date AS
SELECT
    pd.season,
    pd.match_date AS as_of_date,
    st.team_id,
    COALESCE(tsp.points_through_match, 0) AS points,
    COALESCE(tsp.games_through_match, 0) AS games_played,
    ROUND(
        COALESCE(tsp.points_through_match, 0)::numeric
        / NULLIF(COALESCE(tsp.games_through_match, 0), 0),
        3
    ) AS ppg,
    RANK() OVER (
        PARTITION BY pd.season, pd.match_date
        ORDER BY COALESCE(tsp.points_through_match, 0) DESC
    ) AS position
FROM (SELECT DISTINCT season, match_date FROM prediction_targets) pd
JOIN season_teams st ON st.season = pd.season
LEFT JOIN LATERAL (
    SELECT tsp2.points_through_match, tsp2.games_through_match
    FROM team_season_progress tsp2
    WHERE tsp2.team_id = st.team_id
      AND tsp2.season = pd.season
      AND tsp2.match_date < pd.match_date
    ORDER BY tsp2.match_date DESC
    LIMIT 1
) tsp ON true;

-- 4. Head-to-head: last 5 meetings between this specific pair of teams
-- (regardless of which one was home in those past meetings), strictly
-- before the target's date. LEAST/GREATEST makes the pairing symmetric —
-- "Arsenal vs Chelsea" and "Chelsea vs Arsenal" are the same fixture pair.
CREATE OR REPLACE VIEW head_to_head AS
SELECT
    pt.target_id,
    pt.target_type,
    hh.h2h_home_win_rate,
    hh.h2h_draw_rate,
    hh.h2h_away_win_rate,
    hh.h2h_matches_considered
FROM prediction_targets pt
LEFT JOIN LATERAL (
    SELECT
        AVG(CASE
            WHEN (pm.home_team_id = pt.home_team_id AND pm.result = 'H')
              OR (pm.away_team_id = pt.home_team_id AND pm.result = 'A')
            THEN 1.0 ELSE 0 END) AS h2h_home_win_rate,
        AVG(CASE WHEN pm.result = 'D' THEN 1.0 ELSE 0 END) AS h2h_draw_rate,
        AVG(CASE
            WHEN (pm.home_team_id = pt.away_team_id AND pm.result = 'H')
              OR (pm.away_team_id = pt.away_team_id AND pm.result = 'A')
            THEN 1.0 ELSE 0 END) AS h2h_away_win_rate,
        COUNT(*) AS h2h_matches_considered
    FROM (
        SELECT m2.home_team_id, m2.away_team_id, m2.result
        FROM matches m2
        WHERE m2.match_date < pt.match_date
          AND LEAST(m2.home_team_id, m2.away_team_id) = LEAST(pt.home_team_id, pt.away_team_id)
          AND GREATEST(m2.home_team_id, m2.away_team_id) = GREATEST(pt.home_team_id, pt.away_team_id)
        ORDER BY m2.match_date DESC
        LIMIT 5
    ) pm
) hh ON true;

-- 5. The final feature set: one row per match (training) or fixture
-- (serving), joining every view above onto prediction_targets.
CREATE OR REPLACE VIEW match_features AS
SELECT
    pt.target_id,
    pt.target_type,
    pt.season,
    pt.match_date,
    pt.home_team_id,
    pt.away_team_id,
    pt.result,

    home_form.rolling_points_5 AS home_rolling_points_5,
    home_form.rolling_goals_for_5 AS home_rolling_goals_for_5,
    home_form.rolling_goals_against_5 AS home_rolling_goals_against_5,
    home_form.rolling_shots_on_target_5 AS home_rolling_shots_on_target_5,
    home_form.rolling_corners_5 AS home_rolling_corners_5,
    home_form.rolling_fouls_5 AS home_rolling_fouls_5,
    home_form.rolling_cards_5 AS home_rolling_cards_5,

    away_form.rolling_points_5 AS away_rolling_points_5,
    away_form.rolling_goals_for_5 AS away_rolling_goals_for_5,
    away_form.rolling_goals_against_5 AS away_rolling_goals_against_5,
    away_form.rolling_shots_on_target_5 AS away_rolling_shots_on_target_5,
    away_form.rolling_corners_5 AS away_rolling_corners_5,
    away_form.rolling_fouls_5 AS away_rolling_fouls_5,
    away_form.rolling_cards_5 AS away_rolling_cards_5,

    home_standing.position AS home_position,
    away_standing.position AS away_position,
    (home_standing.position - away_standing.position) AS position_differential,
    home_standing.ppg AS home_ppg,
    away_standing.ppg AS away_ppg,
    (home_standing.ppg - away_standing.ppg) AS ppg_differential,

    home_venue.win_rate AS home_team_home_win_rate,
    away_venue.win_rate AS away_team_away_win_rate,

    h2h.h2h_home_win_rate,
    h2h.h2h_draw_rate,
    h2h.h2h_away_win_rate,
    h2h.h2h_matches_considered

FROM prediction_targets pt
LEFT JOIN LATERAL (
    SELECT trf.* FROM team_rolling_form trf
    WHERE trf.team_id = pt.home_team_id AND trf.match_date < pt.match_date
    ORDER BY trf.match_date DESC LIMIT 1
) home_form ON true
LEFT JOIN LATERAL (
    SELECT trf.* FROM team_rolling_form trf
    WHERE trf.team_id = pt.away_team_id AND trf.match_date < pt.match_date
    ORDER BY trf.match_date DESC LIMIT 1
) away_form ON true
LEFT JOIN team_standing_by_date home_standing
    ON home_standing.season = pt.season
   AND home_standing.as_of_date = pt.match_date
   AND home_standing.team_id = pt.home_team_id
LEFT JOIN team_standing_by_date away_standing
    ON away_standing.season = pt.season
   AND away_standing.as_of_date = pt.match_date
   AND away_standing.team_id = pt.away_team_id
LEFT JOIN LATERAL (
    SELECT tvr.win_rate FROM team_venue_win_rate tvr
    WHERE tvr.team_id = pt.home_team_id AND tvr.is_home = true
      AND tvr.match_date < pt.match_date
    ORDER BY tvr.match_date DESC LIMIT 1
) home_venue ON true
LEFT JOIN LATERAL (
    SELECT tvr.win_rate FROM team_venue_win_rate tvr
    WHERE tvr.team_id = pt.away_team_id AND tvr.is_home = false
      AND tvr.match_date < pt.match_date
    ORDER BY tvr.match_date DESC LIMIT 1
) away_venue ON true
LEFT JOIN head_to_head h2h
    ON h2h.target_id = pt.target_id AND h2h.target_type = pt.target_type;
