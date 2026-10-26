"""Screen classification + board segmentation from numeric samples (S0.T7, PLAN §2.2–2.5).

Thresholds are in the video colour domain (BT.709 screen recordings, see measurements.md).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

SCREENS = ("board", "end", "all_words", "other")


def _mean(row, key: str) -> float:
    return (row[f"{key}_r"] + row[f"{key}_g"] + row[f"{key}_b"]) / 3


def classify_row(row) -> str:
    """row: mapping with samples.csv columns (floats)."""
    banner, banner_std = _mean(row, "banner"), row["banner_std"]
    timer = _mean(row, "timer")
    # board: white banner with avatar + text, dark-green timer pill below it
    if banner > 185 and banner_std > 70 and timer < 112:
        return "board"
    # end: green top, white player banner with text, dark-green word list
    if (
        banner < 115
        and banner_std < 25
        and row["end_banner_std"] > 60
        and _mean(row, "end_list") < 110
    ):
        return "end"
    if is_all_words(row):
        return "all_words"
    return "other"


def is_all_words(row) -> bool:
    """VIEW ALL WORDS: pinned REVEAL ALL header; the points column crosses the timer ROI."""
    banner, timer = _mean(row, "banner"), _mean(row, "timer")
    return (
        105 < banner < 135 and 38 < row["banner_std"] < 62 and timer > 140 and row["timer_std"] > 60
    )


def classify(rows) -> list[str]:
    return [classify_row(r) for r in rows]


def smooth(labels: list[str], min_run: int = 3) -> list[str]:
    """Absorb runs shorter than min_run frames into the preceding label (transitions, flashes)."""
    out = list(labels)
    i = 0
    while i < len(out):
        j = i
        while j < len(out) and out[j] == out[i]:
            j += 1
        if j - i < min_run and i > 0:
            out[i:j] = [out[i - 1]] * (j - i)
        i = j
    return out


def runs(labels: list[str]) -> list[tuple[str, int, int]]:
    """(label, first, last) inclusive frame-index runs."""
    out, i = [], 0
    while i < len(labels):
        j = i
        while j + 1 < len(labels) and labels[j + 1] == labels[i]:
            j += 1
        out.append((labels[i], i, j))
        i = j + 1
    return out


@dataclass
class Board:
    seq: int
    first: int
    last: int
    t_start_ms: int
    t_end_ms: int
    view_ms: int
    status: str  # played | skipped
    end_first: int | None = None
    end_last: int | None = None
    end_t_ms: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def segment_boards(
    labels: list[str], t_ms: list[int], merge_gap_ms: int = 700, end_within_ms: int = 4000
) -> list[Board]:
    """Board = run of `board` frames (gaps < merge_gap_ms merged). Played = an `end` run starts
    within end_within_ms of the board's last frame and before the next board."""
    board_runs = [(a, b) for lab, a, b in runs(labels) if lab == "board"]
    merged: list[list[int]] = []
    for a, b in board_runs:
        if merged and t_ms[a] - t_ms[merged[-1][1]] < merge_gap_ms:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    end_runs = [(a, b) for lab, a, b in runs(labels) if lab == "end"]
    boards = []
    for k, (a, b) in enumerate(merged):
        nxt = merged[k + 1][0] if k + 1 < len(merged) else len(labels)
        end = next(
            (
                (ea, eb)
                for ea, eb in end_runs
                if b < ea < nxt and t_ms[ea] - t_ms[b] <= end_within_ms
            ),
            None,
        )
        boards.append(
            Board(
                seq=k,
                first=a,
                last=b,
                t_start_ms=t_ms[a],
                t_end_ms=t_ms[b],
                view_ms=t_ms[b] - t_ms[a],
                status="played" if end else "skipped",
                end_first=end[0] if end else None,
                end_last=end[1] if end else None,
                end_t_ms=t_ms[(end[0] + end[1]) // 2] if end else None,
            )
        )
    return boards


def all_words_runs(labels: list[str], t_ms: list[int], merge_gap_ms: int = 1500):
    """(first, last) frame runs of the all-words screen, merging short interruptions."""
    out: list[list[int]] = []
    for lab, a, b in runs(labels):
        if lab != "all_words":
            continue
        if out and t_ms[a] - t_ms[out[-1][1]] < merge_gap_ms:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [tuple(x) for x in out]


def tile_state_counts(rows, resting) -> np.ndarray:
    """Number of tiles within ±12 of the resting colour, per row."""
    cols = [f"t{i}_{c}" for i in range(16) for c in "rgb"]
    t = np.array([[r[c] for c in cols] for r in rows], float).reshape(-1, 16, 3)
    return (np.abs(t - np.asarray(resting)).max(2) <= 12).sum(1)
