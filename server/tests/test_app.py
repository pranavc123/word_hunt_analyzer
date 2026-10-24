import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/v1/health").json()["ok"] is True


def test_diag_appends(tmp_path, monkeypatch):
    monkeypatch.setenv("WH_DATA", str(tmp_path))
    monkeypatch.setenv("WH_TOKEN", "secret")
    body = {"fps_processed": 29.5, "frames_dropped": 3, "mem_mb": 21.4, "app_group_available": 0}
    assert client.post("/diag", json=body).status_code == 401
    hdr = {"Authorization": "Bearer secret"}
    assert client.post("/diag", json=body, headers=hdr).status_code == 200
    assert client.post("/diag", json=[1], headers=hdr).status_code == 400
    lines = (tmp_path / "diag.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["mem_mb"] == 21.4 and "received_at" in rec
