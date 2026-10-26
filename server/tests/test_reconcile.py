import json
from pathlib import Path

import numpy as np

from whcore.calibration import load_calibration, load_rgb
from whcore.reconcile import read_end_list, reconcile, snap, snap_visible
from whcore.solver import build_trie, load_trie, solve
from whcore.words import align_cost, resolve_board

ROOT = Path(__file__).resolve().parents[2]
CAL = load_calibration(ROOT / "fixtures/calibration/iphone-1206x2622.json")
BOARD = json.loads((ROOT / "fixtures/boards/img0717.json").read_text())
LETTERS = BOARD["letters"].lower()  # lcme / orsi / etra / tdim
SOL = solve(LETTERS, load_trie(ROOT / "fixtures/words_small.txt"))


def test_img0718_visible_words_and_points():
    crop = load_rgb(ROOT / "fixtures/crops/img0718_list.jpg")
    img = np.zeros((CAL["height"], CAL["width"], 3), np.uint8)
    x, y, w, h = CAL["roi_end_list"]
    img[y : y + h, x : x + w] = crop
    assert read_end_list(img, CAL) == [tuple(r) for r in BOARD["top15"]]


def test_snap_uses_points_length():
    assert snap("SALE", ["sale", "sants", "sated"], length=5)[0] in {"sants", "sated"}
    assert snap("MASTFR", SOL.keys())[0] == "master"
    vis = snap_visible([("CLOTTERS", 2200), ("MASTER", 1400), ("RIDERS", None)], SOL.keys())
    assert [v["word"] for v in vis] == ["clotters", "master", "riders"]
    assert [v["points_ok"] for v in vis] == [True, True, None]


def test_align_cost():
    assert align_cost([1, 2, 3], [1, 2, 3, 4]) == 1  # missed last tile
    assert align_cost([1, 9, 2], [1, 2]) == 1  # spurious tile


def path(word):
    return SOL[word]["best_path"]


def test_resolve_board_repairs_and_oov():
    master, mister, cotter = path("master"), path("mister"), path("cotter")
    observed = [
        master,  # exact
        mister[:-1],  # missed the last tile → mister
        cotter[:3] + [cotter[3]] + cotter[4:],  # exact
        [1, 5, 10],  # c-r-r: contiguous, not in the word list → OOV candidate
    ]
    # "miste" fits mist (extra e) or mister/misted (missing tile); the score rules out mist
    res = resolve_board(observed, SOL, LETTERS, end_score=1400 * 3 + 100)
    words = [r.chosen.word for r in res]
    assert words[0] == "master" and words[2] == "cotter"
    assert words[1] in {"mister", "misted"}  # same cost and points: either fits
    assert res[3].chosen.oov and words[3] == "crr"


def test_resolve_board_uses_total_score_to_pick():
    sol = solve(LETTERS, build_trie(["mite", "miter"]))
    mit = sol["mite"]["best_path"][:3]
    # observed "mit": mite (missing 1 tile) or miter (missing 2) — the end score decides
    assert resolve_board([mit], sol, "", end_score=400)[0].chosen.word == "mite"
    assert resolve_board([mit], sol, "", end_score=800)[0].chosen.word == "miter"


def test_reconcile_checks():
    vis = snap_visible([("MASTER", 1400)], SOL.keys())
    ok = reconcile(["master", "mister"], 2, 2800, vis)
    assert ok["verified"]
    bad = reconcile(["master", "master"], 2, 2800, vis)
    assert not bad["verified"] and not bad["checks"]["count"]
    missing = reconcile(["mister"], 1, 1400, vis)
    assert missing["visible_missing"] == ["master"]
