"""Stream a recording through ffmpeg at 30 fps and write numeric samples (S0.T6).

uv run python tools/extract_frames.py session1 [--fps 30]
→ $WH_DATA/frames/<name>/samples.csv.gz (+ meta.json). Full frames are NOT written to disk;
use `frame_at()` to pull single frames on demand.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from whcore.calibration import load_calibration  # noqa: E402
from whcore.letters import load_templates  # noqa: E402
from whcore.oracle.sampler import Sampler, columns, scale_calibration  # noqa: E402

WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
CAL_PATH = ROOT / "fixtures/calibration/iphone-1206x2622.json"


def recording_path(name: str) -> Path:
    p = Path(name)
    return p if p.exists() else WH_DATA / "recordings" / f"{name}.mov"


def probe(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,nb_frames,codec_name:format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    j = json.loads(out.stdout)
    s, f = j["streams"][0], j["format"]
    num, den = map(int, s["avg_frame_rate"].split("/"))
    return {
        "width": s["width"],
        "height": s["height"],
        "codec": s["codec_name"],
        "native_fps": round(num / den, 2),
        "nb_frames": int(s.get("nb_frames", 0)),
        "duration_s": float(f["duration"]),
        "size_bytes": int(f["size"]),
    }


def frames(
    path: Path, w: int, h: int, fps: float, start_s: float = 0.0, dur_s: float | None = None
):
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start_s)]
    if dur_s is not None:
        cmd += ["-t", str(dur_s)]
    cmd += ["-i", str(path), "-an", "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=w * h * 3 * 2
    )
    n = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(n)
            if len(buf) < n:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        proc.stdout.close()
        proc.wait()


def frame_at(name: str, t_ms: float) -> np.ndarray:
    """One RGB frame at t_ms (accurate seek)."""
    path = recording_path(name)
    meta = probe(path)
    return next(frames(path, meta["width"], meta["height"], 30, start_s=t_ms / 1000, dur_s=0.1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--fps", type=float, default=30)
    args = ap.parse_args()
    path = recording_path(args.name)
    meta = probe(path)
    cal = scale_calibration(load_calibration(CAL_PATH), meta["width"], meta["height"])
    out_dir = WH_DATA / "frames" / Path(args.name).stem
    out_dir.mkdir(parents=True, exist_ok=True)
    t0, n = time.time(), 0
    with gzip.open(out_dir / "samples.csv.gz", "wt", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(columns())
        sampler = Sampler(cal, load_templates(ROOT / "fixtures/templates/digits.npz"))
        for n, img in enumerate(frames(path, meta["width"], meta["height"], args.fps)):
            vals = sampler.sample(img)
            wr.writerow([n, round(n * 1000 / args.fps)] + [round(v, 1) for v in vals])
    meta.update(sampled_fps=args.fps, sampled_frames=n + 1, calibration=cal["version"])
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta), f"{time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
