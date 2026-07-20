"""
FastAPI app: GET /health, GET /matches, GET /predict.

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

from api.db import close_pool, get_connection, get_db, init_pool
from api.routers import matches, predict

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


app = FastAPI(title="SoccerIQ", lifespan=lifespan)
app.include_router(matches.router)
app.include_router(predict.router)


@app.get("/health")
def health(conn=Depends(get_db)):
    """A real check, not a static OK — fails loudly if the database isn't
    reachable, since that's the one dependency this API actually has."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1;")
    return {"status": "ok"}
