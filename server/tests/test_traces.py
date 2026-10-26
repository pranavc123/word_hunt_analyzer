import json
import os
from pathlib import Path

import numpy as np
import pytest

from whcore.oracle.traces import STATES, path_is_contiguous, segment_attempts, tile_codes

ROOT = Path(__file__).resolve().parents[2]
WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
REST, W, G, Y = (STATES[k] for k in ("resting", "white", "green", "yellow"))
MID = (215.0, 251.0, 215.0)  # newest tile half-way white→green


def frames(*specs):
    """Each spec: {tile: rgb}; other tiles resting."""
    out = np.tile(np.array(REST), (len(specs), 16, 1))
    for i, spec in enumerate(specs):
        for tile, rgb in spec.items():
            out[i, tile] = rgb
    return out


def test_tile_codes():
    codes = tile_codes(frames({0: W, 1: G, 2: Y, 3: MID}))
    assert "".join(codes[0][:5]) == "WGY?R"


def test_attempts_release_and_fresh_transitional_tile():
    seq = frames(
        {},
        {0: W},
        {0: W, 1: W},
        {0: G, 1: G, 2: MID},
        {2: MID},  # valid word 0-1-2, fade
        {},
        {5: W},
        {5: Y, 6: Y},
        {},
        {},  # already found 5-6 (swipes are ≥ 2 frames apart)
        {9: W},
        {9: W, 10: W},
        {},  # not a word
    )
    t = list(range(0, 33 * len(seq), 33))
    att = segment_attempts(tile_codes(seq), t)
    assert [a.tiles_seen for a in att] == [[0, 1, 2], [5, 6], [9, 10]]
    assert [a.release_state for a in att] == ["valid_new", "already_found", "not_a_word"]


def test_contiguous():
    assert path_is_contiguous([0, 5, 10, 15])
    assert not path_is_contiguous([0, 2])


@pytest.mark.skipif(not (WH_DATA / "labels/traces.json").exists(), reason="no traces")
def test_accepted_matches_end_words():
    boards = json.loads((WH_DATA / "labels/traces.json").read_text())
    assert boards
    for b in boards:
        accepted = sum(a["release_state"] == "valid_new" for a in b["attempts"])
        assert accepted == b["end_words"], (b["recording"], b["seq"])
        assert b["words_jumps_outside"] == 0
