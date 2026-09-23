"""
FastAPI app: GET /health, GET /matches, GET /predict, GET /standings,
GET /result.
Also serves the frontend as static files at "/" — visit http://localhost:8000/
for the whole demo, not just the API.

Run locally:
    uvicorn api.main:app --reload

Run in Docker:
    docker compose up api
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.db import close_pool, get_connection, get_db, init_pool
from api.routers import matches, predict, standings

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

sys.path.insert(0, str(Path(__file__).parent.parent / "ml"))
sys.path.insert(0, str(Path(__file__).parent.parent / "etl"))
from fetch_live_data import refresh as refresh_live_data
from model_registry import load_model

load_dotenv()

# uvicorn's own logger — the only one configured to print INFO under `uvicorn`.
logger = logging.getLogger("uvicorn.error")

# How often the API pulls finished matches / fixtures / standings from
# football-data.org on its own. 0 disables it (the tests do, and so does a
# missing API key). The free tier allows 10 requests/minute and one refresh
# is 3 requests, so 30 minutes is far inside the limit.
DEFAULT_REFRESH_MINUTES = 30


async def live_refresh_loop(database_url: str, api_key: str, interval_seconds: float) -> None:
    """Runs one refresh immediately (catching up after the app was off),
    then again every interval. A failed run — API down, rate limited — is
    logged and retried next tick; it must never take the app down."""
    while True:
        try:
            counts = await asyncio.to_thread(refresh_live_data, database_url, api_key)
            logger.info("live refresh: %s", counts)
        except Exception:
            logger.exception("live refresh failed; will retry in %.0f min", interval_seconds / 60)
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT model_id, name, artifact_path FROM models WHERE is_active = true;"
            )
            row = cur.fetchone()

    if row is not None:
        model_id, name, artifact_path = row
        app.state.active_model = load_model(artifact_path)
        app.state.active_model_info = {"model_id": model_id, "name": name}
    else:
        app.state.active_model = None
        app.state.active_model_info = None

    refresh_task = None
    api_key = os.environ.get("FOOTBALL_DATA_ORG_API_KEY")
    minutes = float(os.environ.get("LIVE_REFRESH_MINUTES", DEFAULT_REFRESH_MINUTES))
    if api_key and minutes > 0:
        refresh_task = asyncio.create_task(
            live_refresh_loop(os.environ["DATABASE_URL"], api_key, minutes * 60)
        )

    yield

    if refresh_task is not None:
        refresh_task.cancel()
    close_pool()


app = FastAPI(title="PredictXI", lifespan=lifespan)

# Wide open — fine for a local-only portfolio demo with no auth or sensitive
# data; the frontend is plain static files served from whatever port/origin
# is convenient, not worth pinning down for this scope.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"],
)

app.include_router(matches.router)
app.include_router(predict.router)
app.include_router(standings.router)


@app.get("/health")
def health(conn=Depends(get_db)):
    """A real check, not a static OK — fails loudly if the database isn't
    reachable, since that's the one dependency this API actually has."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1;")
    return {"status": "ok"}


# Mounted last, at "/" — every API route above is registered first, so it's
# matched before falling through to this catch-all. Lets `docker compose up`
# alone serve the whole demo (API + UI) from one container on one port,
# rather than needing a second manual static-file server.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
