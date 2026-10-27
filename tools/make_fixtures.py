"""Export small committed fixtures from the S0 recordings and labels (S1.T3).

uv run python tools/make_fixtures.py
Writes, for each segment below:
  fixtures/samples/<name>.csv.gz  sample rows (profile p0..p63 omitted: unused by the machine)
  fixtures/expected/<name>.json   machine output (records + crop requests), checked vs S0 labels
and fixtures/expected/labels.json (S0 ground truth for the boards / captures in the segments),
board crops for 3 boards, the list-band crops of one all-words capture, and
fixtures/templates/digits.json (digit templates for the Swift sampler).
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

from extract_frames import frame_at  # noqa: E402

from whcore.allwords import LIST_BAND_RECT  # noqa: E402
from whcore.calibration import load_calibration  # noqa: E402
from whcore.letters import load_templates  # noqa: E402
from whcore.oracle.machine import run  # noqa: E402

WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
FIX = ROOT / "fixtures"
CAL = load_calibration(FIX / "calibration/iphone-1206x2622.json")
SESSION = "0b7d9e10-2c3a-4f5b-8e6d-7a8b9c0d1e2f"
T0 = datetime(2026, 10, 26, tzinfo=UTC)
PAD_MS = 1500

# name → (recording, board seqs in the segment, include the following all-words capture)
SEGMENTS = {
    "session1_b00_played": ("session1", [0], False),
    "session1_b01_skipped": ("session1", [1], False),
    "session1_b02_played": ("session1", [2], False),
    "session1_b12_skipped": ("session1", [12], False),
    "allwords1_b00_played_allwords": ("allwords1", [0], True),
    "allwords1_b03_played_allwords": ("allwords1", [3], True),
}
BOARD_CROPS = ["session1_b00_played", "session1_b02_played", "allwords1_b00_played_allwords"]
PHONE_CROPS = ["session1_b00_played", "allwords1_b03_played_allwords"]  # worker tests
PHONE_W, PHONE_H = 884, 1920  # ReplayKit buffer size on the S0 device


def phone_crop(img: np.ndarray, rect: list[int]) -> np.ndarray:
    """What the phone uploads: the frame at buffer scale, cropped, gray (then JPEG q80)."""
    small = cv2.resize(img, (PHONE_W, PHONE_H), interpolation=cv2.INTER_AREA)
    sx, sy = PHONE_W / CAL["width"], PHONE_H / CAL["height"]
    x, y, w, h = (
        round(rect[0] * sx),
        round(rect[1] * sy),
        max(1, round(rect[2] * sx)),
        max(1, round(rect[3] * sy)),
    )
    return cv2.cvtColor(small[y : y + h, x : x + w], cv2.COLOR_RGB2GRAY)


LIST_CROPS = "allwords1_b03_played_allwords"


def load(name: str) -> tuple[list[str], list[list[str]]]:
    with gzip.open(WH_DATA / "frames" / name / "samples.csv.gz", "rt") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def board_box():
    (x0, y0), (x1, y1) = CAL["tile_centers"][0], CAL["tile_centers"][-1]
    m = CAL["pitch"][0] / 2
    return [round(x0 - m), round(y0 - m), round(x1 + m), round(y1 + m)]


def main() -> int:
    auto = {
        (r["recording"], int(r["seq"])): r
        for r in csv.DictReader(open(WH_DATA / "labels/auto_boards.csv"))
    }
    boards_csv = {
        (r["recording"], int(r["seq"])): r
        for r in csv.DictReader(open(WH_DATA / "labels/boards.csv"))
    }
    traces = {
        (t["recording"], t["seq"]): t
        for t in json.loads((WH_DATA / "labels/traces.json").read_text())
    }
    recon = {
        (r["recording"], r["seq"]): r
        for r in json.loads((WH_DATA / "labels/reconciled.json").read_text())
    }
    allw = {
        (a["recording"], a["capture"]): a
        for a in json.loads((WH_DATA / "labels/allwords.json").read_text())
    }
    cache: dict[str, tuple] = {}
    labels: dict[str, dict] = {}
    (FIX / "samples").mkdir(exist_ok=True)
    (FIX / "expected").mkdir(exist_ok=True)
    for name, (rec, seqs, with_aw) in SEGMENTS.items():
        if rec not in cache:
            cache[rec] = load(rec)
        hdr, rows = cache[rec]
        a = auto[(rec, seqs[0])]
        t_lo = int(a["t_start_ms"]) - PAD_MS
        end_ms = int(a["end_last_ms"] or a["t_end_ms"])
        if with_aw:
            # extend through the all-words run that follows the board
            ti = hdr.index("t_ms")
            sh = hdr.index("list_shift")
            start = int(a["all_words_t_ms"])
            last = start
            for r in rows:
                t = int(float(r[ti]))
                if t >= start and r[sh] != "nan":
                    last = t
                elif t > last + 1600 and last > start:
                    break
            end_ms = last
        t_hi = end_ms + PAD_MS
        ti = hdr.index("t_ms")
        seg = [r for r in rows if t_lo <= int(float(r[ti])) <= t_hi]
        keep = [i for i, c in enumerate(hdr) if not (c.startswith("p") and c[1:].isdigit())]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([hdr[i] for i in keep])
        for r in seg:
            w.writerow([r[i] for i in keep])
        (FIX / "samples" / f"{name}.csv.gz").write_bytes(
            gzip.compress(buf.getvalue().encode(), 9, mtime=0)
        )

        dict_rows = [{hdr[i]: float(r[i]) for i in keep} for r in seg]
        records, crops = run(dict_rows, SESSION, T0)
        boards = [x for x in records if x.kind == "board"]
        aws = [x for x in records if x.kind == "all_words"]
        # check against the S0 labels before writing
        assert len(boards) == len(seqs), (name, len(boards))
        for b, seq in zip(boards, seqs, strict=True):
            truth = boards_csv[(rec, seq)]
            assert b.status == truth["status"], (name, b.status)
            if b.status == "played":
                t = traces[(rec, seq)]
                acc = sum(x.release_state == "valid_new" for x in b.attempts)
                assert acc == t["end_words"], (name, acc, t["end_words"])
                # compare tile sets: S0 traces used index order within a frame
                ref = [(sorted(x["tiles_seen"]), x["release_state"]) for x in t["attempts"]]
                same = sum((sorted(x.tiles_seen), x.release_state) in ref for x in b.attempts)
                assert same >= 0.99 * len(ref), (name, same, len(ref))
        assert len(aws) == int(with_aw), (name, len(aws))
        frame0 = int(float(seg[0][hdr.index("frame")]))
        out = {
            "source": {
                "recording": rec,
                "first_frame": frame0,
                "rows": len(seg),
                "session_id": SESSION,
                "started_at": T0.isoformat(),
            },
            "records": [
                x.model_dump(mode="json", by_alias=True, exclude_none=True) for x in records
            ],
            "crops": [{"name": c.name, "frame": c.frame, "rect": c.rect} for c in crops],
        }
        (FIX / "expected" / f"{name}.json").write_text(json.dumps(out, indent=1) + "\n")

        lab = {"recording": rec, "boards": []}
        for seq in seqs:
            truth = boards_csv[(rec, seq)]
            entry = {"seq": seq, "letters": truth["letters"], "status": truth["status"]}
            if truth["status"] == "played":
                t, r = traces[(rec, seq)], recon[(rec, seq)]
                entry.update(
                    end_words=t["end_words"],
                    end_score=t["end_score"],
                    verified=r["verified"],
                    words=[x["word"] for x in r["words"]],
                    visible=[[v["raw"], v["points"]] for v in r["visible"]],
                )
            lab["boards"].append(entry)
        if with_aw:
            cap = allw[(rec, seqs[0])]
            lab["all_words"] = {
                k: cap[k]
                for k in ("counts_by_length", "board", "revealed", "status", "complete_down_to")
            }
        labels[name] = lab

        # images
        if name in BOARD_CROPS:
            c = next(c for c in crops if c.rect == "board")
            img = frame_at(rec, int(float(seg[c.frame][ti])))
            x0, y0, x1, y1 = board_box()
            cv2.imwrite(
                str(FIX / "crops" / f"{name}_board.jpg"),
                cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_RGB2BGR),
                [cv2.IMWRITE_JPEG_QUALITY, 75],
            )
            lab["board_crop"] = {"file": f"crops/{name}_board.jpg", "origin": [x0, y0]}
        if name in PHONE_CROPS:
            from whcore.pipeline import crop_rect

            lab["phone_crops"] = {}
            for c in crops:
                kind = {
                    "board": "board",
                    "roi_end_banner": "end_banner",
                    "roi_end_list": "end_list",
                }.get(c.rect)
                if kind is None:
                    continue
                img = frame_at(rec, int(float(seg[c.frame][ti])))
                f = f"crops/{name}_phone_{c.name}"
                cv2.imwrite(
                    str(FIX / f),
                    phone_crop(img, crop_rect(CAL, c.rect)),
                    [cv2.IMWRITE_JPEG_QUALITY, 80],
                )
                lab["phone_crops"][kind] = {"file": f, "name": c.name}
        if name == LIST_CROPS:
            x, y, w, h = LIST_BAND_RECT
            files = []
            band = [c for c in crops if c.rect == "list_band"]
            for c in (band[0], band[-1]):  # top of the list (revealed words) and its end
                img = frame_at(rec, int(float(seg[c.frame][ti])))
                gray = cv2.cvtColor(img[y : y + h, x : x + w], cv2.COLOR_RGB2GRAY)
                f = f"crops/{name}_{c.name.removesuffix('.jpg')}.jpg"
                cv2.imwrite(str(FIX / f), gray, [cv2.IMWRITE_JPEG_QUALITY, 80])
                files.append(f)
            lab["list_crops"] = files  # first and last crop only (size budget)
        print(f"{name}: {len(seg)} rows, {len(boards)} board(s), {len(aws)} all-words")

    (FIX / "expected" / "labels.json").write_text(json.dumps(labels, indent=1) + "\n")
    digits = load_templates(FIX / "templates/digits.npz")
    (FIX / "templates" / "digits.json").write_text(
        json.dumps(
            {
                "width": 20,
                "height": 28,
                "ink_threshold": 110,
                "templates": {k: np.round(v, 3).tolist() for k, v in sorted(digits.items())},
            }
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
