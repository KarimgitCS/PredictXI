"""
Team name reconciliation. football-data.co.uk and football-data.org spell
team names differently, and teams get promoted/relegated/renamed across
seasons — this module is the single place that maps every raw spelling seen
in either source to one canonical team.

The canonical `name` chosen here is just an internal display label — it does
not need to exactly match either source's own spelling, since each source's
raw string gets its own row in team_aliases pointing at the same team_id.
That's what makes it safe to not worry about matching football-data.org's
exact naming convention until Phase 3 actually talks to that API.

ALIAS_MAP['football-data.co.uk'] covers all 36 distinct HomeTeam/AwayTeam
spellings found across the 2010/11-2019/20 season CSVs (verified by scanning
every downloaded file — see data/raw/). Phase 3 adds a
ALIAS_MAP['football-data.org'] section once real API responses are in hand.
"""

ALIAS_MAP: dict[str, dict[str, str]] = {
    "football-data.co.uk": {
        "Arsenal": "Arsenal",
        "Aston Villa": "Aston Villa",
        "Birmingham": "Birmingham City",
        "Blackburn": "Blackburn Rovers",
        "Blackpool": "Blackpool",
        "Bolton": "Bolton Wanderers",
        "Bournemouth": "Bournemouth",
        "Brighton": "Brighton & Hove Albion",
        "Burnley": "Burnley",
        "Cardiff": "Cardiff City",
        "Chelsea": "Chelsea",
        "Crystal Palace": "Crystal Palace",
        "Everton": "Everton",
        "Fulham": "Fulham",
        "Huddersfield": "Huddersfield Town",
        "Hull": "Hull City",
        "Leicester": "Leicester City",
        "Liverpool": "Liverpool",
        "Man City": "Manchester City",
        "Man United": "Manchester United",
        "Middlesbrough": "Middlesbrough",
        "Newcastle": "Newcastle United",
        "Norwich": "Norwich City",
        "QPR": "Queens Park Rangers",
        "Reading": "Reading",
        "Sheffield United": "Sheffield United",
        "Southampton": "Southampton",
        "Stoke": "Stoke City",
        "Sunderland": "Sunderland",
        "Swansea": "Swansea City",
        "Tottenham": "Tottenham Hotspur",
        "Watford": "Watford",
        "West Brom": "West Bromwich Albion",
        "West Ham": "West Ham United",
        "Wigan": "Wigan Athletic",
        "Wolves": "Wolverhampton Wanderers",
    },
}


def resolve_team_id(cur, source: str, alias: str) -> int:
    """Return the team_id for a raw name from `source`, creating the team
    and/or alias row if this is the first time either has been seen.
    Idempotent — safe to call repeatedly with the same (source, alias).
    """
    cur.execute(
        "SELECT team_id FROM team_aliases WHERE source = %s AND alias = %s;",
        (source, alias),
    )
    row = cur.fetchone()
    if row is not None:
        return row[0]

    try:
        canonical_name = ALIAS_MAP[source][alias]
    except KeyError:
        raise ValueError(
            f"No canonical name mapping for source={source!r} alias={alias!r}. "
            f"Add it to ALIAS_MAP in etl/team_aliases.py before re-running."
        )

    cur.execute("SELECT team_id FROM teams WHERE name = %s;", (canonical_name,))
    row = cur.fetchone()
    if row is not None:
        team_id = row[0]
    else:
        cur.execute(
            "INSERT INTO teams (name) VALUES (%s) RETURNING team_id;",
            (canonical_name,),
        )
        team_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO team_aliases (source, alias, team_id) VALUES (%s, %s, %s);",
        (source, alias, team_id),
    )
    return team_id
