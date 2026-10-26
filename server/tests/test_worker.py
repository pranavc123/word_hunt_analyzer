"""S3.T3: uploaded fixture records → processed boards / matched all-words captures."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

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
    worker.huey.immediate = True  # run tasks inline
    with TestClient(app) as c:
        yield c
    worker.huey.immediate = False


def records(name):
    return json.loads((FIX / "expected" / f"{name}.json").read_text())["records"]


def post_board(client, name):
    rec = next(r for r in records(name) if r["kind"] == "board")
    phone = LABELS[name]["phone_crops"]
    parts = [("record", ("record.json", json.dumps(rec), "application/json"))]
    parts += [
        ("files", (v["name"], (FIX / v["file"]).read_bytes(), "image/jpeg")) for v in phone.values()
    ]
    assert client.post("/v1/boards", files=parts, headers=AUTH).status_code == 200
    return rec


def post_allwords(client, name):
    rec = next(r for r in records(name) if r["kind"] == "all_words")
    files = {Path(f).name.split("_allwords_", 1)[1]: f for f in LABELS[name]["list_crops"]}
    rec = dict(
        rec,
        frames=[n for n in rec["frames"] if n in files],
        shifts_px=[o for n, o in zip(rec["frames"], rec["shifts_px"], strict=True) if n in files],
        gap_flags=[g for n, g in zip(rec["frames"], rec["gap_flags"], strict=True) if n in files],
    )
    parts = [("record", ("record.json", json.dumps(rec), "application/json"))]
    parts += [("files", (n, (FIX / f).read_bytes(), "image/jpeg")) for n, f in files.items()]
    assert client.post("/v1/allwords", files=parts, headers=AUTH).status_code == 200
    return rec


def test_played_board_is_verified_from_phone_crops(client):
    from app import db
    from app.models import AttemptRow, Board, BoardWord

    name = "session1_b00_played"
    rec = post_board(client, name)
    truth = LABELS[name]["boards"][0]
    with db.session() as s:
        b = s.get(Board, rec["board_id"])
        assert b.letters == truth["letters"]
        assert (b.final_word_count, b.final_score) == (truth["end_words"], truth["end_score"])
        assert b.review_status == "verified" and b.reconciled
        accepted = s.exec(
            select(AttemptRow).where(AttemptRow.board_id == b.id, AttemptRow.result == "valid_new")
        ).all()
        assert len(accepted) == truth["end_words"] and all(a.word for a in accepted)
        found = s.exec(select(BoardWord).where(BoardWord.board_id == b.id, BoardWord.found)).all()
        assert len(found) == truth["end_words"]
    latest = client.get("/v1/sessions/latest", headers=AUTH).json()
    assert latest["verified_count"] == 1


def test_allwords_uploaded_first_is_matched_when_its_board_arrives(client):
    from app import db
    from app.models import AllWordsCapture, Board

    name = "allwords1_b03_played_allwords"
    aw = post_allwords(client, name)
    with db.session() as s:
        assert s.get(AllWordsCapture, aw["record_id"]).match_state == "unmatched"
    rec = post_board(client, name)
    with db.session() as s:
        cap = s.get(AllWordsCapture, aw["record_id"])
        assert cap.match_state == "matched" and cap.board_id == rec["board_id"]
        b = s.get(Board, rec["board_id"])
        assert b.all_words_id == aw["record_id"]
        assert b.review_status in ("verified", "needs_review")
