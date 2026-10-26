"""Ingest API (S3.T2): records + crops from the phone (contract in docs/decisions.md, S2.T4)."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import ValidationError
from sqlmodel import func, select

from whcore.schema import AllWordsRecord, BoardRecord, parse_record

from . import db
from .models import AllWordsCapture, Board, Session

router = APIRouter()

# the worker registers itself here (app/worker.py); tests can swap in a recorder
on_board_stored: list[Callable[[str], None]] = []
on_allwords_stored: list[Callable[[str], None]] = []


def require_token(authorization: str | None = Header(default=None)) -> None:
    token = os.environ.get("WH_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="bad token")


def _parse(raw: bytes, kind: type):
    try:
        rec = parse_record(raw)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"invalid record: {e.errors()[:3]}") from e
    if not isinstance(rec, kind):
        raise HTTPException(status_code=422, detail=f"expected a {kind.__name__}")
    return rec


async def _save_files(files: list[UploadFile], allowed: set[str], folder: Path) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        name = Path(f.filename or "").name
        debug = name.startswith("debug_") and name.endswith(".jpg")  # WH_DEBUG frames (S3.T5)
        if name not in allowed and not debug:
            raise HTTPException(status_code=422, detail=f"unexpected file {name!r}")
        (folder / name).write_bytes(await f.read())
        saved.append(name)
    return saved


def _touch_session(
    s, session_id: str, at: datetime, device: str = "", app_version: str = "", calibration: str = ""
) -> None:
    sess = s.get(Session, session_id)
    if sess is None:
        sess = Session(
            id=session_id,
            started_at=at,
            device=device,
            app_version=app_version,
            calibration_id=calibration,
        )
        s.add(sess)
        s.flush()
    elif at < _aware(sess.started_at):
        sess.started_at = at
    if device:
        sess.device = device
    if app_version:
        sess.app_version = app_version


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@router.post("/v1/boards", dependencies=[Depends(require_token)])
async def post_board(
    record: UploadFile = File(...), files: list[UploadFile] = File(default=[])
) -> dict:
    rec: BoardRecord = _parse(await record.read(), BoardRecord)
    bid, sid = str(rec.board_id), str(rec.session_id)
    with db.session() as s:
        if s.get(Board, bid) is not None:
            return {"ok": True, "duplicate": True, "board_id": bid}
    refs = {r for r in (rec.board_image, rec.end_banner_image, rec.end_list_image) if r}
    folder = db.data_dir() / "images" / sid / bid
    saved = await _save_files(files, refs, folder)
    rel = lambda name: str((folder / name).relative_to(db.data_dir())) if name in saved else None  # noqa: E731
    with db.session() as s:
        _touch_session(s, sid, rec.opened_at, rec.device, rec.app_version, rec.calibration_version)
        s.add(
            Board(
                id=bid,
                session_id=sid,
                seq=rec.seq,
                opened_at=rec.opened_at,
                view_ms=rec.view_ms,
                status=rec.status,
                image_path=rel(rec.board_image),
                end_banner_path=rel(rec.end_banner_image) if rec.end_banner_image else None,
                end_list_path=rel(rec.end_list_image) if rec.end_list_image else None,
                review_status="pending" if rec.status == "played" else "skipped",
                all_words_status="pending" if rec.status == "played" else "none",
                record=rec.model_dump(mode="json", by_alias=True),
                received_at=datetime.now(UTC),
            )
        )
        s.flush()
        sess = s.get(Session, sid)
        sess.board_count = s.exec(select(func.count()).where(Board.session_id == sid)).one()
        s.commit()
    for hook in on_board_stored:
        hook(bid)
    return {"ok": True, "duplicate": False, "board_id": bid, "files": saved}


@router.post("/v1/allwords", dependencies=[Depends(require_token)])
async def post_allwords(
    record: UploadFile = File(...), files: list[UploadFile] = File(default=[])
) -> dict:
    rec: AllWordsRecord = _parse(await record.read(), AllWordsRecord)
    rid, sid = str(rec.record_id), str(rec.session_id)
    with db.session() as s:
        if s.get(AllWordsCapture, rid) is not None:
            return {"ok": True, "duplicate": True, "record_id": rid}
    folder = db.data_dir() / "images" / sid / f"allwords_{rid}"
    saved = await _save_files(files, set(rec.frames), folder)
    with db.session() as s:
        _touch_session(s, sid, rec.captured_at)
        s.add(
            AllWordsCapture(
                id=rid,
                session_id=sid,
                captured_at=rec.captured_at,
                frames_path=str(folder.relative_to(db.data_dir())),
                record=rec.model_dump(mode="json", by_alias=True),
                received_at=datetime.now(UTC),
            )
        )
        s.commit()
    for hook in on_allwords_stored:
        hook(rid)
    return {"ok": True, "duplicate": False, "record_id": rid, "files": saved}


@router.get("/v1/sessions/latest", dependencies=[Depends(require_token)])
def latest_session() -> dict:
    with db.session() as s:
        sess = s.exec(select(Session).order_by(Session.started_at.desc())).first()
        if sess is None:
            raise HTTPException(status_code=404, detail="no sessions yet")
        boards = s.exec(select(Board).where(Board.session_id == sess.id)).all()
    played = [b for b in boards if b.status == "played"]
    return {
        "id": sess.id,
        "started_at": _aware(sess.started_at).isoformat(),
        "board_count": len(boards),
        "played_count": len(played),
        "verified_count": sum(b.review_status == "verified" for b in played),
        "needs_letter_fix": sum(b.review_status == "needs_letter_fix" for b in boards),
        "needs_review": sum(b.review_status == "needs_review" for b in played),
        "pending": sum(b.review_status == "pending" for b in boards),
    }
