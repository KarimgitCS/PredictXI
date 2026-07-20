"""
Database connection pooling for the API. A small psycopg2 pool, not a
fresh connection per request — the database is reached over the network
(hosted Neon/Supabase), so reusing connections avoids repeating a TCP+SSL
handshake on every request.
"""

import os
from contextlib import contextmanager

from psycopg2 import pool

_pool: pool.SimpleConnectionPool | None = None


def init_pool() -> None:
    global _pool
    _pool = pool.SimpleConnectionPool(1, 5, dsn=os.environ["DATABASE_URL"])


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def get_connection():
    """Commits on success, rolls back on any exception, always returns the
    connection to the pool. Usable both as a FastAPI dependency (below) and
    directly at app startup, before any request-scoped dependency exists."""
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def get_db():
    with get_connection() as conn:
        yield conn
