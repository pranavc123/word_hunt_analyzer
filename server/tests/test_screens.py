import csv
import gzip
import os
from pathlib import Path

import pytest

from whcore.oracle.screens import (
    all_words_runs,
    classify,
    classify_row,
    runs,
    segment_boards,
    smooth,
)

ROOT = Path(__file__).resolve().parents[2]
WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))


def row(**kw):
    """Minimal sample row; each key sets r=g=b for an ROI, or a *_std value."""
    base = {"banner": 60, "banner_std": 10, "timer": 60, "timer_std": 5,
            "end_banner": 100, "end_banner_std": 5, "end_list": 150}  # fmt: skip
    base.update(kw)
    out = {}
    for k, v in base.items():
        if k.endswith("_std"):
            out[k] = v
        else:
            out.update({f"{k}_r": v, f"{k}_g": v, f"{k}_b": v})
    return out


BOARD = row(banner=205, banner_std=85, timer=92, timer_std=54)
END = row(banner=87, banner_std=10, end_banner=160, end_banner_std=82, end_list=70)
ALL = row(banner=120, banner_std=50, timer=158, timer_std=72)
CHAT = row(banner=175, banner_std=62, timer=228, timer_std=48)


def test_classify_row():
    assert classify_row(BOARD) == "board"
    assert classify_row(END) == "end"
    assert classify_row(ALL) == "all_words"
    assert classify_row(CHAT) == "other"


def test_smooth_and_runs():
    labels = ["board"] * 5 + ["other"] * 2 + ["board"] * 5
    assert smooth(labels) == ["board"] * 12
    assert runs(["a", "a", "b"]) == [("a", 0, 1), ("b", 2, 2)]


def test_segment_played_and_skipped():
    seq = [CHAT] * 30 + [BOARD] * 90 + [END] * 30 + [CHAT] * 150 + [BOARD] * 20 + [CHAT] * 150
    seq += [ALL] * 60 + [CHAT] * 10
    labels = smooth(classify(seq))
    t = [round(i * 1000 / 30) for i in range(len(seq))]
    boards = segment_boards(labels, t)
    assert [b.status for b in boards] == ["played", "skipped"]
    assert boards[0].end_first == 120 and boards[1].view_ms == t[319] - t[300]
    assert all_words_runs(labels, t) == [(470, 529)]


def load(name):
    with gzip.open(WH_DATA / "frames" / name / "samples.csv.gz", "rt") as f:
        return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]


@pytest.mark.skipif(
    not (WH_DATA / "frames/session1/samples.csv.gz").exists(), reason="samples not extracted"
)
def test_session1_segmentation():
    rows = load("session1")
    t = [int(r["t_ms"]) for r in rows]
    labels = smooth(classify(rows))
    boards = segment_boards(labels, t)
    played = [b for b in boards if b.status == "played"]
    assert len(boards) == 21 and len(played) == 6  # 10-min session (measurements.md)
    assert all(b.end_first is not None for b in played)
    assert all(80_000 <= b.view_ms <= 82_000 for b in played)  # 80 s timer
    assert not all_words_runs(labels, t)
