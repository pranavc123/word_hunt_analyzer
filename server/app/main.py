"""FastAPI app. S0: health + device diagnostics sink."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.1.0"

app = FastAPI(title="Word Hunt Analyzer", version=VERSION)


def data_dir() -> Path:
    return Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))


def require_token(authorization: str | None = Header(default=None)) -> None:
    token = os.environ.get("WH_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="bad token")


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
    out = data_dir() / "diag.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        f.write(json.dumps(payload, separators=(",", ":")) + "\n")
    return {"ok": True}
