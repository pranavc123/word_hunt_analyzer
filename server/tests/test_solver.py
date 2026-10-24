import json
import time
from pathlib import Path

import pytest

from whcore.scoring import word_points
from whcore.solver import ADJ, best_path, direction_changes, load_trie, max_points, normalise, solve

ROOT = Path(__file__).resolve().parents[2]
BOARD = json.loads((ROOT / "fixtures/boards/img0717.json").read_text())
LETTERS = BOARD["letters"]


@pytest.fixture(scope="module")
def yawl():
    return load_trie(ROOT / "dictionaries/yawl.txt")


@pytest.fixture(scope="module")
def enable():
    return load_trie(ROOT / "dictionaries/enable1.txt")


def test_scoring():
    assert [word_points(n) for n in range(3, 10)] == [100, 400, 800, 1400, 1800, 2200, 2600]
    assert word_points(16) == 1400 + 400 * 10
    with pytest.raises(ValueError):
        word_points(2)


def test_normalise():
    assert normalise(" Cat\n") == "cat"
    assert normalise("ab") is None
    assert normalise("don't") is None
    assert normalise("café") is None


def test_adjacency():
    assert sorted(ADJ[0]) == [1, 4, 5]
    assert len(ADJ[5]) == 8


def test_best_path():
    assert direction_changes([0, 1, 2, 3]) == 0
    assert best_path([[0, 5, 6], [0, 1, 2]]) == [0, 1, 2]


def timed_solve(trie):
    t = time.perf_counter()
    sol = solve(LETTERS, trie)
    return sol, time.perf_counter() - t


def test_yawl(yawl):
    sol, dt = timed_solve(yawl)
    assert len(sol) == 335
    assert max_points(sol) == 262_800
    assert {w.lower() for w, _ in BOARD["top15"]} <= sol.keys()
    for w, pts in BOARD["top15"]:
        assert sol[w.lower()]["points"] == pts
        path = sol[w.lower()]["best_path"]
        assert "".join(LETTERS[i] for i in path) == w
    assert dt < 0.1


def test_enable(enable):
    sol, dt = timed_solve(enable)
    assert len(sol) == 251
    assert max_points(sol) == 196_500
    assert not {"clotter", "clotters", "lotter", "lotters"} & sol.keys()
    assert dt < 0.1
