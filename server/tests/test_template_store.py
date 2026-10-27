import json
from pathlib import Path

import numpy as np

from whcore.calibration import detect_grid, load_rgb
from whcore.letters import read_board
from whcore.pipeline import process_board
from whcore.template_store import BASE_WEIGHT, TemplateStore

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures"
LETTERS = json.loads((FIX / "boards/img0717.json").read_text())["letters"]


def test_store_learns_from_known_boards(tmp_path):
    crop = load_rgb(FIX / "crops/img0717_tiles.jpg")
    grid = detect_grid(crop)
    store = TemplateStore(tmp_path / "t.npz")
    before = store.templates()["L"].copy()
    assert store.counts["L"] == BASE_WEIGHT
    assert store.add_board("b1", crop, grid, LETTERS)
    assert not store.add_board("b1", crop, grid, LETTERS)  # each board once
    assert store.counts["L"] == BASE_WEIGHT + 1 and store.counts["E"] == BASE_WEIGHT + 2
    store.save()
    again = TemplateStore(tmp_path / "t.npz")
    assert again.boards == {"b1"} and again.counts["E"] == BASE_WEIGHT + 2
    assert not np.allclose(again.templates()["L"], before)
    assert read_board(crop, grid, again.templates())[0] == LETTERS


def test_glimpse_skips_are_not_letter_fixes():
    rec = {"status": "skipped", "view_ms": 500, "attempts": []}
    out = process_board(rec, {}, {}, None, set())
    assert out["review_status"] == "skipped" and out["glimpse"]
    rec = dict(rec, view_ms=5000)
    assert process_board(rec, {}, {}, None, set())["review_status"] == "needs_letter_fix"
