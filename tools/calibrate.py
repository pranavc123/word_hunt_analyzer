"""Build the device calibration from a board screenshot (+ optional end screenshot).

uv run python tools/calibrate.py [--board IMG_0717.PNG] [--end IMG_0718.PNG]
Writes fixtures/calibration/iphone-<w>x<h>.json, fixtures/crops/img0717_tiles.png (0.5x board
crop) and $WH_DATA/templates/seed.npz (letter templates seeded from the known board letters).
"""

import argparse
import json
import os
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from whcore import calibration as cb  # noqa: E402

WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
CROP_SCALE = 0.5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=WH_DATA / "recordings/IMG_0717.PNG")
    ap.add_argument("--end", default=WH_DATA / "recordings/IMG_0718.PNG")
    ap.add_argument("--letters", default=None, help="known letters (default: fixture img0717)")
    args = ap.parse_args()
    letters = (
        args.letters or json.loads((ROOT / "fixtures/boards/img0717.json").read_text())["letters"]
    )

    board = cb.load_rgb(args.board)
    end = cb.load_rgb(args.end) if args.end and Path(args.end).exists() else None
    cal = cb.calibrate(board, end)
    out = ROOT / f"fixtures/calibration/iphone-{cal['width']}x{cal['height']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    cb.save_calibration(cal, out)

    # downscaled crop of the 4x4 tiles (margin of half a pitch) for committed tests
    (x0, y0), (x1, y1) = cal["tile_centers"][0], cal["tile_centers"][-1]
    m = cal["pitch"][0] / 2
    box = [round(x0 - m), round(y0 - m), round(x1 + m), round(y1 + m)]
    crop = board[box[1] : box[3], box[0] : box[2]]
    crop = cv2.resize(crop, None, fx=CROP_SCALE, fy=CROP_SCALE, interpolation=cv2.INTER_AREA)
    crop_path = ROOT / "fixtures/crops/img0717_tiles.png"
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(crop_path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))

    templates = cb.seed_templates(board, cal, letters)
    (WH_DATA / "templates").mkdir(parents=True, exist_ok=True)
    cb.save_templates(templates, WH_DATA / "templates/seed.npz")
    read, margins = cb.read_letters(board, cal, templates)

    print(f"wrote {out.relative_to(ROOT)}  crop {crop.shape[1]}x{crop.shape[0]} origin {box[:2]}")
    print(f"tile_size {cal['tile_size']} pitch {cal['pitch']} resting {cal['resting_rgb']}")
    for k in (
        "roi_banner",
        "roi_banner_words",
        "roi_banner_score",
        "roi_timer",
        "roi_end_banner",
        "roi_end_list",
        "end_list_first_row",
        "end_list_row_pitch",
        "end_list_rows",
    ):
        print(f"{k}: {cal.get(k)}")
    print(
        f"re-read {read} (min margin {min(margins):.3f}) {'OK' if read == letters else 'MISMATCH'}"
    )
    return 0 if read == letters else 1


if __name__ == "__main__":
    sys.exit(main())
