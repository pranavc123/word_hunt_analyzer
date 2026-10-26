import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlmodel import select

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'wh.db'}"
    monkeypatch.setenv("WH_DB_URL", url)
    from app import db as dbm

    dbm._engine.cache_clear()
    return dbm


def test_alembic_baseline_creates_plan_tables(db, tmp_path):
    env = {"WH_DB_URL": f"sqlite:///{tmp_path / 'wh.db'}", "PATH": "/usr/bin:/bin"}
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    tables = set(inspect(db.engine()).get_table_names())
    expected = {
        "sessions",
        "calibrations",
        "boards",
        "all_words_captures",
        "attempts",
        "board_words",
        "board_features",
        "words",
        "dictionary_versions",
        "insights",
    }
    assert expected <= tables


def test_roundtrip_board_with_json(db):
    from app.models import AttemptRow, Board, Session

    db.create_all()
    now = datetime(2026, 10, 26, tzinfo=UTC)
    with db.session() as s:
        s.add(Session(id="s1", started_at=now, board_count=1))
        s.flush()
        s.add(
            Board(
                id="b1",
                session_id="s1",
                seq=0,
                opened_at=now,
                view_ms=80000,
                status="played",
                letters="LCMEORSIETRATDIM",
                record={"kind": "board"},
                end_visible_words=["master"],
            )
        )
        s.flush()  # parents first: no ORM relationships, so inserts are not FK-ordered
        s.add(
            AttemptRow(
                board_id="b1",
                seq=0,
                t_start_ms=1,
                t_end_ms=2,
                tiles_seen=[0, 1, 2],
                result="valid_new",
                word="lcm",
                points=100,
            )
        )
        s.commit()
    with db.session() as s:
        b = s.get(Board, "b1")
        assert b.record == {"kind": "board"} and b.end_visible_words == ["master"]
        a = s.exec(select(AttemptRow).where(AttemptRow.board_id == "b1")).one()
        assert a.tiles_seen == [0, 1, 2]
