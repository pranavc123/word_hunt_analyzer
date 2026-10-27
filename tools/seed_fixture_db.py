"""Seed a development database from the committed fixtures, through the real ingest + worker path.

uv run python tools/seed_fixture_db.py
→ $WH_DATA/dev.db (2 sessions, 12 boards) with images under $WH_DATA/dev/.
Serve it:  WH_DATA=$WH_DATA/dev WH_DB_URL=sqlite:///$WH_DATA/dev.db WH_TOKEN=dev \
           uv run uvicorn app.main:app --app-dir server --port 8001
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
REAL = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
DEV_DB = REAL / "dev.db"
DEV_DATA = REAL / "dev"

# must be set before the app modules are imported (the worker opens its queue on import)
os.environ.update(WH_DATA=str(DEV_DATA), WH_DB_URL=f"sqlite:///{DEV_DB}", WH_TOKEN="dev")
sys.path.insert(0, str(ROOT / "server"))

from fastapi.testclient import TestClient  # noqa: E402

LABELS = json.loads((FIX / "expected/labels.json").read_text())
AUTH = {"Authorization": "Bearer dev"}

# (fixture segment, which images to send, how many extra clones) per session
SESSIONS = {
    "session1": [
        ("session1_b00_played", "phone", 2),
        ("session1_b01_skipped", None, 0),
        ("session1_b02_played", "board", 0),
        ("session1_b12_skipped", None, 0),
    ],
    "allwords1": [
        ("allwords1_b00_played_allwords", "board", 2),
        ("allwords1_b03_played_allwords", "phone", 2),
    ],
}


def board_record(name: str) -> dict:
    recs = json.loads((FIX / f"expected/{name}.json").read_text())["records"]
    return next(r for r in recs if r["kind"] == "board")


def images_for(name: str, kind: str | None, rec: dict) -> dict[str, bytes]:
    lab = LABELS[name]
    if kind == "phone":
        return {v["name"]: (FIX / v["file"]).read_bytes() for v in lab["phone_crops"].values()}
    if kind == "board":
        return {rec["board_image"]: (FIX / lab["board_crop"]["file"]).read_bytes()}
    return {}


def post(client: TestClient, path: str, rec: dict, files: dict[str, bytes]) -> None:
    parts = [("record", ("record.json", json.dumps(rec), "application/json"))]
    parts += [("files", (n, data, "image/jpeg")) for n, data in files.items()]
    r = client.post(path, files=parts, headers=AUTH)
    r.raise_for_status()


def main() -> int:
    for f in (DEV_DB, DEV_DB.with_suffix(".db-wal"), DEV_DB.with_suffix(".db-shm")):
        f.unlink(missing_ok=True)
    from app import worker
    from app.main import app

    worker.huey.immediate = True
    with TestClient(app) as client:
        for k, (sess_name, entries) in enumerate(SESSIONS.items()):
            sid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"wordhunt-dev-{sess_name}"))
            start = datetime(2026, 10, 25 + k, 20, 0)
            seq = 0
            for name, kind, clones in entries:
                base = board_record(name)
                for _ in range(clones + 1):
                    rec = dict(
                        base,
                        session_id=sid,
                        seq=seq,
                        board_id=str(uuid.uuid5(uuid.UUID(sid), f"board-{seq}")),
                        opened_at=(start + timedelta(seconds=95 * seq)).isoformat() + "Z",
                    )
                    post(client, "/v1/boards", rec, images_for(name, kind, base))
                    seq += 1
            for name, _, _ in entries:  # the all-words capture that followed a board
                lab = LABELS[name]
                if "list_crops" not in lab:
                    continue
                recs = json.loads((FIX / f"expected/{name}.json").read_text())["records"]
                aw = next(r for r in recs if r["kind"] == "all_words")
                files = {Path(f).name.split("_allwords_", 1)[1]: f for f in lab["list_crops"]}
                keep = [i for i, n in enumerate(aw["frames"]) if n in files]
                aw = dict(
                    aw,
                    session_id=sid,
                    record_id=str(uuid.uuid5(uuid.UUID(sid), "allwords-0")),
                    frames=[aw["frames"][i] for i in keep],
                    shifts_px=[aw["shifts_px"][i] for i in keep],
                    gap_flags=[aw["gap_flags"][i] for i in keep],
                )
                post(
                    client,
                    "/v1/allwords",
                    aw,
                    {n: (FIX / f).read_bytes() for n, f in files.items()},
                )
        sessions = client.get("/v1/sessions", headers=AUTH).json()
    for s in sessions:
        print(
            f"session {s['id'][:8]}: {s['board_count']} boards, {s['played_count']} played, "
            f"{s['verified_count']} verified, {s['needs_letter_fix']} need letters, "
            f"{s['needs_review']} need review"
        )
    print(f"wrote {DEV_DB} ({len(sessions)} sessions)")
    return 0 if len(sessions) == 2 else 1


if __name__ == "__main__":
    sys.exit(main())
