"""Tile colour states + attempt (trace) segmentation from numeric samples (S0.T9, PLAN §2.4).

While dragging, selected tiles are white (no word yet), green (valid new word), yellow (already
found) or red (seen briefly on some non-words). The colour at release decides the outcome; the
newest tile animates white→colour and fades slowly after release, so mixed colours are
"transitional" and only count when a tile changes straight out of resting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

# RGB centroids in the video domain (measurements.md)
STATES = {
    "resting": (247.4, 209.3, 150.5),
    "white": (252.0, 252.0, 252.0),
    "green": (128.0, 250.0, 128.0),
    "yellow": (248.0, 248.0, 116.0),
    "red": (252.0, 140.0, 140.0),
}
CODES = {"resting": "R", "white": "W", "green": "G", "yellow": "Y", "red": "X"}
TOL = 22  # max per-channel distance to a centroid
RELEASE = {"G": "valid_new", "Y": "already_found"}  # anything else → not_a_word


def tile_codes(tiles: np.ndarray, states: dict | None = None) -> np.ndarray:
    """N×16×3 RGB → N×16 single-char codes (R/W/G/Y/X, or '?' for transitional)."""
    states = states or STATES
    names = [CODES[k] for k in states]
    cent = np.array(list(states.values()), float)
    d = np.abs(tiles[:, :, None, :] - cent[None, None]).max(3)
    codes = np.array(names)[d.argmin(2)]
    return np.where(d.min(2) <= TOL, codes, "?")


@dataclass
class Attempt:
    seq: int
    first: int  # frame index of first selected tile
    last: int  # last frame with a selection colour
    t_start_ms: int
    t_end_ms: int
    tiles_seen: list[int]
    release_state: str
    release_codes: str
    banner_words_after: int | None = None
    confidence: float = 1.0

    def as_dict(self) -> dict:
        return asdict(self)


SELECTED = set("WGYX")


def segment_attempts(
    codes: np.ndarray, t_ms, first: int = 0, last: int | None = None, gap: int = 1
):
    """Attempts within frames [first, last]. An attempt is a run of frames where any tile shows a
    selection colour (gaps ≤ `gap` frames bridged)."""
    last = len(codes) - 1 if last is None else last
    active = np.array([any(c in SELECTED for c in row) for row in codes[first : last + 1]])
    idx = np.where(active)[0] + first
    runs: list[list[int]] = []
    for i in idx:
        if runs and i - runs[-1][1] <= gap + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    attempts = []
    for k, (a, b) in enumerate(runs):
        seen: list[int] = []
        for i in range(a, b + 1):
            for tile, c in enumerate(codes[i]):
                if tile in seen:
                    continue
                fresh = c == "?" and i > 0 and codes[i - 1][tile] == "R"
                if c in SELECTED or (fresh and i > a):
                    seen.append(tile)
        rel = "".join(c for c in codes[b] if c in SELECTED)
        top = max("GYWX", key=rel.count) if rel else "W"
        conf = rel.count(top) / len(rel) if rel else 0.0
        attempts.append(
            Attempt(
                seq=k,
                first=a,
                last=b,
                t_start_ms=int(t_ms[a]),
                t_end_ms=int(t_ms[b]),
                tiles_seen=seen,
                release_state=RELEASE.get(top, "not_a_word"),
                release_codes=rel,
                confidence=round(conf, 3),
            )
        )
    return attempts


def adjacent(a: int, b: int) -> bool:
    return a != b and abs(a // 4 - b // 4) <= 1 and abs(a % 4 - b % 4) <= 1


def path_is_contiguous(tiles: list[int]) -> bool:
    return all(adjacent(a, b) for a, b in zip(tiles, tiles[1:], strict=False))
