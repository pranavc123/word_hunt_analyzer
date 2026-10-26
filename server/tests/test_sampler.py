import csv
import gzip
import os
from pathlib import Path

import numpy as np
import pytest

from whcore.calibration import load_calibration
from whcore.oracle.sampler import (
    columns,
    dominant_tile_colour,
    sample_frame,
    scale_calibration,
    tile_matrix,
)

ROOT = Path(__file__).resolve().parents[2]
WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
CAL = load_calibration(ROOT / "fixtures/calibration/iphone-1206x2622.json")
SAMPLES = WH_DATA / "frames/session1/samples.csv.gz"


def test_sample_frame_shape_and_values():
    img = np.zeros((CAL["height"], CAL["width"], 3), np.uint8)
    img[...] = (10, 20, 30)
    vals = sample_frame(img, CAL)
    assert len(vals) == len(columns()) - 4  # Sampler adds words + list_shift
    assert vals[:3] == [10, 20, 30]


def test_scale_calibration():
    half = scale_calibration(CAL, CAL["width"] // 2, CAL["height"] // 2)
    assert half["sample_rects"][0][0] == round(CAL["sample_rects"][0][0] / 2)
    assert scale_calibration(CAL, CAL["width"], CAL["height"]) is CAL


def test_dominant_colour():
    tiles = np.full((100, 16, 3), (247.0, 209.0, 151.0))
    tiles[:10] = (126, 252, 126)
    assert dominant_tile_colour(tiles) == [247.0, 209.0, 151.0]


@pytest.mark.skipif(not SAMPLES.exists(), reason="session1 samples not extracted")
def test_session1_board_frames_match_video_resting():
    with gzip.open(SAMPLES, "rt") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 1000
    cols = {k: [float(r[k]) for r in rows] for k in columns() if k.startswith("t") and "_" in k}
    tiles = tile_matrix(cols)
    resting = np.abs(tiles - CAL["resting_rgb_video"]).max(2) <= 12
    # a known board frame: most frames have ≥12 resting tiles, and some have all 16
    assert (resting.sum(1) == 16).sum() > 100
    assert resting.mean() > 0.6


def test_sampler_reads_words_on_board_frames_only():
    import cv2

    from whcore.letters import load_templates
    from whcore.oracle.sampler import Sampler

    digits = load_templates(ROOT / "fixtures/templates/digits.npz")
    img = np.full((CAL["height"], CAL["width"], 3), 255, np.uint8)
    crop = cv2.imread(str(ROOT / "fixtures/crops/banner_words_64.png"), cv2.IMREAD_GRAYSCALE)
    x, y, w, h = CAL["roi_banner_words"]
    img[y : y + h, x : x + w] = crop[..., None]
    on_board = Sampler(CAL, digits, classify=lambda row: "board").sample(img)
    assert len(on_board) == len(columns()) - 2
    assert on_board[-2] == 64 and np.isnan(on_board[-1])
    elsewhere = Sampler(CAL, digits, classify=lambda row: "other").sample(img)
    assert np.isnan(elsewhere[-2])


def test_sampler_tracks_list_shift_on_all_words_frames():
    from whcore.allwords import LIST_Y0
    from whcore.oracle.sampler import Sampler

    rng = np.random.default_rng(1)
    tall = rng.integers(0, 255, (6000, CAL["width"], 3), dtype=np.uint8)
    frames = [tall[y0 : y0 + CAL["height"]] for y0 in (1000, 1100, 1250)]  # content moves up
    s = Sampler(CAL, {}, classify=lambda row: "all_words")
    shifts = [s.sample(f)[-1] for f in frames]
    assert np.isnan(shifts[0]) and shifts[1:] == [100, 150]
    assert LIST_Y0 > 0
