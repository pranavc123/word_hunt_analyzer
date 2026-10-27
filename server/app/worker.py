"""Background processing (S3.T3): one Huey task per uploaded board / all-words capture.

Run: `uv run huey_consumer app.worker.huey` (with --app-dir semantics: PYTHONPATH=server).
Set WH_HUEY_IMMEDIATE=1 to run tasks inline (tests, debugging).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import cv2
from huey import SqliteHuey
from sqlmodel import delete, select

from whcore import allwords as aw
from whcore.calibration import load_calibration
from whcore.letters import default_templates
from whcore.pipeline import crop_rect, process_board, to_cal_scale
from whcore.solver import load_trie, load_words

from . import api_ingest, db
from .models import AllWordsCapture, AttemptRow, Board, BoardWord

ROOT = Path(__file__).resolve().parents[2]

db.data_dir().mkdir(parents=True, exist_ok=True)  # fresh checkouts / CI have no $WH_DATA yet
huey = SqliteHuey(
    "wordhunt",
    filename=str(db.data_dir() / "huey.db"),
    immediate=os.environ.get("WH_HUEY_IMMEDIATE") == "1",
)


@lru_cache(maxsize=1)
def calibration() -> dict:
    return load_calibration(ROOT / "fixtures/calibration/iphone-1206x2622.json")


@lru_cache(maxsize=1)
def trie():
    return load_trie(os.environ.get("WH_DICT", ROOT / "dictionaries/yawl.txt"))


@lru_cache(maxsize=1)
def enable() -> set[str]:
    return load_words(ROOT / "dictionaries/enable1.txt")


def _gray(rel: str | None):
    if not rel:
        return None
    return cv2.imread(str(db.data_dir() / rel), cv2.IMREAD_GRAYSCALE)


# ---- boards -----------------------------------------------------------------------


def run_board(board_id: str) -> str:
    """Process one board (idempotent: re-running replaces its attempts and word list)."""
    with db.session() as s:
        b = s.get(Board, board_id)
        if b is None:
            return "missing"
        images = {
            k: img
            for k, img in (
                ("board", _gray(b.image_path)),
                ("end_banner", _gray(b.end_banner_path)),
                ("end_list", _gray(b.end_list_path)),
            )
            if img is not None
        }
        record = b.record
        confirmed = b.letters if b.letters_confirmed else None
    try:
        res = process_board(
            record, images, calibration(), trie(), enable(), letters_override=confirmed
        )
    except Exception as e:  # keep the board, flag it
        with db.session() as s:
            b = s.get(Board, board_id)
            b.error, b.review_status, b.processed_at = (
                repr(e)[:500],
                "needs_review",
                datetime.now(UTC),
            )
            s.commit()
        raise
    with db.session() as s:
        b = s.get(Board, board_id)
        for k in (
            "letters",
            "letters_conf",
            "final_score",
            "final_word_count",
            "extracted_score",
            "reconciled",
            "end_visible_words",
            "review_status",
            "error",
            "fixes",
        ):
            if k in res:
                setattr(b, k, res[k])
        b.processed_at = datetime.now(UTC)
        s.exec(delete(AttemptRow).where(AttemptRow.board_id == board_id))
        s.exec(delete(BoardWord).where(BoardWord.board_id == board_id))
        s.flush()
        for a in res["attempts"]:
            s.add(AttemptRow(board_id=board_id, **a))
        for word, info in res["board_words"].items():
            s.add(BoardWord(board_id=board_id, word=word, **info))
        s.commit()
        status, played = b.review_status, b.status == "played"
    if played and status in ("verified", "needs_review"):
        retry_unmatched_allwords()
    return status


@huey.task(retries=2, retry_delay=10)
def process_board_task(board_id: str) -> str:
    return run_board(board_id)


# ---- all words ----------------------------------------------------------------------


def _candidates() -> list[dict]:
    with db.session() as s:
        boards = s.exec(
            select(Board).where(
                Board.status == "played", Board.review_status.in_(["verified", "needs_review"])
            )
        ).all()
        out = []
        for b in boards:
            words = s.exec(
                select(AttemptRow.word).where(
                    AttemptRow.board_id == b.id, AttemptRow.result == "valid_new"
                )
            ).all()
            out.append({"id": b.id, "words": [w for w in words if w], "t": b.opened_at})
    return out


def run_allwords(record_id: str) -> str:
    with db.session() as s:
        cap = s.get(AllWordsCapture, record_id)
        if cap is None:
            return "missing"
        rec = cap.record
        folder = db.data_dir() / (cap.frames_path or "")
    rect = crop_rect(calibration(), "list_band")
    crops, offsets, gaps = [], [], []
    for name, off, gap in zip(rec["frames"], rec["shifts_px"], rec["gap_flags"], strict=True):
        img = cv2.imread(str(folder / name), cv2.IMREAD_GRAYSCALE)
        if img is not None:
            crops.append(to_cal_scale(img, rect))
            offsets.append(off)
            gaps.append(gap)
    if not crops:
        return "no frames"
    cap_obj = aw.process_allwords(crops, offsets, gaps, default_templates("digits"))
    summary = aw.summarise(cap_obj)
    cands = _candidates()
    raw = [(sl.length, sl.word) for sl in cap_obj.ordered() if sl.kind == "found" and sl.word]
    revealed = aw.snap_revealed(raw, cands) if cands else [w for _, w in raw]
    state, bid, _ = aw.match_revealed(revealed, cands)
    rows = [[sl.length, sl.kind, sl.word] for sl in cap_obj.ordered()]
    with db.session() as s:
        cap = s.get(AllWordsCapture, record_id)
        cap.rows, cap.revealed = rows, revealed
        cap.counts_by_length = {str(k): v for k, v in summary["counts_by_length"].items()}
        cap.status, cap.match_state = summary["status"], state
        cap.board_id = bid if state == "matched" else None
        cap.processed_at = datetime.now(UTC)
        if state == "matched":
            b = s.get(Board, bid)
            b.all_words_status, b.all_words_id = summary["status"], record_id
            b.masked_counts_by_length = {
                str(k): v for k, v in summary["masked_counts_by_length"].items()
            }
            b.all_words_complete_down_to = summary["complete_down_to"]
        s.commit()
    return state


def retry_unmatched_allwords() -> None:
    with db.session() as s:
        ids = s.exec(
            select(AllWordsCapture.id).where(
                AllWordsCapture.match_state != "matched", AllWordsCapture.processed_at.is_not(None)
            )
        ).all()
    for rid in ids:
        run_allwords(rid)


@huey.task(retries=2, retry_delay=10)
def process_allwords_task(record_id: str) -> str:
    return run_allwords(record_id)


# ---- wiring -------------------------------------------------------------------------

api_ingest.on_board_stored.append(lambda bid: process_board_task(bid))
api_ingest.on_allwords_stored.append(lambda rid: process_allwords_task(rid))
