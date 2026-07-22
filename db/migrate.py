"""
Tiny migration runner — no Alembic, no ORM. Applies every *.sql file in
db/migrations/, in filename order, exactly once each.

Usage:
    python db/migrate.py

Relies on filenames sorting in the order they should run (001_, 002_, ...),
so always zero-pad the numeric prefix when adding a new migration.
"""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def already_applied(cur) -> set[str]:
    cur.execute("SELECT filename FROM schema_migrations;")
    return {row[0] for row in cur.fetchall()}


def is_effectively_empty(sql: str) -> bool:
    """True if a file is only comments/whitespace (e.g. a reserved-number
    placeholder, like 008_match_features_views.sql before it was filled in)."""
    lines = (line.strip() for line in sql.splitlines())
    return not any(line and not line.startswith("--") for line in lines)


def main() -> None:
    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("DATABASE_URL is not set — check your .env file.")

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        sys.exit(f"No .sql files found in {MIGRATIONS_DIR}")

    conn = psycopg2.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_MIGRATIONS_TABLE)

            with conn.cursor() as cur:
                applied = already_applied(cur)

        for path in migration_files:
            if path.name in applied:
                print(f"skip    {path.name} (already applied)")
                continue

            sql = path.read_text()
            with conn:
                with conn.cursor() as cur:
                    if not is_effectively_empty(sql):
                        cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s);",
                        (path.name,),
                    )
            print(f"applied {path.name}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
