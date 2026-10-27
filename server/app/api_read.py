"""Read API for the review app (S4.T2) + letter fixes + the built web app."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import func, select

from . import db
from .api_ingest import require_token
from .models import AllWordsCapture, AttemptRow, Board, BoardWord, Session

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])
BAR = 30000  # the user's keep bar (PLAN §8)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def _board_stats(s, board_ids: list[str]) -> dict[str, dict]:
    """max_points, solver word count and found count per board."""
    if not board_ids:
        return {}
    rows = s.exec(
        select(
            BoardWord.board_id, func.sum(BoardWord.points), func.count(), func.sum(BoardWord.found)
        )
        .where(BoardWord.board_id.in_(board_ids), BoardWord.in_base)
        .group_by(BoardWord.board_id)
    ).all()
    return {
        bid: {"max_points": int(mp or 0), "solver_words": int(n or 0), "found_in_base": int(f or 0)}
        for bid, mp, n, f in rows
    }


def _board_row(b: Board, stats: dict) -> dict:
    st = stats.get(b.id, {})
    return {
        "id": b.id,
        "seq": b.seq,
        "status": b.status,
        "review_status": b.review_status,
        "letters": b.letters,
        "opened_at": _iso(b.opened_at),
        "view_ms": b.view_ms,
        "final_score": b.final_score,
        "final_word_count": b.final_word_count,
        "extracted_score": b.extracted_score,
        "max_points": st.get("max_points"),
        "solver_words": st.get("solver_words"),
        "fixes": b.fixes or [],
        "all_words_status": b.all_words_status,
    }


def _session_summary(s, sess: Session) -> dict:
    boards = s.exec(select(Board).where(Board.session_id == sess.id).order_by(Board.seq)).all()
    stats = _board_stats(s, [b.id for b in boards])
    played = [b for b in boards if b.status == "played"]
    skipped = [b for b in boards if b.status == "skipped"]
    scores = [b.final_score or b.extracted_score or 0 for b in played]
    best = max(played, key=lambda b: b.final_score or b.extracted_score or 0, default=None)
    # biggest miss: the highest-scoring word not found on a played board
    miss = None
    if played:
        row = s.exec(
            select(BoardWord.word, BoardWord.points, BoardWord.board_id)
            .where(BoardWord.board_id.in_([b.id for b in played]), BoardWord.found == False)  # noqa: E712
            .order_by(BoardWord.points.desc(), BoardWord.word)
        ).first()
        if row:
            miss = {"word": row[0], "points": row[1], "board_id": row[2]}
    return {
        "id": sess.id,
        "started_at": _iso(sess.started_at),
        "device": sess.device,
        "board_count": len(boards),
        "played_count": len(played),
        "keep_rate": round(len(played) / len(boards), 3) if boards else 0.0,
        "count_30k": sum(sc >= BAR for sc in scores),
        "skip_seconds": round(sum(b.view_ms for b in skipped) / 1000, 1),
        "verified_count": sum(b.review_status == "verified" for b in played),
        "needs_review": sum(b.review_status == "needs_review" for b in played),
        "needs_letter_fix": sum(b.review_status == "needs_letter_fix" for b in boards),
        "best_board": _board_row(best, stats) if best else None,
        "biggest_miss": miss,
        "score_by_position": [
            {"seq": b.seq, "score": b.final_score or b.extracted_score} for b in played
        ],
        "boards": [_board_row(b, stats) for b in boards],
    }


@router.get("/sessions")
def list_sessions(limit: int = 50) -> list[dict]:
    with db.session() as s:
        sessions = s.exec(select(Session).order_by(Session.started_at.desc()).limit(limit)).all()
        out = []
        for sess in sessions:
            summ = _session_summary(s, sess)
            summ.pop("boards")
            out.append(summ)
    return out


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    with db.session() as s:
        sess = s.get(Session, session_id)
        if sess is None:
            raise HTTPException(404, "no such session")
        return _session_summary(s, sess)


def _image_url(rel: str | None) -> str | None:
    return f"/v1/images/{rel.removeprefix('images/')}" if rel else None


def _board_detail(s, b: Board) -> dict:
    stats = _board_stats(s, [b.id])
    attempts = s.exec(
        select(AttemptRow).where(AttemptRow.board_id == b.id).order_by(AttemptRow.seq)
    ).all()
    words = s.exec(
        select(BoardWord)
        .where(BoardWord.board_id == b.id)
        .order_by(BoardWord.points.desc(), BoardWord.word)
    ).all()
    siblings = s.exec(
        select(Board.id, Board.seq).where(Board.session_id == b.session_id).order_by(Board.seq)
    ).all()
    ids = [i for i, _ in siblings]
    k = ids.index(b.id)
    capture = s.get(AllWordsCapture, b.all_words_id) if b.all_words_id else None
    return {
        **_board_row(b, stats),
        "session_id": b.session_id,
        "letters_conf": b.letters_conf,
        "letters_confirmed": b.letters_confirmed,
        "end_visible_words": b.end_visible_words,
        "reconciled": b.reconciled,
        "error": b.error,
        "images": {
            "board": _image_url(b.image_path),
            "end_banner": _image_url(b.end_banner_path),
            "end_list": _image_url(b.end_list_path),
        },
        "attempts": [
            {
                "seq": a.seq,
                "t_start_ms": a.t_start_ms,
                "t_end_ms": a.t_end_ms,
                "tiles_seen": a.tiles_seen,
                "path": a.path,
                "word": a.word,
                "result": a.result,
                "points": a.points,
            }
            for a in attempts
        ],
        "words": [
            {
                "word": w.word,
                "path": w.best_path,
                "points": w.points,
                "found": w.found,
                "found_at_ms": w.found_at_ms,
                "in_enable": w.in_enable,
                "in_base": w.in_base,
            }
            for w in words
        ],
        "all_words": {
            "status": capture.status,
            "counts_by_length": capture.counts_by_length,
            "revealed": capture.revealed,
        }
        if capture
        else None,
        "prev_id": ids[k - 1] if k > 0 else None,
        "next_id": ids[k + 1] if k + 1 < len(ids) else None,
    }


@router.get("/boards/{board_id}")
def get_board(board_id: str) -> dict:
    with db.session() as s:
        b = s.get(Board, board_id)
        if b is None:
            raise HTTPException(404, "no such board")
        return _board_detail(s, b)


class LettersFix(BaseModel):
    letters: str


@router.patch("/boards/{board_id}/letters")
def fix_letters(board_id: str, body: LettersFix) -> dict:
    letters = body.letters.strip().upper()
    if not re.fullmatch(r"[A-Z]{16}", letters):
        raise HTTPException(422, "letters must be 16 A–Z characters, row by row")
    with db.session() as s:
        b = s.get(Board, board_id)
        if b is None:
            raise HTTPException(404, "no such board")
        b.letters, b.letters_confirmed = letters, True
        s.commit()
    from . import worker  # re-solve + re-reconcile with the confirmed letters, synchronously

    worker.run_board(board_id)
    with db.session() as s:
        return _board_detail(s, s.get(Board, board_id))


@router.get("/images/{path:path}")
def get_image(path: str) -> FileResponse:
    base = (db.data_dir() / "images").resolve()
    target = (base / path).resolve()
    if base not in target.parents or not target.is_file():
        raise HTTPException(404, "no such image")
    return FileResponse(target, media_type="image/jpeg")


def mount_web(app) -> None:
    """Serve the built PWA (web/dist) at /, with deep links falling back to index.html."""
    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if not (dist / "index.html").exists():
        return

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        f = (dist / full_path).resolve()
        if full_path and dist in f.parents and f.is_file():
            return FileResponse(f)
        if full_path.startswith(("v1/", "diag")):
            raise HTTPException(404)
        return FileResponse(dist / "index.html")
