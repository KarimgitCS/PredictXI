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
from model_registry import load_model

load_dotenv()


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

    yield

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
