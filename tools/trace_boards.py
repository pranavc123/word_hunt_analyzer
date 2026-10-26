"""Attempt traces for every played board (S0.T9).

uv run python tools/trace_boards.py [--fps 30]
Streams each played board once, reads the live WORDS/SCORE banner on every frame (digit
templates), segments attempts from tile colours, and writes $WH_DATA/labels/traces[_<fps>].json.
An attempt is accepted when the WORDS count rises right after its release; the release colour is
kept alongside for comparison.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

from extract_frames import frame_at, frames, probe, recording_path  # noqa: E402

from whcore import letters as lt  # noqa: E402
from whcore.calibration import load_calibration  # noqa: E402
from whcore.oracle.sampler import tile_matrix  # noqa: E402
from whcore.oracle.traces import segment_attempts, tile_codes  # noqa: E402

WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
CAL = load_calibration(ROOT / "fixtures/calibration/iphone-1206x2622.json")
DIGITS = lt.load_templates(ROOT / "fixtures/templates/digits.npz")
AFTER = 4  # frames after release at which the WORDS count is read


def load_codes(name: str):
    with gzip.open(WH_DATA / "frames" / name / "samples.csv.gz", "rt") as f:
        rows = list(csv.DictReader(f))
    cols = {k: np.array([float(r[k]) for r in rows]) for k in rows[0]}
    return tile_codes(tile_matrix(cols)), cols["t_ms"].astype(int)


def banner_series(name: str, first: int, last: int, fps: float) -> list[tuple]:
    """(words, score) per sampled frame index in [first, last] (None where unreadable)."""
    path = recording_path(name)
    meta = probe(path)
    out = []
    for img in frames(
        path, meta["width"], meta["height"], fps, first / fps, (last - first + 1) / fps
    ):
        w, _ = lt.read_number(lt.gray_roi(img, CAL["roi_banner_words"]), DIGITS)
        s, _ = lt.read_number(lt.gray_roi(img, CAL["roi_banner_score"]), DIGITS)
        out.append((w, s))
    return out[: last - first + 1]


def trace_board(b: dict, codes, t_ms, fps: float, step: int) -> dict:
    """All indices below are in the effective stream (every `step`-th 30 fps frame)."""
    first30 = int(b["t_start_ms"]) * fps // 1000
    last30 = int(b["t_end_ms"]) * fps // 1000
    series = banner_series(b["recording"], first30, last30, fps)
    if first30 % step:  # align the banner series with the subsampled stream
        series = series[step - first30 % step :]
    series = series[::step]
    codes, t_ms = codes[::step], t_ms[::step]
    first = -(-first30 // step)
    hi = min(last30 // step, first + len(series) - 1)

    def words_at(i: int) -> int | None:
        i = min(max(i, first), first + len(series) - 1)
        return series[i - first][0]

    sub_t = t_ms
    attempts = segment_attempts(codes, t_ms, first, hi)
    out = []
    prev_words = 0
    for k, a in enumerate(attempts):
        nxt = attempts[k + 1].first if k + 1 < len(attempts) else hi + 1
        after = words_at(min(a.last + AFTER, nxt - 1))
        before = words_at(a.first - 1)
        before = before if before is not None else prev_words
        accepted = after is not None and after == before + 1
        colour = a.release_state
        state = (
            "valid_new"
            if accepted
            else ("already_found" if colour == "already_found" else "not_a_word")
        )
        prev_words = after if after is not None else prev_words
        d = a.as_dict()
        d.update(
            release_state=state,
            colour_state=colour,
            banner_words_before=before,
            banner_words_after=after,
            t_start_ms=int(sub_t[a.first]),
            t_end_ms=int(sub_t[a.last]),
        )
        out.append(d)
    # settled SCORE after each accepted word: read just before the next acceptance's release
    # (the counter rolls up for ~1 s), and at the end of the board for the last one
    acc = [d for d in out if d["release_state"] == "valid_new"]
    for j, d in enumerate(acc):
        upto = acc[j + 1]["last"] if j + 1 < len(acc) else hi
        vals = [series[i - first][1] for i in range(max(d["last"], upto - 2), upto + 1)]
        vals = [v for v in vals if v is not None]
        d["banner_score_after"] = max(vals) if vals else None
    end = frame_at(b["recording"], int(b["end_t_ms"]))
    end_words, end_score, end_conf = lt.read_banner(end, CAL, DIGITS, end=True)
    final = [x for x in series[-15:] if x[0] is not None]
    return {
        "recording": b["recording"],
        "seq": int(b["seq"]),
        "letters": b["letters"],
        "attempts": out,
        "end_words": end_words,
        "end_score": end_score,
        "end_conf": round(end_conf, 3),
        "live_final": final[-1] if final else None,
        "words_jumps_outside": words_jumps_outside(series, out, first),
    }


def words_jumps_outside(series, attempts, first) -> int:
    """WORDS increments not explained by an accepted attempt (missed attempts)."""
    vals = [w for w, _ in series]
    total = 0
    known = {a["banner_words_after"] for a in attempts if a["release_state"] == "valid_new"}
    seen = 0
    for v in vals:
        if v is not None and v == seen + 1:
            if v not in known:
                total += 1
            seen = v
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=30, help="30, or 15 to use every 2nd frame")
    args = ap.parse_args()
    step = 30 // args.fps
    labels = {
        (r["recording"], r["seq"]): r["letters"]
        for r in csv.DictReader(open(WH_DATA / "labels/boards.csv"))
    }
    auto = [
        r
        for r in csv.DictReader(open(WH_DATA / "labels/auto_boards.csv"))
        if r["status"] == "played"
    ]
    cache: dict[str, tuple] = {}
    results = []
    for b in auto:
        if b["recording"] not in cache:
            cache[b["recording"]] = load_codes(b["recording"])
        codes, t_ms = cache[b["recording"]]
        b = {**b, "letters": labels.get((b["recording"], b["seq"]), "")}
        r = trace_board(b, codes, t_ms, 30, step)
        acc = sum(a["release_state"] == "valid_new" for a in r["attempts"])
        col = sum(a["colour_state"] == "valid_new" for a in r["attempts"])
        ok = acc == r["end_words"]
        r["accepted"] = acc
        results.append(r)
        print(
            f"{b['recording']} #{b['seq']}: attempts {len(r['attempts'])} accepted {acc} "
            f"(colour {col}) end WORDS {r['end_words']} SCORE {r['end_score']} "
            f"missed {r['words_jumps_outside']} {'OK' if ok else 'MISMATCH'}"
        )
    suffix = "" if args.fps == 30 else f"_{args.fps}"
    (WH_DATA / f"labels/traces{suffix}.json").write_text(json.dumps(results, indent=1, default=int))
    good = sum(r["accepted"] == r["end_words"] for r in results)
    print(f"{good}/{len(results)} boards: accepted attempts == end WORDS")
    return 0 if good == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
