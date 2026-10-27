"""S4.T2: read API over boards processed by the real worker."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures"
LABELS = json.loads((FIX / "expected/labels.json").read_text())
AUTH = {"Authorization": "Bearer secret"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WH_DATA", str(tmp_path))
    monkeypatch.setenv("WH_DB_URL", f"sqlite:///{tmp_path / 'wh.db'}")
    monkeypatch.setenv("WH_TOKEN", "secret")
    from app import db, worker
    from app.main import app

    db._engine.cache_clear()
    worker.huey.immediate = True
    with TestClient(app) as c:
        yield c
    worker.huey.immediate = False


def upload(client, name, with_images=True, seq=None):
    rec = next(
        r
        for r in json.loads((FIX / f"expected/{name}.json").read_text())["records"]
        if r["kind"] == "board"
    )
    if seq is not None:  # each fixture segment numbers its first board 0: give it a slot
        import uuid

        rec = dict(
            rec, seq=seq, board_id=str(uuid.uuid5(uuid.UUID(rec["session_id"]), f"board-{seq}"))
        )
    parts = [("record", ("record.json", json.dumps(rec), "application/json"))]
    if with_images:
        for v in LABELS[name]["phone_crops"].values():
            parts.append(("files", (v["name"], (FIX / v["file"]).read_bytes(), "image/jpeg")))
    assert client.post("/v1/boards", files=parts, headers=AUTH).status_code == 200
    return rec


def test_sessions_summary_and_board_detail(client):
    played = upload(client, "session1_b00_played")
    skipped = upload(client, "session1_b01_skipped", with_images=False, seq=1)
    sessions = client.get("/v1/sessions", headers=AUTH).json()
    assert len(sessions) == 1
    s = client.get(f"/v1/sessions/{sessions[0]['id']}", headers=AUTH).json()
    assert s["board_count"] == 2 and s["played_count"] == 1 and s["keep_rate"] == 0.5
    assert s["verified_count"] == 1 and s["needs_letter_fix"] == 0  # a 0.8 s skip is a glimpse
    assert s["best_board"]["id"] == played["board_id"] and s["biggest_miss"]["points"] > 0
    assert [b["seq"] for b in s["boards"]] == [0, 1]

    b = client.get(f"/v1/boards/{played['board_id']}", headers=AUTH).json()
    truth = LABELS["session1_b00_played"]["boards"][0]
    assert b["letters"] == truth["letters"] and b["review_status"] == "verified"
    assert sum(w["found"] for w in b["words"]) == truth["end_words"]
    assert b["max_points"] > b["final_score"] and b["next_id"] == skipped["board_id"]
    accepted = [a for a in b["attempts"] if a["result"] == "valid_new"]
    assert len(accepted) == truth["end_words"] and all(a["path"] for a in accepted)
    img = client.get(b["images"]["board"], headers=AUTH)
    assert img.status_code == 200 and img.content[:2] == b"\xff\xd8"


def test_letter_fix_resolves_and_confirms(client):
    rec = upload(client, "session1_b12_skipped", with_images=False)
    b = client.get(f"/v1/boards/{rec['board_id']}", headers=AUTH).json()
    assert b["review_status"] == "needs_letter_fix" and b["letters"] is None
    letters = LABELS["session1_b12_skipped"]["boards"][0]["letters"]
    assert (
        client.patch(
            f"/v1/boards/{rec['board_id']}/letters", json={"letters": "abc"}, headers=AUTH
        ).status_code
        == 422
    )
    r = client.patch(
        f"/v1/boards/{rec['board_id']}/letters", json={"letters": letters.lower()}, headers=AUTH
    )
    assert r.status_code == 200
    fixed = r.json()
    assert fixed["letters"] == letters and fixed["letters_confirmed"]
    assert fixed["review_status"] == "skipped" and len(fixed["words"]) > 50


def test_auth_and_image_paths(client):
    assert client.get("/v1/sessions").status_code == 401
    assert client.get("/v1/images/../wh.db", headers=AUTH).status_code == 404
    assert client.get("/v1/boards/nope", headers=AUTH).status_code == 404
