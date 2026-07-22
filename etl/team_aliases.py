"""
Team name reconciliation. football-data.co.uk and football-data.org spell
team names differently, and teams get promoted/relegated/renamed across
seasons — this module is the single place that maps every raw spelling seen
in either source to one canonical team.

The canonical `name` chosen here is just an internal display label — it does
not need to exactly match either source's own spelling, since each source's
raw string gets its own row in team_aliases pointing at the same team_id.

ALIAS_MAP['football-data.co.uk'] covers all 36 distinct HomeTeam/AwayTeam
spellings found across the 2010/11-2019/20 season CSVs (verified by scanning
every downloaded file — see data/raw/).

ALIAS_MAP['football-data.org'] covers the 20 teams in the current-season
standings table, pulled directly from a live API response (their `name`
field, e.g. "Arsenal FC") rather than guessed. Where a team already existed
in the historical set, it reuses that canonical name (e.g. "Arsenal FC" ->
"Arsenal") rather than introducing a second entry for the same club. Teams
new to this section (promoted since 2019/20, or otherwise not seen in the
historical CSVs) get a fresh canonical name here.
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
    "football-data.org": {
        "AFC Bournemouth": "Bournemouth",
        "Arsenal FC": "Arsenal",
        "Aston Villa FC": "Aston Villa",
        "Brentford FC": "Brentford",
        "Brighton & Hove Albion FC": "Brighton & Hove Albion",
        "Chelsea FC": "Chelsea",
        "Coventry City FC": "Coventry City",
        "Crystal Palace FC": "Crystal Palace",
        "Everton FC": "Everton",
        "Fulham FC": "Fulham",
        "Hull City AFC": "Hull City",
        "Ipswich Town FC": "Ipswich Town",
        "Leeds United FC": "Leeds United",
        "Liverpool FC": "Liverpool",
        "Manchester City FC": "Manchester City",
        "Manchester United FC": "Manchester United",
        "Newcastle United FC": "Newcastle United",
        "Nottingham Forest FC": "Nottingham Forest",
        "Sunderland AFC": "Sunderland",
        "Tottenham Hotspur FC": "Tottenham Hotspur",
    },
}


def resolve_team_id(cur, source: str, alias: str, crest_url: str | None = None) -> int:
    """Return the team_id for a raw name from `source`, creating the team
    and/or alias row if this is the first time either has been seen.
    Idempotent — safe to call repeatedly with the same (source, alias).

    crest_url is optional (only football-data.org responses include one) and
    only ever fills in a currently-NULL value — never overwrites, so a team
    already backfilled from a prior run is left alone.
    """
    cur.execute(
        "SELECT team_id FROM team_aliases WHERE source = %s AND alias = %s;",
        (source, alias),
    )
    row = cur.fetchone()
    if row is not None:
        team_id = row[0]
        _backfill_crest(cur, team_id, crest_url)
        return team_id

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
            "INSERT INTO teams (name, crest_url) VALUES (%s, %s) RETURNING team_id;",
            (canonical_name, crest_url),
        )
        team_id = cur.fetchone()[0]

    _backfill_crest(cur, team_id, crest_url)

    cur.execute(
        "INSERT INTO team_aliases (source, alias, team_id) VALUES (%s, %s, %s);",
        (source, alias, team_id),
    )
    return team_id


def _backfill_crest(cur, team_id: int, crest_url: str | None) -> None:
    if crest_url is None:
        return
    cur.execute(
        "UPDATE teams SET crest_url = %s WHERE team_id = %s AND crest_url IS NULL;",
        (crest_url, team_id),
    )
