"""
Loads football-data.co.uk Premier League season CSVs (already downloaded into
data/raw/, see data/raw/README.md) into the unified `matches` table.

Usage:
    python etl/load_historical_csv.py

Safe to re-run: matches are upserted on (season, match_date, home_team_id,
away_team_id), so running this twice does not create duplicate rows.
"""

import math
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from team_aliases import resolve_team_id

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"

# Two different "source" vocabularies, easy to conflate:
# - ALIAS_SOURCE identifies which naming convention a raw team name follows,
#   for team_aliases lookups (team_aliases.source CHECK constraint).
# - MATCH_SOURCE identifies which pipeline populated a matches row
#   (matches.source CHECK constraint).
ALIAS_SOURCE = "football-data.co.uk"
MATCH_SOURCE = "historical_csv"

# (filename, season label) — season label is assigned explicitly rather than
# inferred from the data, since that's simpler and impossible to get wrong.
SEASON_FILES = [
    ("E0_1011.csv", "2010-2011"),
    ("E0_1112.csv", "2011-2012"),
    ("E0_1213.csv", "2012-2013"),
    ("E0_1314.csv", "2013-2014"),
    ("E0_1415.csv", "2014-2015"),
    ("E0_1516.csv", "2015-2016"),
    ("E0_1617.csv", "2016-2017"),
    ("E0_1718.csv", "2017-2018"),
    ("E0_1819.csv", "2018-2019"),
    ("E0_1920.csv", "2019-2020"),
]

# CSV column -> matches column. Betting-odds columns (the large majority of
# each file) are simply never selected.
COLUMNS = {
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "FTHG": "home_goals",
    "FTAG": "away_goals",
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_shots_on_target",
    "AST": "away_shots_on_target",
    "HC": "home_corners",
    "AC": "away_corners",
    "HF": "home_fouls",
    "AF": "away_fouls",
    "HY": "home_yellow",
    "AY": "away_yellow",
    "HR": "home_red",
    "AR": "away_red",
}

INSERT_SQL = """
    INSERT INTO matches (
        season, match_date, home_team_id, away_team_id,
        home_goals, away_goals,
        home_shots, away_shots, home_shots_on_target, away_shots_on_target,
        home_corners, away_corners, home_fouls, away_fouls,
        home_yellow, away_yellow, home_red, away_red,
        source
    )
    VALUES (
        %(season)s, %(match_date)s, %(home_team_id)s, %(away_team_id)s,
        %(home_goals)s, %(away_goals)s,
        %(home_shots)s, %(away_shots)s, %(home_shots_on_target)s, %(away_shots_on_target)s,
        %(home_corners)s, %(away_corners)s, %(home_fouls)s, %(away_fouls)s,
        %(home_yellow)s, %(away_yellow)s, %(home_red)s, %(away_red)s,
        %(source)s
    )
    ON CONFLICT (season, match_date, home_team_id, away_team_id) DO NOTHING;
"""


def clean(value):
    """pandas represents a blank CSV cell as NaN (float); psycopg2 needs
    None for a SQL NULL, not NaN."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def load_season(cur, filename: str, season: str) -> tuple[int, int]:
    path = RAW_DIR / filename
    df = pd.read_csv(path, usecols=list(COLUMNS.keys()) + ["Date"])
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True).dt.date

    inserted = 0
    for _, row in df.iterrows():
        home_team_id = resolve_team_id(cur, ALIAS_SOURCE, row["HomeTeam"])
        away_team_id = resolve_team_id(cur, ALIAS_SOURCE, row["AwayTeam"])

        params = {"season": season, "match_date": row["Date"], "source": MATCH_SOURCE,
                  "home_team_id": home_team_id, "away_team_id": away_team_id}
        for csv_col, db_col in COLUMNS.items():
            if csv_col in ("HomeTeam", "AwayTeam"):
                continue
            params[db_col] = clean(row[csv_col])

        cur.execute(INSERT_SQL, params)
        inserted += cur.rowcount

    return len(df), inserted


def main() -> None:
    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set — check your .env file.")

    conn = psycopg2.connect(database_url)
    total_rows, total_inserted = 0, 0
    try:
        for filename, season in SEASON_FILES:
            path = RAW_DIR / filename
            if not path.exists():
                sys.exit(f"Missing {path} — see data/raw/README.md to fetch it.")

            with conn:
                with conn.cursor() as cur:
                    rows, inserted = load_season(cur, filename, season)
            total_rows += rows
            total_inserted += inserted
            print(f"{season}: {rows} rows in CSV, {inserted} newly inserted")
    finally:
        conn.close()

    print(f"\nTotal: {total_rows} rows across {len(SEASON_FILES)} seasons, "
          f"{total_inserted} newly inserted this run.")


if __name__ == "__main__":
    main()
