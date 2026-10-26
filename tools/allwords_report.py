"""Process every VIEW ALL WORDS capture (S0.T12).

uv run python tools/allwords_report.py [--fps 30]
For each all-words run in the sampled recordings: stitch rows, OCR revealed words, summarise
per-length counts, match to a played board (reconciled.json), compare with the YAWL/ENABLE
solver counts, and derive slot evidence. Writes $WH_DATA/labels/allwords[_<fps>].json.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pytesseract

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

from extract_frames import frames, probe, recording_path  # noqa: E402

from whcore import allwords as aw  # noqa: E402
from whcore.letters import load_templates  # noqa: E402
from whcore.oracle.screens import all_words_runs, classify, smooth  # noqa: E402
from whcore.solver import load_trie, solve  # noqa: E402

WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
DIGITS = load_templates(ROOT / "fixtures/templates/digits.npz")


def ocr_word(crop: np.ndarray) -> str:
    g = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if b.mean() < 128:
        b = 255 - b
    txt = pytesseract.image_to_string(
        b, config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    )
    return re.sub("[^A-Z]", "", txt).lower()


def captures(name: str) -> list[tuple[int, int]]:
    with gzip.open(WH_DATA / "frames" / name / "samples.csv.gz", "rt") as f:
        rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]
    t = [int(r["t_ms"]) for r in rows]
    return [(t[a], t[b]) for a, b in all_words_runs(smooth(classify(rows)), t)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()
    yawl = load_trie(ROOT / "dictionaries/yawl.txt")
    enable = load_trie(ROOT / "dictionaries/enable1.txt")
    boards = json.loads((WH_DATA / "labels/reconciled.json").read_text())
    auto = {
        (r["recording"], int(r["seq"])): r
        for r in csv.DictReader(open(WH_DATA / "labels/auto_boards.csv"))
    }
    cands = [
        {
            "id": f"{b['recording']}#{b['seq']}",
            "words": [w["word"] for w in b["words"] if w["word"]],
            "t": (b["recording"], int(auto[(b["recording"], b["seq"])]["t_start_ms"])),
            "letters": b["letters"].lower(),
        }
        for b in boards
    ]
    by_id = {c["id"]: c for c in cands}
    results = []
    for name in ("session1", "allwords1"):
        path = recording_path(name)
        meta = probe(path)
        for k, (t0, t1) in enumerate(captures(name)):
            cap = aw.stitch(
                frames(
                    path, meta["width"], meta["height"], args.fps, t0 / 1000, (t1 - t0) / 1000 + 0.1
                ),
                DIGITS,
            )
            for s in cap.slots.values():
                if s.kind == "found" and s.crops:
                    s.word = ocr_word(s.crops[len(s.crops) // 2])
            summ = aw.summarise(cap)
            raw = [(s.length, s.word) for s in cap.ordered() if s.kind == "found" and s.word]
            revealed = aw.snap_revealed(raw, cands)
            it = iter(revealed)
            for s in cap.ordered():
                if s.kind == "found" and s.word:
                    s.word = next(it)
            state, bid, ids = aw.match_revealed(revealed, cands)
            rec = {
                "recording": name,
                "capture": k,
                "t_ms": [t0, t1],
                **summ,
                "revealed": revealed,
                "match_state": state,
                "board": bid,
                "candidates": ids,
                "shift_abs_max": int(max((abs(s) for s in cap.shifts), default=0)),
                "shift_p95": float(np.percentile(np.abs(cap.shifts), 95)) if cap.shifts else 0.0,
                "cost_max": round(max(cap.costs, default=0.0), 2),
                "shifts": cap.shifts,
                "costs": [round(c, 2) for c in cap.costs],
            }
            if bid:
                b = by_id[bid]
                accepted = set(b["words"])
                sy, se = solve(b["letters"], yawl), solve(b["letters"], enable)
                rec["yawl_counts"] = dict(sorted(Counter(len(w) for w in sy).items(), reverse=True))
                rec["enable_counts"] = dict(
                    sorted(Counter(len(w) for w in se).items(), reverse=True)
                )
                rec["accepted_counts"] = dict(
                    sorted(Counter(len(w) for w in accepted).items(), reverse=True)
                )
                order = aw.list_order(accepted)
                rec["revealed_is_prefix"] = revealed == order[: len(revealed)]
                rows = [(sl.length, sl.kind, sl.word) for sl in cap.ordered()]
                rec["slot_evidence"] = aw.slot_evidence(rows, accepted, set(sy))
                rec["not_in_yawl_but_accepted"] = sorted(accepted - set(sy))
            results.append(rec)
            print(
                f"{name} capture {k} ({t0 / 1000:.1f}s): {summ['counts_by_length']} "
                f"revealed {len(revealed)} → {state} {bid} | yawl {rec.get('yawl_counts')} "
                f"| prefix {rec.get('revealed_is_prefix')} | max|shift| {rec['shift_abs_max']} "
                f"status {summ['status']} gaps {summ['gap_frames']}"
            )
    suffix = "" if args.fps == 30 else f"_{args.fps}"
    (WH_DATA / f"labels/allwords{suffix}.json").write_text(
        json.dumps(results, indent=1, default=int)
    )
    ok = sum(r["match_state"] == "matched" for r in results)
    print(f"{ok}/{len(results)} captures matched")
    return 0 if ok >= 3 else 1


if __name__ == "__main__":
    sys.exit(main())
