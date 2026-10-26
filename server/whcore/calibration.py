"""Screen calibration from screenshots (S0.T4): tile grid, ROIs, resting colour, seed letters.

All coordinates are pixels in the native screenshot frame; rects are [x, y, w, h].
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

SIZE = 4
LETTER_PX = 48  # template side
LETTER_FRAC = 0.76  # central fraction of a tile used for the letter glyph
SAMPLE_DY_FRAC = -0.39  # colour sample patch sits in the tile's top strip, clear of the glyph
SAMPLE_W_FRAC, SAMPLE_H_FRAC = 0.21, 0.085


def load_rgb(path: str | Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def _components(mask: np.ndarray, close: int, min_area: int) -> list[list[int]]:
    """Bounding boxes [x, y, w, h] of closed connected components above min_area."""
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((close, close), np.uint8))
    _, _, stats, _ = cv2.connectedComponentsWithStats(m)
    return [s[:4].tolist() for s in stats[1:] if s[4] >= min_area]


def _beige(img: np.ndarray) -> np.ndarray:
    r, g, b = (img[..., i].astype(int) for i in range(3))
    return (r > 170) & (r - b > 35) & (r > g)


def detect_grid(img: np.ndarray) -> dict:
    """Find the 16 resting tiles (beige squares on the green board), row-major."""
    side = min(img.shape[:2])
    boxes = _components(_beige(img), max(3, side // 50) | 1, (side // 12) ** 2)
    boxes = [b for b in boxes if 0.85 < b[2] / b[3] < 1.18]
    if len(boxes) != SIZE * SIZE:
        raise ValueError(f"expected 16 tiles, found {len(boxes)}")
    boxes.sort(key=lambda b: b[1])
    rows = [sorted(boxes[i : i + SIZE], key=lambda b: b[0]) for i in range(0, 16, SIZE)]
    ordered = [b for row in rows for b in row]
    centres = np.array([[x + w / 2, y + h / 2] for x, y, w, h in ordered]).reshape(SIZE, SIZE, 2)
    # fit a regular lattice: per-column x and per-row y averaged, then a constant pitch
    xs, ys = centres[..., 0].mean(0), centres[..., 1].mean(1)
    px, py = np.diff(xs).mean(), np.diff(ys).mean()
    fit = [[xs[0] + c * px, ys[0] + r * py] for r in range(SIZE) for c in range(SIZE)]
    size = float(np.median([min(b[2], b[3]) for b in ordered]))
    return {
        "tile_centers": [[round(x, 1), round(y, 1)] for x, y in fit],
        "raw_centers": centres.reshape(-1, 2).round(1).tolist(),
        "tile_size": round(size, 1),
        "pitch": [round(float(px), 2), round(float(py), 2)],
    }


def sample_rect(cx: float, cy: float, tile_size: float) -> list[int]:
    w, h = tile_size * SAMPLE_W_FRAC, tile_size * SAMPLE_H_FRAC
    y = cy + tile_size * SAMPLE_DY_FRAC
    return [round(cx - w / 2), round(y - h / 2), round(w), round(h)]


def rect_mean(img: np.ndarray, rect: list[int]) -> list[float]:
    x, y, w, h = rect
    return img[y : y + h, x : x + w].reshape(-1, 3).mean(0).round(1).tolist()


def tile_samples(img: np.ndarray, cal: dict) -> list[list[float]]:
    s = cal["tile_size"]
    return [rect_mean(img, sample_rect(cx, cy, s)) for cx, cy in cal["tile_centers"]]


def find_banner(img: np.ndarray) -> dict:
    """Board-screen banner: the white box at the top holding WORDS and SCORE."""
    h, w = img.shape[:2]
    white = img.min(2) > 235
    white[int(h * 0.3) :] = False
    boxes = [b for b in _components(white, 21, (w // 6) ** 2) if b[2] > w * 0.6]
    if not boxes:
        raise ValueError("banner not found")
    x, y, bw, bh = max(boxes, key=lambda b: b[2] * b[3])
    # text lines inside the banner: dark glyphs, to the right of the avatar
    box = img[y : y + bh, x : x + bw].astype(int)
    dark = (box.max(2) < 120) & (box.max(2) - box.min(2) < 25)  # neutral ink, not the avatar
    lines = _runs(dark.any(1))
    lines = [ln for ln in lines if ln[1] - ln[0] > bh * 0.08]
    words_line, score_line = lines[0], lines[-1]

    def line_rect(ln, left=0):
        cols = left + np.where(dark[ln[0] : ln[1], left:].any(0))[0]
        return [int(x + cols[0]), int(y + ln[0]), int(cols[-1] - cols[0] + 1), int(ln[1] - ln[0])]

    words = line_rect(words_line)  # "WORDS: n" starts right of the avatar
    return {
        "roi_banner": [x, y, bw, bh],
        "roi_banner_words": words,
        "roi_banner_score": line_rect(score_line, left=words[0] - x - 10),
    }


def find_timer(img: np.ndarray, below_y: int) -> list[int]:
    """Timer pill: a dark-green rounded rect just below the banner."""
    r, g = img[..., 0].astype(int), img[..., 1].astype(int)
    pill = (r < 85) & (g > 95) & (g < 125) & (g - r > 25)
    pill[:below_y] = False
    pill[below_y + img.shape[0] // 8 :] = False
    boxes = _components(pill, 15, 4000)
    if not boxes:
        raise ValueError("timer not found")
    return max(boxes, key=lambda b: b[2] * b[3])


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    d = np.diff(np.r_[0, mask.astype(int), 0])
    return list(zip(np.where(d == 1)[0].tolist(), np.where(d == -1)[0].tolist(), strict=True))


def find_end_layout(img: np.ndarray) -> dict:
    """End screen: the player's (left) banner and found-word list column."""
    h, w = img.shape[:2]
    r, g, b = (img[..., i].astype(int) for i in range(3))
    panel = (abs(r - 52) < 6) & (abs(g - 70) < 6) & (abs(b - 46) < 6)
    panels = [p for p in _components(panel, 31, (w // 6) ** 2) if p[0] + p[2] / 2 < w / 2]
    if not panels:
        raise ValueError("end-screen list panel not found")
    lx, ly, lw, lh = min(panels, key=lambda p: p[0])
    white = img.min(2) > 180
    boxes = [
        bx
        for bx in _components(white, 21, (w // 10) ** 2)
        if bx[1] + bx[3] <= ly + 5 and bx[0] < w / 2 and bx[2] > lw * 0.8
    ]
    if not boxes:
        raise ValueError("end-screen banner not found")
    bx, by, bw, bh = max(boxes, key=lambda bb: bb[1])
    dark = img[by : by + bh, bx : bx + bw].max(2) < 120
    lines = [ln for ln in _runs(dark.any(1)) if ln[1] - ln[0] > bh * 0.1]
    # list rows: tan word text on the left part of the panel
    tan = (r > 120) & (r - b > 30)
    sub = tan[ly : ly + lh, lx : lx + lw]
    rows = [(a + ly, z + ly) for a, z in _runs(sub.any(1)) if z - a > 20]
    cols = np.where(sub.any(0))[0]
    word_x1 = int(lx + cols.max())
    pitch = float(np.diff([a for a, _ in rows]).mean()) if len(rows) > 1 else 0.0
    return {
        "roi_end_banner": [bx, by, bw, bh],
        "roi_end_words": [bx, by + lines[0][0], bw, lines[0][1] - lines[0][0]],
        "roi_end_score": [bx, by + lines[-1][0], bw, lines[-1][1] - lines[-1][0]],
        "roi_end_list": [lx, ly, lw, lh],
        "end_list_word_x": [lx, word_x1 + 10],
        "end_list_points_x": [word_x1 + 10, lx + lw],
        "end_list_first_row": [rows[0][0], rows[0][1] - rows[0][0]] if rows else None,
        "end_list_row_pitch": round(pitch, 2),
        "end_list_rows": len(rows),
    }


# ---- letter templates -------------------------------------------------------


def letter_glyph(img: np.ndarray, cx: float, cy: float, tile_size: float) -> np.ndarray:
    """Binary-ish glyph (1 = ink) of the tile's central region, LETTER_PX square, float32."""
    half = tile_size * LETTER_FRAC / 2
    x0, y0 = round(cx - half), round(cy - half)
    x1, y1 = round(cx + half), round(cy + half)
    patch = np.ascontiguousarray(img[y0:y1, x0:x1])
    gray = patch if patch.ndim == 2 else cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
    ink = (gray < 100).astype(np.float32)
    return cv2.resize(ink, (LETTER_PX, LETTER_PX), interpolation=cv2.INTER_AREA)


def glyphs(img: np.ndarray, cal: dict) -> list[np.ndarray]:
    return [letter_glyph(img, cx, cy, cal["tile_size"]) for cx, cy in cal["tile_centers"]]


def seed_templates(img: np.ndarray, cal: dict, letters: str) -> dict[str, np.ndarray]:
    acc: dict[str, list[np.ndarray]] = {}
    for ch, gl in zip(letters.upper(), glyphs(img, cal), strict=True):
        acc.setdefault(ch, []).append(gl)
    return {ch: np.mean(v, axis=0) for ch, v in acc.items()}


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a - a.mean(), b - b.mean()
    d = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d else 0.0


def read_letters(img: np.ndarray, cal: dict, templates: dict[str, np.ndarray]):
    """Returns (letters, per-tile margin between best and second-best match)."""
    out, margins = [], []
    for gl in glyphs(img, cal):
        scores = sorted(((_ncc(gl, t), ch) for ch, t in templates.items()), reverse=True)
        out.append(scores[0][1])
        margins.append(scores[0][0] - (scores[1][0] if len(scores) > 1 else 0.0))
    return "".join(out), margins


def save_templates(templates: dict[str, np.ndarray], path: str | Path) -> None:
    np.savez_compressed(path, **templates)


def load_templates(path: str | Path) -> dict[str, np.ndarray]:
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


# ---- full calibration -------------------------------------------------------


def calibrate(board_img: np.ndarray, end_img: np.ndarray | None = None) -> dict:
    h, w = board_img.shape[:2]
    cal: dict = {"version": f"iphone-{w}x{h}@1", "width": w, "height": h}
    cal.update(detect_grid(board_img))
    s = cal["tile_size"]
    cal["sample_rects"] = [sample_rect(cx, cy, s) for cx, cy in cal["tile_centers"]]
    cal["resting_rgb"] = np.mean(tile_samples(board_img, cal), axis=0).round(1).tolist()
    cal.update(find_banner(board_img))
    by = cal["roi_banner"][1] + cal["roi_banner"][3]
    cal["roi_timer"] = find_timer(board_img, by - 10)
    if end_img is not None:
        cal.update(find_end_layout(end_img))
    return cal


def save_calibration(cal: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(cal, indent=1) + "\n")


def load_calibration(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def scaled(cal: dict, factor: float, origin: tuple[float, float] = (0.0, 0.0)) -> dict:
    """Grid part of a calibration mapped into a crop/rescale: p' = (p - origin) * factor."""
    ox, oy = origin
    return {
        "tile_centers": [[(x - ox) * factor, (y - oy) * factor] for x, y in cal["tile_centers"]],
        "tile_size": cal["tile_size"] * factor,
    }
