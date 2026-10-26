import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / "fixtures/expected"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WH_DATA", str(tmp_path))
    monkeypatch.setenv("WH_DB_URL", f"sqlite:///{tmp_path / 'wh.db'}")
    monkeypatch.setenv("WH_TOKEN", "secret")
    from app import api_ingest, db
    from app.main import app

    db._engine.cache_clear()
    stored: list[str] = []
    monkeypatch.setattr(api_ingest, "on_board_stored", [stored.append])
    monkeypatch.setattr(api_ingest, "on_allwords_stored", [stored.append])
    with TestClient(app) as c:
        c.stored = stored
        c.tmp = tmp_path
        yield c


AUTH = {"Authorization": "Bearer secret"}


def fixture_records(name):
    return json.loads((EXPECTED / f"{name}.json").read_text())["records"]


def post(client, path, rec, files):
    parts = [("record", ("record.json", json.dumps(rec), "application/json"))]
    parts += [("files", (n, data, "image/jpeg")) for n, data in files.items()]
    return client.post(path, files=parts, headers=AUTH)


def test_board_stored_once_with_images(client):
    rec = fixture_records("session1_b00_played")[0]
    files = {rec["board_image"]: b"B", rec["end_banner_image"]: b"E", rec["end_list_image"]: b"L"}
    r1 = post(client, "/v1/boards", rec, files)
    r2 = post(client, "/v1/boards", rec, files)
    assert r1.status_code == 200 and r1.json()["duplicate"] is False
    assert r2.status_code == 200 and r2.json()["duplicate"] is True
    assert client.stored == [rec["board_id"]]
    folder = client.tmp / "images" / rec["session_id"] / rec["board_id"]
    assert (folder / rec["board_image"]).read_bytes() == b"B"
    latest = client.get("/v1/sessions/latest", headers=AUTH).json()
    assert latest["board_count"] == 1 and latest["played_count"] == 1 and latest["pending"] == 1


def test_auth_validation_and_unexpected_files(client):
    rec = fixture_records("session1_b01_skipped")[0]
    parts = [("record", ("record.json", json.dumps(rec), "application/json"))]
    assert client.post("/v1/boards", files=parts).status_code == 401
    bad = dict(rec, status="won")
    assert post(client, "/v1/boards", bad, {}).status_code == 422
    assert post(client, "/v1/boards", rec, {"../../evil.jpg": b"x"}).status_code == 422
    assert post(client, "/v1/allwords", rec, {}).status_code == 422  # a board sent to /allwords
    assert client.get("/v1/sessions/latest", headers=AUTH).status_code == 404


def test_allwords_stored_once(client):
    recs = fixture_records("allwords1_b03_played_allwords")
    aw = next(r for r in recs if r["kind"] == "all_words")
    files = {n: b"J" for n in aw["frames"]}
    assert post(client, "/v1/allwords", aw, files).json()["duplicate"] is False
    assert post(client, "/v1/allwords", aw, files).json()["duplicate"] is True
    assert client.stored == [aw["record_id"]]
    folder = client.tmp / "images" / aw["session_id"] / f"allwords_{aw['record_id']}"
    assert sorted(p.name for p in folder.iterdir()) == sorted(aw["frames"])


def test_debug_frames_are_accepted(client):
    rec = fixture_records("session1_b12_skipped")[0]
    r = post(client, "/v1/boards", rec, {rec["board_image"]: b"B", "debug_123.jpg": b"D"})
    assert r.status_code == 200 and "debug_123.jpg" in r.json()["files"]
