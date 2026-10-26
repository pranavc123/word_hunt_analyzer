import json
import os
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from whcore.allwords import (
    Capture,
    Slot,
    estimate_shift,
    list_order,
    match_revealed,
    slot_evidence,
    summarise,
)

ROOT = Path(__file__).resolve().parents[2]
WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))


def test_estimate_shift_recovers_scroll():
    rng = np.random.default_rng(0)
    content = rng.normal(100, 30, 6000)
    prev, cur = content[1000:3000], content[1240:3240]  # scrolled down 240 px
    assert estimate_shift(prev, cur, predicted=200)[0] == 240


def test_estimate_shift_uses_prediction_on_repeating_rows():
    rows = np.tile(np.r_[np.full(30, 200.0), np.full(31, 60.0)], 80)  # identical 61 px rows
    prev, cur = rows[0:2000], rows[122:2122]
    s, _ = estimate_shift(prev, cur, predicted=120)
    assert s == 122
    s, _ = estimate_shift(prev, cur, predicted=0)
    assert s % 61 == 0  # ambiguous without the prediction, but row-aligned


def slot(kind, pts, word=None):
    s = Slot()
    s.kinds[kind] += 1
    s.points[pts] += 1
    s.word = word
    return s


def test_summarise_counts_and_checks():
    slots = [slot("masked", 1800), slot("found", 1400, "master"), slot("masked", 1400),
             slot("found", 800, "mites"), slot("masked", 100)]  # fmt: skip
    cap = Capture(dict(enumerate(slots)), [0], [0.0], [False], True, [0])
    s = summarise(cap)
    assert s["counts_by_length"] == {7: 1, 6: 2, 5: 1, 3: 1}
    assert s["masked_counts_by_length"] == {7: 1, 6: 1, 3: 1}
    assert s["lengths_non_increasing"] and s["found_alphabetical"]
    assert s["status"] == "complete" and s["complete_down_to"] == 3


def test_match_revealed_prefix_with_ocr_noise():
    a = {"id": "a", "t": 1, "words": ["master", "mister", "mites", "rat", "tar"]}
    b = {"id": "b", "t": 2, "words": ["cotter", "lotter", "rat"]}
    revealed = list_order(a["words"])[:4]
    assert match_revealed(revealed, [a, b])[:2] == ("matched", "a")
    noisy = revealed[:3] + ["xxx"]
    assert match_revealed(noisy, [a, b], min_frac=0.7)[:2] == ("matched", "a")
    assert match_revealed(["zzz"], [a, b])[0] == "unmatched"


def test_slot_evidence():
    solver = {"abed", "abet", "able", "ably", "acid"}
    accepted = {"abed", "acid"}
    rows = [(4, "found", "abed"), (4, "masked", None), (4, "masked", None), (4, "found", "acid")]
    ev = slot_evidence(rows, accepted, solver)
    # two masked rows between abed and acid, but three unfound solver words fit: no confirmation
    assert ev["confirmed"] == []
    rows = [(4, "found", "abed"), (4, "masked", None), (4, "found", "acid")]
    ev = slot_evidence(rows, accepted, solver - {"able", "ably"})
    assert ev["confirmed"] == ["abet"]
    rows = [(4, "found", "abed"), (4, "found", "acid")]
    assert slot_evidence(rows, accepted, solver)["rejected"] == ["abet", "able", "ably"]


@pytest.mark.skipif(not (WH_DATA / "labels/allwords.json").exists(), reason="no captures")
def test_captures_matched_to_their_boards():
    caps = json.loads((WH_DATA / "labels/allwords.json").read_text())
    matched = [c for c in caps if c["match_state"] == "matched"]
    assert len(matched) >= 3
    for c in matched:  # each allwords1 capture follows its own board
        assert c["board"] == f"{c['recording']}#{c['capture']}"
        diff = Counter(c["counts_by_length"]) - Counter(c["yawl_counts"])
        assert sum(diff.values()) <= 10  # game list ≈ YAWL
