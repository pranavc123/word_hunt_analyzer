"""S1.T4: the server-side modules on committed fixtures only (no $WH_DATA)."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from whcore import allwords as aw
from whcore.calibration import load_calibration, load_rgb, scaled
from whcore.letters import default_templates, read_letters
from whcore.reconcile import reconcile, snap_visible
from whcore.solver import load_trie, solve
from whcore.words import build_words

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures"
CAL = load_calibration(FIX / "calibration/iphone-1206x2622.json")
LABELS = json.loads((FIX / "expected/labels.json").read_text())
WITH_CROP = [k for k, v in LABELS.items() if "board_crop" in v]
PLAYED = [k for k, v in LABELS.items() if v["boards"][0]["status"] == "played"]


@pytest.fixture(scope="module")
def yawl():
    return load_trie(ROOT / "dictionaries/yawl.txt")


@pytest.mark.parametrize("name", WITH_CROP)
def test_read_letters_on_board_crops(name):
    lab = LABELS[name]
    img = load_rgb(FIX / lab["board_crop"]["file"])
    letters, conf = read_letters(img, scaled(CAL, 1.0, tuple(lab["board_crop"]["origin"])))
    assert letters == lab["boards"][0]["letters"]
    assert len(conf) == 16 and min(conf) > 0.02


@pytest.mark.parametrize("name", PLAYED)
def test_words_and_reconciliation_match_s0(name, yawl):
    lab = LABELS[name]
    truth = lab["boards"][0]
    expected = json.loads((FIX / "expected" / f"{name}.json").read_text())
    board = next(r for r in expected["records"] if r["kind"] == "board")
    letters = truth["letters"].lower()
    sol = solve(letters, yawl)
    observed = [a["tiles_seen"] for a in board["attempts"] if a["release_state"] == "valid_new"]
    oov = {"".join(letters[i] for i in o) for o in observed}
    visible = snap_visible([tuple(v) for v in truth["visible"]], set(sol) | oov)
    words = build_words(board["attempts"], letters, sol, truth["end_score"],
                        {v["word"] for v in visible if v["word"]})  # fmt: skip
    got = [w["word"] for w in words]
    rec = reconcile(got, truth["end_words"], truth["end_score"], visible)
    assert rec["verified"] == truth["verified"]
    assert rec["checks"]["count"] and rec["checks"]["score"]


def test_allwords_rows_from_list_crops():
    name = next(k for k, v in LABELS.items() if "list_crops" in v)
    lab = LABELS[name]
    first, last = (cv2.imread(str(FIX / f), cv2.IMREAD_GRAYSCALE) for f in lab["list_crops"])
    top = aw.parse_band_rows(first, default_templates("digits"))
    assert len(top) >= 25
    lengths = [aw.POINTS_TO_LEN.get(r.points) for r in top]
    assert None not in lengths and lengths == sorted(lengths, reverse=True)
    assert lengths[0] == max(int(n) for n in lab["all_words"]["counts_by_length"])
    found = [aw.ocr_word(r.word_crop) for r in top if r.kind == "found"]
    revealed = lab["all_words"]["revealed"]
    assert found and all(w in revealed for w in found if len(w) >= 4)
    bottom = aw.parse_band_rows(last, default_templates("digits"))
    assert bottom[-1].y < last.shape[0] - 2 * aw.PITCH  # end of the list is visible
    assert {aw.POINTS_TO_LEN[r.points] for r in bottom} == {3}


def test_stitch_scrolling_frames_built_from_a_crop():
    name = next(k for k, v in LABELS.items() if "list_crops" in v)
    crop = cv2.imread(str(FIX / LABELS[name]["list_crops"][0]), cv2.IMREAD_GRAYSCALE)
    digits = default_templates("digits")
    x, y, w, h = aw.LIST_BAND_RECT
    panel = int(crop[:, 20:30].mean())
    content = cv2.copyMakeBorder(crop, 0, 600, 0, 0, cv2.BORDER_CONSTANT, value=panel)

    def frame(top):  # a full screen whose list band shows content[top:]
        out = np.full((CAL["height"], CAL["width"], 3), panel, np.uint8)
        out[y : y + h, x : x + w] = cv2.cvtColor(content[top : top + h], cv2.COLOR_GRAY2RGB)
        return out

    frames = [frame(t) for t in (0, 0, 120, 240, 240, 400, 400)]
    cap = aw.stitch(frames, digits)
    assert cap.shifts == [0, 120, 120, 0, 160, 0]
    single = aw.parse_band_rows(crop, digits)
    summary = aw.summarise(cap)
    assert sum(summary["counts_by_length"].values()) == len(single)
    assert summary["lengths_non_increasing"]
