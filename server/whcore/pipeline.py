"""Server-side processing of uploaded records (S3.T3, PLAN §3).

The phone uploads grayscale crops at its buffer scale (884×1920 on the S0 device). Each crop is
first resized to calibration scale, so every coordinate in the calibration applies unchanged.
"""

from __future__ import annotations

import re

import cv2
import numpy as np

from . import letters as lt
from .allwords import LIST_BAND_RECT
from .reconcile import _ocr_line, _runs, reconcile, snap_visible
from .scoring import word_points
from .solver import best_path, solve
from .words import build_words

LOW_LETTER_MARGIN = 0.03  # best-vs-runner-up NCC margin below this → needs_letter_fix
TEXT_GRAY = 110  # tan list words / white points are brighter than this; the panel is ~63


def crop_rect(cal: dict, kind: str) -> list[int]:
    if kind == "board":
        (x0, y0), (x1, y1) = cal["tile_centers"][0], cal["tile_centers"][-1]
        m = cal["pitch"][0] / 2
        bx0, by0, bx1, by1 = round(x0 - m), round(y0 - m), round(x1 + m), round(y1 + m)
        return [bx0, by0, bx1 - bx0, by1 - by0]
    if kind == "list_band":
        return list(LIST_BAND_RECT)
    return list(cal[kind])  # roi_end_banner, roi_end_list


def to_cal_scale(img: np.ndarray, rect: list[int]) -> np.ndarray:
    """Gray crop resized to the calibration-scale size of its rect."""
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    w, h = rect[2], rect[3]
    if g.shape[1] == w and g.shape[0] == h:
        return g
    return cv2.resize(
        g, (w, h), interpolation=cv2.INTER_CUBIC if g.shape[1] < w else cv2.INTER_AREA
    )


def read_board_letters(board: np.ndarray, cal: dict, templates: dict | None = None):
    """(letters, margins[16]) from a board crop (any scale, gray or RGB)."""
    rect = crop_rect(cal, "board")
    g = to_cal_scale(board, rect)
    local = {
        "tile_centers": [[x - rect[0], y - rect[1]] for x, y in cal["tile_centers"]],
        "tile_size": cal["tile_size"],
    }
    return lt.read_letters(g, local, templates)


def _sub(rect: list[int], inner: list[int]) -> tuple[slice, slice]:
    """Slices of `inner` (absolute rect) inside a crop of `rect`."""
    x, y = inner[0] - rect[0], inner[1] - rect[1]
    return slice(max(0, y), y + inner[3]), slice(max(0, x), x + inner[2])


def read_end_banner(banner: np.ndarray, cal: dict, digits: dict | None = None):
    """(words, score) from the end-screen banner crop."""
    digits = digits or lt.default_templates("digits")
    rect = crop_rect(cal, "roi_end_banner")
    g = to_cal_scale(banner, rect)
    w, _ = lt.read_number(g[_sub(rect, cal["roi_end_words"])], digits)
    s, _ = lt.read_number(g[_sub(rect, cal["roi_end_score"])], digits)
    return w, s


