"""Letter and digit recognition by nearest template (S0.T10, PLAN §3.1).

Letters: 48×48 ink masks of the tile centre (see calibration.letter_glyph), many samples per
letter averaged into one template. Digits: connected ink components of a banner line, each
normalised to DIGIT_W×DIGIT_H, matched against 0–9 templates.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .calibration import _ncc, glyphs

DIGIT_W, DIGIT_H = 20, 28
INK = 110  # gray level below which a banner pixel is ink


# ---- letters -----------------------------------------------------------------


def build_letter_templates(samples: dict[str, list[np.ndarray]]) -> dict[str, np.ndarray]:
    return {ch: np.mean(v, axis=0).astype(np.float32) for ch, v in samples.items()}


def classify_glyph(gl: np.ndarray, templates: dict[str, np.ndarray]) -> tuple[str, float, float]:
    """(letter, score, margin to the runner-up)."""
    scores = sorted(((_ncc(gl, t), ch) for ch, t in templates.items()), reverse=True)
    best, ch = scores[0]
    second = scores[1][0] if len(scores) > 1 else 0.0
    return ch, best, best - second


def read_board(img: np.ndarray, cal: dict, templates: dict[str, np.ndarray]):
    """Returns (letters, per-tile margins)."""
    out = [classify_glyph(g, templates) for g in glyphs(img, cal)]
    return "".join(c for c, _, _ in out), [m for _, _, m in out]


# ---- digits ------------------------------------------------------------------


def ink_components(gray: np.ndarray, min_area: int = 8) -> list[tuple[int, int, int, int]]:
    """Bounding boxes (x, y, w, h) of ink blobs, left to right."""
    ink = (gray < INK).astype(np.uint8)
    _, _, stats, _ = cv2.connectedComponentsWithStats(ink)
    return sorted(tuple(int(v) for v in s[:4]) for s in stats[1:] if s[4] >= min_area)


def norm_glyph(gray: np.ndarray, box) -> np.ndarray:
    x, y, w, h = box
    ink = (gray[y : y + h, x : x + w] < INK).astype(np.float32)
    # pad to the target aspect so "1" keeps its shape
    target = DIGIT_W / DIGIT_H
    if w / h < target:
        pad = int(round(h * target - w))
        ink = np.pad(ink, ((0, 0), (pad // 2, pad - pad // 2)))
    return cv2.resize(ink, (DIGIT_W, DIGIT_H), interpolation=cv2.INTER_AREA)


def line_digit_boxes(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Digit boxes of a 'LABEL: 123' line: tall blobs right of the colon (the small blobs)."""
    boxes = ink_components(gray)
    if not boxes:
        return []
    tall_h = max(b[3] for b in boxes)
    small = [b for b in boxes if b[3] < 0.6 * tall_h and b[2] < 0.6 * tall_h]
    if not small:
        return []
    colon_x = max(b[0] + b[2] for b in small)
    return [b for b in boxes if b[0] > colon_x and b[3] >= 0.75 * tall_h]


def read_number(gray: np.ndarray, templates: dict[str, np.ndarray]) -> tuple[int | None, float]:
    """(value, min match score) or (None, 0) if no digits."""
    boxes = line_digit_boxes(gray)
    if not boxes:
        return None, 0.0
    digits, worst = [], 1.0
    for b in boxes:
        ch, score, _ = classify_glyph(norm_glyph(gray, b), templates)
        digits.append(ch)
        worst = min(worst, score)
    return int("".join(digits)), worst


def gray_roi(img: np.ndarray, rect) -> np.ndarray:
    x, y, w, h = rect
    return cv2.cvtColor(np.ascontiguousarray(img[y : y + h, x : x + w]), cv2.COLOR_RGB2GRAY)


def read_banner(img: np.ndarray, cal: dict, digits: dict[str, np.ndarray], end: bool = False):
    """(words, score, min confidence) from the live banner, or the end screen if end=True."""
    wr = cal["roi_end_words"] if end else cal["roi_banner_words"]
    sr = cal["roi_end_score"] if end else cal["roi_banner_score"]
    w, cw = read_number(gray_roi(img, wr), digits)
    s, cs = read_number(gray_roi(img, sr), digits)
    return w, s, min(cw, cs)


# ---- persistence -------------------------------------------------------------


def save_templates(templates: dict[str, np.ndarray], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **templates)


def load_templates(path: str | Path) -> dict[str, np.ndarray]:
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


_DEFAULT: dict[str, dict] = {}


def default_templates(kind: str) -> dict[str, np.ndarray]:
    """Committed templates (fixtures/templates/<kind>.npz), loaded once."""
    if kind not in _DEFAULT:
        root = Path(__file__).resolve().parents[2]
        _DEFAULT[kind] = load_templates(root / "fixtures" / "templates" / f"{kind}.npz")
    return _DEFAULT[kind]


def read_letters(img: np.ndarray, cal: dict, templates: dict | None = None):
    """S1 signature: (letters, conf[16]) where conf is the best-vs-runner-up NCC margin."""
    return read_board(img, cal, templates or default_templates("letters"))
