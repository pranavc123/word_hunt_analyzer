import json
import os
from pathlib import Path

import numpy as np
import pytest
from whcore import calibration as cb

ROOT = Path(__file__).resolve().parents[2]
WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
LETTERS = json.loads((ROOT / "fixtures/boards/img0717.json").read_text())["letters"]
CAL = cb.load_calibration(ROOT / "fixtures/calibration/iphone-1206x2622.json")
CROP = cb.load_rgb(ROOT / "fixtures/crops/img0717_tiles.png")
BOARD_PNG = WH_DATA / "recordings/IMG_0717.PNG"
END_PNG = WH_DATA / "recordings/IMG_0718.PNG"
needs_screens = pytest.mark.skipif(not BOARD_PNG.exists(), reason="screenshots not in $WH_DATA")


def assert_regular(centres, max_cv=0.03):
    c = np.array(centres).reshape(4, 4, 2)
    dx = np.diff(c[..., 0], axis=1).ravel()
    dy = np.diff(c[..., 1], axis=0).ravel()
    for d in (dx, dy):
        assert d.min() > 0
        assert d.std() / d.mean() < max_cv
    assert abs(dx.mean() - dy.mean()) / dx.mean() < max_cv


def test_calibration_file():
    assert (CAL["width"], CAL["height"]) == (1206, 2622)
    assert len(CAL["tile_centers"]) == 16 and len(CAL["sample_rects"]) == 16
    assert_regular(CAL["tile_centers"])
    assert_regular(CAL["raw_centers"])
    r, g, b = CAL["resting_rgb"]
    assert r > g > b and r > 200  # beige
    for k in (
        "roi_banner",
        "roi_banner_words",
        "roi_banner_score",
        "roi_timer",
        "roi_end_banner",
        "roi_end_list",
    ):
        x, y, w, h = CAL[k]
        assert 0 <= x and x + w <= 1206 and 0 <= y and y + h <= 2622 and w > 0 and h > 0
    # banner above timer above board
    assert CAL["roi_banner"][1] < CAL["roi_timer"][1] < CAL["tile_centers"][0][1]
    assert CAL["end_list_rows"] == 15


def test_crop_grid_and_letters():
    grid = cb.detect_grid(CROP)
    assert_regular(grid["raw_centers"])
    assert abs(grid["tile_size"] - CAL["tile_size"] / 2) < 3
    templates = cb.seed_templates(CROP, grid, LETTERS)
    read, margins = cb.read_letters(CROP, grid, templates)
    assert read == LETTERS
    assert min(margins) > 0.05


@needs_screens
def test_full_screens_reproduce_calibration():
    board = cb.load_rgb(BOARD_PNG)
    cal = cb.calibrate(board, cb.load_rgb(END_PNG) if END_PNG.exists() else None)
    assert np.abs(np.array(cal["tile_centers"]) - CAL["tile_centers"]).max() < 2
    templates = cb.seed_templates(board, cal, LETTERS)
    assert cb.read_letters(board, cal, templates)[0] == LETTERS
    # full-res seed templates also read the 0.5x crop (glyphs are scale-normalised)
    assert cb.read_letters(CROP, cb.detect_grid(CROP), templates)[0] == LETTERS
    # resting tile samples agree with the stored colour within ±12
    assert np.abs(np.array(cb.tile_samples(board, CAL)) - CAL["resting_rgb"]).max() <= 12
