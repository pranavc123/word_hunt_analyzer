"""Database engine + sessions. SQLite at $WH_DATA/wh.db (override with WH_DB_URL)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from . import models  # noqa: F401  (register tables)

ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))


def db_url() -> str:
    return os.environ.get("WH_DB_URL") or f"sqlite:///{data_dir() / 'wh.db'}"


@lru_cache(maxsize=8)
def _engine(url: str):
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(eng, "connect")
    def _pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")  # the API and the worker write concurrently
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return eng


def engine():
    return _engine(db_url())


def create_all() -> None:
    """For tests and first runs; production schema changes go through Alembic."""
    SQLModel.metadata.create_all(engine())


@contextmanager
def session() -> Iterator[Session]:
    with Session(engine(), expire_on_commit=False) as s:
        yield s