def read_end_list(end_list: np.ndarray, cal: dict) -> list[tuple[str, int | None]]:
    """[(WORD, points)] of the visible end-screen rows from the gray list crop."""
    rect = crop_rect(cal, "roi_end_list")
    g = to_cal_scale(end_list, rect)
    wx0, wx1 = (v - rect[0] for v in cal["end_list_word_x"])
    px0, px1 = (v - rect[0] for v in cal["end_list_points_x"])
    rows = [(a, b) for a, b in _runs((g[:, wx0:wx1] > TEXT_GRAY).any(1)) if b - a > 20]
    out = []
    for y0, y1 in rows:
        lo, hi = max(0, y0 - 4), y1 + 4
        word = re.sub("[^A-Z]", "", _ocr_line(g[lo:hi, wx0:wx1], "ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        pts = re.search(r"\d+", _ocr_line(g[lo:hi, px0:px1], "0123456789"))
        value = int(pts.group()) if pts else None
        if not word or (value is None and "MORE" in word):  # the "(N more)" line
            continue
        out.append((word, value))
    return out[:15]  # the end screen shows the top 15


def process_board(
    record: dict,
    images: dict[str, np.ndarray],
    cal: dict,
    trie,
    enable: set[str],
    templates: dict | None = None,
) -> dict:
    """One uploaded BoardRecord → letters, words, reconciliation and the board's word list.
    images: {"board": ..., "end_banner": ..., "end_list": ...} (gray or RGB, any scale)."""
    out: dict = {"error": None}
    if "board" not in images:
        return {**out, "review_status": "needs_letter_fix", "error": "no board image"}
    letters, margins = read_board_letters(images["board"], cal, templates)
    out.update(letters=letters, letters_conf=[round(float(m), 3) for m in margins])
    low = min(margins) < LOW_LETTER_MARGIN
    sol = solve(letters.lower(), trie)
    played = record["status"] == "played"
    attempts = record.get("attempts", [])
    words = []
    if played:
        end_words = end_score = None
        if "end_banner" in images:
            end_words, end_score = read_end_banner(images["end_banner"], cal)
        rows = read_end_list(images["end_list"], cal) if "end_list" in images else []
        lw = letters.lower()
        accepted = [a for a in attempts if a["release_state"] == "valid_new"]
        oov = {
            "".join(lw[i] for i in a["tiles_seen"]) for a in accepted if len(a["tiles_seen"]) >= 3
        }
        visible = snap_visible(rows, set(sol) | oov)
        vis_words = {v["word"] for v in visible if v["word"]}
        words = build_words(attempts, letters, sol, end_score, vis_words)
        rec = reconcile([w["word"] for w in words if w["word"]], end_words, end_score, visible)
        out.update(
            final_word_count=end_words,
            final_score=end_score,
            extracted_score=rec["points"],
            reconciled=rec["verified"],
            end_visible_words=[v["word"] or v["raw"] for v in visible],
            reconcile=rec,
            visible=visible,
        )
        status = "verified" if rec["verified"] else "needs_review"
    else:
        status = "skipped"
    if low:
        status = "needs_letter_fix"
    found_at = {}
    by_attempt = iter(words)
    resolved = []
    for a in attempts:
        if a["release_state"] == "valid_new":
            w = next(by_attempt, None)
            resolved.append((a, w))
            if w and w["word"] and w["word"] not in found_at:
                found_at[w["word"]] = a["t_start_ms"]
        else:
            resolved.append((a, None))
    out["attempts"] = [
        {
            "seq": a["seq"],
            "t_start_ms": a["t_start_ms"],
            "t_end_ms": a["t_end_ms"],
            "tiles_seen": a["tiles_seen"],
            "result": a["release_state"],
            "word": w["word"] if w else None,
            "path": w["path"] if w else None,
            "points": word_points(len(w["word"])) if w and w["word"] else 0,
            "confidence": a.get("confidence", 1.0),
        }
        for a, w in resolved
    ]
    board_words = {
        word: {
            "best_path": info["best_path"],
            "points": info["points"],
            "found": word in found_at,
            "found_at_ms": found_at.get(word),
            "in_enable": word in enable,
            "in_base": True,
        }
        for word, info in sol.items()
    }
    for w in words:  # accepted words the base list lacks (OOV)
        if w["word"] and w["word"] not in board_words:
            board_words[w["word"]] = {
                "best_path": w["path"] or best_path([w["observed"]]),
                "points": word_points(len(w["word"])),
                "found": True,
                "found_at_ms": found_at.get(w["word"]),
                "in_enable": w["word"] in enable,
                "in_base": False,
            }
    out.update(review_status=status, board_words=board_words, solver_words=len(sol))
    return out
