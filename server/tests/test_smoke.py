import json
from pathlib import Path

import whcore

ROOT = Path(__file__).resolve().parents[2]


def test_import():
    assert whcore.__doc__


def test_fixtures_present():
    board = json.loads((ROOT / "fixtures/boards/img0717.json").read_text())
    assert len(board["letters"]) == 16
    assert len(board["top15"]) == 15
    words = (ROOT / "fixtures/words_small.txt").read_text().split()
    assert 300 <= len(words) <= 500
    assert {w for w, _ in board["top15"]} <= {w.upper() for w in words}
