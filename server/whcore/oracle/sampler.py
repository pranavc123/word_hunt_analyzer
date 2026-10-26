"""Per-frame numeric sampling (PLAN §2.1): pixels → numbers. Mirrors the phone sampler.

The record layout is the Swift contract; see fixtures/samples/README.md.
"""

from __future__ import annotations

import math

import numpy as np

ROI_KEYS = (
    "roi_banner",
    "roi_banner_words",
    "roi_banner_score",
    "roi_timer",
    "roi_end_banner",
    "roi_end_list",
)
PROFILE_BINS = 64


def columns() -> list[str]:
    cols = ["frame", "t_ms"]
    cols += [f"t{i}_{c}" for i in range(16) for c in "rgb"]
    for k in ROI_KEYS:
        name = k.removeprefix("roi_")
        cols += [f"{name}_{c}" for c in "rgb"] + [f"{name}_std"]
    cols += [f"p{i}" for i in range(PROFILE_BINS)]
    cols += ["words", "list_shift"]
    return cols


def _rect(img: np.ndarray, rect) -> np.ndarray:
    x, y, w, h = rect
    return img[y : y + h, x : x + w]


def sample_frame(img: np.ndarray, cal: dict) -> list[float]:
    """Values in `columns()` order, without frame and t_ms. img: HxWx3 uint8 RGB."""
    out: list[float] = []
    for rect in cal["sample_rects"]:
        out += _rect(img, rect).reshape(-1, 3).mean(0).tolist()
    for k in ROI_KEYS:
        px = _rect(img, cal[k]).reshape(-1, 3)
        out += px.mean(0).tolist() + [float(px.mean(1).std())]
    gray_rows = img[:, ::4].mean(axis=(1, 2))  # row means of every 4th column
    out += [float(b.mean()) for b in np.array_split(gray_rows, PROFILE_BINS)]
    return out


class Sampler:
    """Stateful per-frame sampler: the stateless means of `sample_frame`, plus the live WORDS count
    (board frames only) and the all-words scroll shift (all-words frames only, with a velocity
    prior). Unavailable values are NaN."""

    def __init__(self, cal: dict, digits: dict, classify=None):
        from .screens import classify_row

        self.cal, self.digits = cal, digits
        self.classify = classify or classify_row
        self.prev_profile: np.ndarray | None = None
        self.velocity = 0

    def sample(self, img: np.ndarray) -> list[float]:
        from ..allwords import estimate_shift, profile
        from ..letters import gray_roi, read_number

        base = sample_frame(img, self.cal)
        row = dict(zip(columns()[2:-2], base, strict=True))
        screen = self.classify(row)
        words = math.nan
        if screen == "board":
            value, _ = read_number(gray_roi(img, self.cal["roi_banner_words"]), self.digits)
            words = float(value) if value is not None else math.nan
        shift = math.nan
        if screen == "all_words":
            prof = profile(img)
            if self.prev_profile is not None:
                s, _ = estimate_shift(self.prev_profile, prof, self.velocity)
                self.velocity, shift = s, float(s)
            self.prev_profile = prof
        else:
            self.prev_profile, self.velocity = None, 0
        return base + [words, shift]


def scale_calibration(cal: dict, width: int, height: int) -> dict:
    """Rescale pixel coordinates when a recording's size differs from the calibration's."""
    if (width, height) == (cal["width"], cal["height"]):
        return cal
    sx, sy = width / cal["width"], height / cal["height"]

    def r(rect):
        x, y, w, h = rect
        return [round(x * sx), round(y * sy), max(1, round(w * sx)), max(1, round(h * sy))]

    out = dict(cal, width=width, height=height)
    out["sample_rects"] = [r(x) for x in cal["sample_rects"]]
    out["tile_centers"] = [[x * sx, y * sy] for x, y in cal["tile_centers"]]
    out["tile_size"] = cal["tile_size"] * sx
    for k in ROI_KEYS:
        out[k] = r(cal[k])
    return out


def tile_matrix(rows) -> np.ndarray:
    """N×16×3 tile RGB from samples rows (dicts or a DataFrame-like with column access)."""
    cols = [f"t{i}_{c}" for i in range(16) for c in "rgb"]
    return np.stack([np.asarray(rows[c], dtype=float) for c in cols], axis=-1).reshape(-1, 16, 3)


def dominant_tile_colour(tiles: np.ndarray, bin_size: int = 6) -> list[float]:
    """Median RGB of the most common tile colour (the resting state dominates any session)."""
    flat = tiles.reshape(-1, 3)
    keys, inv, counts = np.unique(
        (flat // bin_size).astype(int), axis=0, return_inverse=True, return_counts=True
    )
    centre = flat[inv.ravel() == counts.argmax()].mean(0)
    near = flat[np.abs(flat - centre).max(1) <= 12]
    return np.median(near, axis=0).round(1).tolist()
