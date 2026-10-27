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
    """(words, score) from the end-screen banner crop. The two text lines are located from the
    ink itself (robust to the screen sliding a little); calibrated offsets are the fallback."""
    digits = digits or lt.default_templates("digits")
    rect = crop_rect(cal, "roi_end_banner")
    g = to_cal_scale(banner, rect)
    ink_rows = (g < 120).sum(1) > 3
    lines = [(a, b) for a, b in _runs(ink_rows) if b - a >= 15]
    if len(lines) >= 2:
        (a1, b1), (a2, b2) = lines[0], lines[-1]
        w, _ = lt.read_number(g[max(0, a1 - 3) : b1 + 3], digits)
        s, _ = lt.read_number(g[max(0, a2 - 3) : b2 + 3], digits)
        if w is not None and s is not None:
            return w, s
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


def _evaluate(letters: str, attempts: list[dict], rows, end_words, end_score, trie) -> dict:
    """Solve, resolve the accepted attempts and reconcile against the end screen."""
    sol = solve(letters.lower(), trie)
    lw = letters.lower()
    accepted = [a for a in attempts if a["release_state"] == "valid_new"]
    oov = {"".join(lw[i] for i in a["tiles_seen"]) for a in accepted if len(a["tiles_seen"]) >= 3}
    visible = snap_visible(rows, set(sol) | oov)
    vis_words = {v["word"] for v in visible if v["word"]}
    words = build_words(attempts, letters, sol, end_score, vis_words)
    rec = reconcile([w["word"] for w in words if w["word"]], end_words, end_score, visible)
    exact = sum(raw.lower() in sol for raw, _ in rows)
    return {"sol": sol, "words": words, "rec": rec, "visible": visible, "exact_visible": exact}


def _try_letter_fixes(
    letters,
    ranked,
    margins,
    attempts,
    rows,
    end_words,
    end_score,
    trie,
    base,
    max_tiles: int = 6,
    max_full: int = 4,
):
    """A misread tile shows up as visible end-screen words the board cannot spell. Try the
    runner-up letters on the least certain tiles; keep a variant only if it then reconciles."""
    raw = [w.lower() for w, _ in rows]
    order = sorted(range(16), key=lambda i: margins[i])[:max_tiles]
    variants = []
    for i in order:
        for ch, _ in ranked[i][1:]:
            v = letters[:i] + ch + letters[i + 1 :]
            sol = solve(v.lower(), trie)
            variants.append((sum(w in sol for w in raw), i, ch, v))
    variants.sort(key=lambda x: -x[0])
    for exact, i, ch, v in variants[:max_full]:
        if exact <= base["exact_visible"]:
            break
        ev = _evaluate(v, attempts, rows, end_words, end_score, trie)
        if ev["rec"]["verified"]:
            return ev, v, f"tile {i}: {letters[i]}→{ch} (end-screen words)"
    return None


def _try_dropping(letters, attempts, rows, end_words, end_score, trie, base, max_tries: int = 30):
    """More accepted attempts than the end screen's WORDS: a WORDS misread or a last-instant
    acceptance. Drop the likeliest single extra attempt if that makes the board reconcile."""
    accepted = [k for k, a in enumerate(attempts) if a["release_state"] == "valid_new"]
    if len(accepted) - end_words != 1:
        return None
    words = base["words"]

    # likeliest first: colour disagreed, then repaired/OOV reads, then short words, then the rest
    def rank(j):
        a, w = attempts[accepted[j]], words[j] if j < len(words) else {}
        return (
            a.get("confidence", 1.0) >= 1.0,
            not (w.get("cost") or w.get("oov")),
            len(a["tiles_seen"]) > 3,
            -j,
        )

    for j in sorted(range(len(accepted)), key=rank)[:max_tries]:
        k = accepted[j]
        trial = [
            dict(a, release_state="not_a_word") if n == k else a for n, a in enumerate(attempts)
        ]
        ev = _evaluate(letters, trial, rows, end_words, end_score, trie)
        if ev["rec"]["verified"]:
            return (
                ev,
                trial,
                f"attempt {attempts[k]['seq']} not counted (WORDS {len(accepted)}→{end_words})",
            )
    return None


def process_board(
    record: dict,
    images: dict[str, np.ndarray],
    cal: dict,
    trie,
    enable: set[str],
    templates: dict | None = None,
    letters_override: str | None = None,
) -> dict:
    """One uploaded BoardRecord → letters, words, reconciliation and the board's word list.
    images: {"board": ..., "end_banner": ..., "end_list": ...} (gray or RGB, any scale).
    letters_override: letters a person confirmed (used as-is, no automatic letter fixes)."""
    out: dict = {"error": None}
    if letters_override:
        ranked = [[(c, 1.0)] for c in letters_override.upper()]
    elif "board" not in images:  # keep the attempts; letters come from a person (PATCH)
        attempts = [
            {
                "seq": a["seq"],
                "t_start_ms": a["t_start_ms"],
                "t_end_ms": a["t_end_ms"],
                "tiles_seen": a["tiles_seen"],
                "result": a["release_state"],
                "word": None,
                "path": None,
                "points": 0,
                "confidence": a.get("confidence", 1.0),
            }
            for a in record.get("attempts", [])
        ]
        return {
            **out,
            "letters": None,
            "review_status": "needs_letter_fix",
            "error": "no board image",
            "attempts": attempts,
            "board_words": {},
        }
    else:
        rect = crop_rect(cal, "board")
        g = to_cal_scale(images["board"], rect)
        local = {
            "tile_centers": [[x - rect[0], y - rect[1]] for x, y in cal["tile_centers"]],
            "tile_size": cal["tile_size"],
        }
        ranked = lt.rank_board(g, local, templates or lt.default_templates("letters"))
    letters = "".join(r[0][0] for r in ranked)
    margins = [r[0][1] - (r[1][1] if len(r) > 1 else 0.0) for r in ranked]
    out.update(letters=letters, letters_conf=[round(float(m), 3) for m in margins])
    low = min(margins) < LOW_LETTER_MARGIN
    played = record["status"] == "played"
    attempts = record.get("attempts", [])
    sol = solve(letters.lower(), trie)
    words = []
    if played:
        end_words = end_score = None
        if "end_banner" in images:
            end_words, end_score = read_end_banner(images["end_banner"], cal)
        rows = read_end_list(images["end_list"], cal) if "end_list" in images else []
        ev = _evaluate(letters, attempts, rows, end_words, end_score, trie)
        fixes: list[str] = []
        if not ev["rec"]["verified"] and not letters_override:
            better = _try_letter_fixes(
                letters, ranked, margins, attempts, rows, end_words, end_score, trie, ev
            )
            if better:
                ev, letters, fix = better
                fixes.append(fix)
                low = False  # the end screen confirmed the corrected letters
        if not ev["rec"]["verified"] and end_words is not None:
            dropped = _try_dropping(letters, attempts, rows, end_words, end_score, trie, ev)
            if dropped:
                ev, attempts, fix = dropped
                fixes.append(fix)
        sol, words, rec, visible = ev["sol"], ev["words"], ev["rec"], ev["visible"]
        out.update(
            letters=letters,
            final_word_count=end_words,
            final_score=end_score,
            extracted_score=rec["points"],
            reconciled=rec["verified"],
            end_visible_words=[v["word"] or v["raw"] for v in visible],
            reconcile=rec,
            visible=visible,
            fixes=fixes,
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
