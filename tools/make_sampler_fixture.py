"""Expected Python sampler values for the Swift sampler parity test (S2.T3).

uv run python tools/make_sampler_fixture.py → fixtures/expected/sampler.json
Each board crop in fixtures/expected/labels.json is pasted at its origin into a 1206×2622 frame
filled with BACKGROUND; the Python sampler's tile and ROI values for that frame are stored.
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from whcore.calibration import load_calibration, load_rgb  # noqa: E402
from whcore.oracle.sampler import columns, sample_frame  # noqa: E402

FIX = ROOT / "fixtures"
BACKGROUND = (40, 60, 40)


def main() -> int:
    cal = load_calibration(FIX / "calibration/iphone-1206x2622.json")
    labels = json.loads((FIX / "expected/labels.json").read_text())
    out = {"background": BACKGROUND, "frames": []}
    for lab in labels.values():
        if "board_crop" not in lab:
            continue
        crop = load_rgb(FIX / lab["board_crop"]["file"])
        img = np.empty((cal["height"], cal["width"], 3), np.uint8)
        img[...] = BACKGROUND
        x0, y0 = lab["board_crop"]["origin"]
        img[y0 : y0 + crop.shape[0], x0 : x0 + crop.shape[1]] = crop
        vals = dict(zip(columns()[2:-2], sample_frame(img, cal), strict=True))
        out["frames"].append({"crop": lab["board_crop"]["file"], "origin": [x0, y0],
                              "values": {k: round(v, 3) for k, v in vals.items()}})  # fmt: skip
    (FIX / "expected/sampler.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {len(out['frames'])} frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
