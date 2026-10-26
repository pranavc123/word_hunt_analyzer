import json
from pathlib import Path

import cv2
import pytest

from whcore import letters as lt
from whcore.calibration import detect_grid, load_rgb

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures"
LETTERS = lt.load_templates(FIX / "templates/letters.npz")
DIGITS = lt.load_templates(FIX / "templates/digits.npz")


def test_templates_cover_digits_and_common_letters():
    assert sorted(DIGITS) == list("0123456789")
    assert set("AEIOURSTLN") <= set(LETTERS)


def test_reads_img0717_crop_with_video_templates():
    crop = load_rgb(FIX / "crops/img0717_tiles.jpg")  # 0.5x PNG crop; templates are from video
    letters, margins = lt.read_board(crop, detect_grid(crop), LETTERS)
    expected = json.loads((FIX / "boards/img0717.json").read_text())["letters"]
    assert letters == expected
    assert min(margins) > 0.02


@pytest.mark.parametrize(
    "name,value",
    [
        ("end_words_65", 65),
        ("end_score_44700", 44700),
        ("end_score_28000", 28000),
        ("banner_words_64", 64),
        ("banner_score_38300", 38300),
    ],
)
def test_read_number(name, value):
    gray = cv2.imread(str(FIX / f"crops/{name}.png"), cv2.IMREAD_GRAYSCALE)
    got, conf = lt.read_number(gray, DIGITS)
    assert got == value
    assert conf > 0.5
