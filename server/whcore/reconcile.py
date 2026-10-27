"""End-screen reading + reconciliation of a played board (S0.T11, PLAN §3.3)."""

from __future__ import annotations

import re

import cv2
import numpy as np
import pytesseract

from .scoring import word_points

TAN_MIN_R, TAN_MIN_RB = 120, 30  # word text on the end-screen list (tan on dark green)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    d = np.diff(np.r_[0, mask.astype(int), 0])
    return list(zip(np.where(d == 1)[0].tolist(), np.where(d == -1)[0].tolist(), strict=True))


def list_rows(img: np.ndarray, cal: dict) -> list[tuple[int, int]]:
    """(y0, y1) of the found-word rows in the player's end-screen list."""
    x, y, w, h = cal["roi_end_list"]
    sub = img[y : y + h, x : x + w].astype(int)
    tan = (sub[..., 0] > TAN_MIN_R) & (sub[..., 0] - sub[..., 2] > TAN_MIN_RB)
    wx0, wx1 = (v - x for v in cal["end_list_word_x"])
    rows = [(a + y, b + y) for a, b in _runs(tan[:, wx0:wx1].any(1)) if b - a > 20]
    return rows


def _ocr_line(gray: np.ndarray, whitelist: str) -> str:
    big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, b = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if b.mean() < 128:
        b = 255 - b
    b = cv2.copyMakeBorder(b, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)
    cfg = f"--psm 7 -c tessedit_char_whitelist={whitelist}"
    return pytesseract.image_to_string(b, config=cfg).strip()


def read_end_list(img: np.ndarray, cal: dict) -> list[tuple[str, int | None]]:
    """[(WORD, points)] for each visible row of the player's end-screen list (top 15)."""
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    wx0, wx1 = cal["end_list_word_x"]
    px0, px1 = cal["end_list_points_x"]
    out = []
    for y0, y1 in list_rows(img, cal):
        pad = 4
        # tan words are lighter than the panel: use the red channel for contrast
        word = _ocr_line(img[y0 - pad : y1 + pad, wx0:wx1, 0], "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        pts = _ocr_line(gray[y0 - pad : y1 + pad, px0:px1], "0123456789")
        word = re.sub("[^A-Z]", "", word)
        m = re.search(r"\d+", pts)
        if word:
            out.append((word, int(m.group()) if m else None))
    return out


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def snap(word: str, vocabulary, length: int | None = None) -> tuple[str, int]:
    """Nearest vocabulary word (edit distance; ties → same length, then alphabetical).
    `length` (from the points column) restricts the candidates when any have that length."""
    w = word.lower()
    vocab = [v for v in vocabulary if length is None or len(v) == length] or list(vocabulary)
    best = min(vocab, key=lambda v: (levenshtein(w, v), abs(len(v) - len(w)), v))
    return best, levenshtein(w, best)


POINTS_TO_LEN = {word_points(n): n for n in range(3, 17)}


def snap_visible(rows, vocabulary, max_dist: int = 2) -> list[dict]:
    """Snap OCR'd end-screen rows to vocabulary words. points_ok is None when unread."""
    out = []
    for raw, pts in rows:
        word, dist = snap(raw, vocabulary, POINTS_TO_LEN.get(pts))
        ok = dist <= max_dist
        out.append(
            {
                "raw": raw,
                "word": word if ok else None,
                "dist": dist,
                "points": pts,
                "points_ok": (pts == word_points(len(word)))
                if ok and pts in POINTS_TO_LEN
                else None,
            }
        )
    return out


def reconcile(
    accepted: list[str], end_words: int | None, end_score: int | None, visible: list[dict]
) -> dict:
    """§3.3: verified iff Σ points == SCORE, count == WORDS, every visible word ∈ accepted."""
    acc = set(accepted)
    total = sum(word_points(len(w)) for w in accepted)
    read = [v for v in visible if v["word"] is not None]  # an OCR-unreadable row is unknown
    vis_words = [v["word"] for v in read]
    checks = {
        "score": end_score is not None and total == end_score,
        "count": end_words is not None and len(accepted) == end_words and len(acc) == len(accepted),
        "visible": len(read) >= max(1, len(visible) - 2)  # at most 2 unreadable rows
        and all(w in acc for w in vis_words)
        and all(v["points_ok"] is not False for v in read),
    }
    return {
        "verified": all(checks.values()),
        "checks": checks,
        "points": total,
        "end_score": end_score,
        "count": len(accepted),
        "end_words": end_words,
        "visible_missing": [w for w in vis_words if w not in acc],
        "points_unread": sum(v["points_ok"] is None for v in visible),
        "rows_unread": len(visible) - len(read),
    }
