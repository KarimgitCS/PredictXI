# Database migrations

Plain numbered SQL files in `migrations/`, applied in order by `migrate.py`.
No ORM or migration framework (Alembic, etc.) — unnecessary ceremony at this
project's scale, and one less tool to learn.

## Running migrations

```
python db/migrate.py
```

Requires `DATABASE_URL` to be set in `.env` (see `.env.example`). Safe to run
repeatedly — a `schema_migrations` table tracks which files have already been
applied, and anything already applied is skipped.

## Adding a new migration

Add a new file to `migrations/`, numbered one higher than the last
(`009_whatever.sql`), and run `python db/migrate.py` again. Filenames sort in
run order, so always zero-pad the numeric prefix.

## Editing an already-applied migration

`schema_migrations` tracks by filename only, not content — editing a file
that's already applied does nothing until its tracking row is removed:

```sql
DELETE FROM schema_migrations WHERE filename = '008_match_features_views.sql';
```

then re-run `python db/migrate.py`. This is a deliberate exception, not a
general pattern — it's what `008`'s placeholder was reserved for early on,
to be filled in with real `CREATE OR REPLACE VIEW` statements once the
feature-views work needed them, without renumbering every migration that
already existed.

## Current migrations

| File | Creates |
|---|---|
| `001_teams.sql` | `teams` |
| `002_team_aliases.sql` | `team_aliases` |
| `003_matches.sql` | `matches` (unified historical + current-season) |
| `004_standings_snapshot.sql` | `standings_snapshot` |
| `005_fixtures.sql` | `fixtures` |
| `006_models.sql` | `models` |
| `007_predictions.sql` | `predictions` |
| `008_match_features_views.sql` | `team_match_log`, `team_rolling_form`, `team_venue_win_rate`, `team_season_progress`, `prediction_targets`, `season_teams`, `head_to_head`, `match_features` |
| `009_team_crest_url.sql` | `teams.crest_url` |
