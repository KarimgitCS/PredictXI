"""
Database connection pooling for the API. A small psycopg2 pool, not a
fresh connection per request — the database is reached over the network
(hosted Neon/Supabase), so reusing connections avoids repeating a TCP+SSL
handshake on every request.

Uses ThreadedConnectionPool, not SimpleConnectionPool — FastAPI runs sync
`def` route handlers in a worker thread pool (via anyio.to_thread), so
concurrent requests mean concurrent getconn()/putconn() calls.
SimpleConnectionPool isn't safe under that; its internal free-list
bookkeeping can corrupt under concurrent access, which surfaced as
intermittent "server closed the connection unexpectedly" errors during
manual testing — not a flaky network, a real concurrency bug.
"""

import os
from contextlib import contextmanager

from psycopg2 import pool

_pool: pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    # maxconn=20: the frontend's fixture list fires one /predict call per
    # fixture in parallel (Promise.all), so a single page load can produce
    # ~12 concurrent requests — maxconn=5 (the original value) hit
    # "connection pool exhausted" under exactly that load during manual
    # testing, not just synthetic stress.
    _pool = pool.ThreadedConnectionPool(1, 20, dsn=os.environ["DATABASE_URL"])


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
