"""FastAPI app: health, device diagnostics (S0), ingest + sessions (S3)."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from . import api_ingest, db, worker  # noqa: F401  (worker registers its ingest hooks)
from .api_ingest import require_token

VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.create_all()  # creates missing tables; schema changes go through Alembic
    yield


app = FastAPI(title="Word Hunt Analyzer", version=VERSION, lifespan=lifespan)
app.include_router(api_ingest.router)


class Health(BaseModel):
    ok: bool
    version: str


@app.get("/v1/health")
def health() -> Health:
    return Health(ok=True, version=VERSION)


@app.post("/diag", dependencies=[Depends(require_token)])
async def diag(request: Request) -> dict:
    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="body must be JSON") from e
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    payload["received_at"] = datetime.now(UTC).isoformat()
    out = db.data_dir() / "diag.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        f.write(json.dumps(payload, separators=(",", ":")) + "\n")
    return {"ok": True}
