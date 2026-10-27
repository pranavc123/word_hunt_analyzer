"""S3.T7 fixes: tile order within a frame, letter self-correction, one extra acceptance."""

import json
from pathlib import Path

import pytest

from whcore.pipeline import _evaluate, _try_dropping, _try_letter_fixes
from whcore.solver import load_trie, solve
from whcore.words import candidates

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures"
LABELS = json.loads((FIX / "expected/labels.json").read_text())
NAME = "session1_b00_played"
TRUTH = LABELS[NAME]["boards"][0]
RECORD = next(r for r in json.loads((FIX / f"expected/{NAME}.json").read_text())["records"])
ROWS = [tuple(v) for v in TRUTH["visible"]]


@pytest.fixture(scope="module")
def yawl():
    return load_trie(ROOT / "dictionaries/yawl.txt")


def test_baseline_fixture_reconciles(yawl):
    ev = _evaluate(
        TRUTH["letters"], RECORD["attempts"], ROWS, TRUTH["end_words"], TRUTH["end_score"], yawl
    )
    assert ev["rec"]["verified"]


def test_tiles_recorded_out_of_order_resolve_to_the_word(yawl):
    sol = solve(TRUTH["letters"].lower(), yawl)
    word = next(w for w, i in sol.items() if len(w) == 6)
    path = sol[word]["best_path"]
    shuffled = [path[1], path[0]] + path[2:]  # two tiles lit in one frame, index order
    top = candidates(shuffled, sol, TRUTH["letters"].lower())[0]
    assert top.word == word and top.cost == 1


def test_misread_letter_is_corrected_by_end_screen_words(yawl):
    letters = TRUTH["letters"]
    sol = solve(letters.lower(), yawl)
    vis = [w.lower() for w, _ in ROWS]
    # corrupt a tile used by visible words
    i = next(i for i in range(16) if sum(letters[i].lower() in w for w in vis) >= 3)
    wrong = "Q" if letters[i] != "Q" else "Z"
    bad = letters[:i] + wrong + letters[i + 1 :]
    ranked = [[(c, 0.9)] for c in bad]
    ranked[i] = [(wrong, 0.62), (letters[i], 0.60)]
    margins = [0.2] * 16
    margins[i] = 0.02
    base = _evaluate(bad, RECORD["attempts"], ROWS, TRUTH["end_words"], TRUTH["end_score"], yawl)
    assert not base["rec"]["verified"] and sol
    ev, fixed, note = _try_letter_fixes(
        bad,
        ranked,
        margins,
        RECORD["attempts"],
        ROWS,
        TRUTH["end_words"],
        TRUTH["end_score"],
        yawl,
        base,
    )
    assert fixed == letters and ev["rec"]["verified"] and f"tile {i}" in note


def test_one_extra_acceptance_is_dropped(yawl):
    attempts = [dict(a) for a in RECORD["attempts"]]
    fake = next(
        a for a in attempts if a["release_state"] == "not_a_word" and len(a["tiles_seen"]) == 3
    )
    fake.update(
        release_state="valid_new", confidence=0.5
    )  # colour said no, a WORDS misread said yes
    base = _evaluate(TRUTH["letters"], attempts, ROWS, TRUTH["end_words"], TRUTH["end_score"], yawl)
    assert not base["rec"]["verified"]
    ev, kept, note = _try_dropping(
        TRUTH["letters"], attempts, ROWS, TRUTH["end_words"], TRUTH["end_score"], yawl, base
    )
    assert ev["rec"]["verified"]
    dropped = int(note.split()[1])
    # any low-confidence acceptance may be the extra one; the reconciled board is what matters
    assert next(a for a in attempts if a["seq"] == dropped).get("confidence", 1.0) < 1.0


def test_two_stacked_views_vote_per_tile():
    import cv2
    import numpy as np

    from whcore.calibration import load_calibration
    from whcore.pipeline import read_board_letters

    cal = load_calibration(FIX / "calibration/iphone-1206x2622.json")
    phone = LABELS[NAME]["phone_crops"]["board"]["file"]
    one = cv2.imread(str(FIX / phone), cv2.IMREAD_GRAYSCALE)
    assert read_board_letters(one, cal)[0] == TRUTH["letters"]
    # the later look has a dark smear across tile 5 (e.g. a banner or finger path); voting with the
    # clean first look still reads every tile
    smeared = one.copy()
    h = one.shape[0] // 4
    smeared[h + 10 : 2 * h - 10, h + 10 : 2 * h - 10] = 40
    letters, margins = read_board_letters(np.vstack([one, smeared]), cal)
    assert letters == TRUTH["letters"]
    assert len(margins) == 16
