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
import time
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool

_pool: pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    # maxconn=20: the frontend's fixture list fires one /predict call per
    # fixture in parallel (Promise.all), so a single page load can produce
    # ~12 concurrent requests — maxconn=5 (the original value) hit
    # "connection pool exhausted" under exactly that load during manual
    # testing, not just synthetic stress.
    #
    # TCP keepalives: hosted Postgres (and the poolers in front of it) drop
    # connections that sit silent for a while; keepalive probes keep an idle
    # pooled connection from being closed behind our back.
    _pool = pool.ThreadedConnectionPool(
        1, 20, dsn=os.environ["DATABASE_URL"],
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
    )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


# A pooled connection idle longer than this gets a liveness check before it
# is handed out. Busy connections skip the check (it costs a network round
# trip to the hosted DB); only ones that sat long enough to be dropped pay it.
PING_AFTER_IDLE_SECONDS = 30
_last_used: dict[int, float] = {}


def _checkout() -> psycopg2.extensions.connection:
    """A live connection from the pool. A connection the server closed while
    it sat idle would otherwise be handed to a request and fail it with
    "server closed the connection unexpectedly" — so a long-idle one is
    pinged first and, if dead, discarded (the pool then opens a fresh one)."""
    while True:
        conn = _pool.getconn()
        idle_for = time.monotonic() - _last_used.get(id(conn), 0.0)
        if not conn.closed and idle_for < PING_AFTER_IDLE_SECONDS:
            return conn
        try:
            if conn.closed:
                raise psycopg2.OperationalError("connection already closed")
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
            conn.rollback()
            return conn
        except psycopg2.Error:
            _last_used.pop(id(conn), None)
            _pool.putconn(conn, close=True)


@contextmanager
def get_connection():
    """Commits on success, rolls back on any exception, always returns the
    connection to the pool. Usable both as a FastAPI dependency (below) and
    directly at app startup, before any request-scoped dependency exists."""
    conn = _checkout()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _last_used[id(conn)] = time.monotonic()
        _pool.putconn(conn)


def get_db():
    with get_connection() as conn:
        yield conn
