"""Resolve words and reconcile every played board (S0.T11).

uv run python tools/reconcile_boards.py [--traces traces.json]
Reads $WH_DATA/labels/traces*.json, writes $WH_DATA/labels/reconciled*.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

from extract_frames import frame_at  # noqa: E402

from whcore.calibration import load_calibration  # noqa: E402
from whcore.oracle.traces import path_is_contiguous  # noqa: E402
from whcore.reconcile import POINTS_TO_LEN, read_end_list, reconcile, snap_visible  # noqa: E402
from whcore.solver import load_trie, solve  # noqa: E402
from whcore.words import resolve_board, word_of  # noqa: E402

WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
CAL = load_calibration(ROOT / "fixtures/calibration/iphone-1206x2622.json")
DICT = Path(os.environ.get("WH_DICT", ROOT / "dictionaries/yawl.txt"))


def end_list_vote(recording: str, t_ms: int) -> list[tuple[str, int | None]]:
    """Read the end list on 5 frames (the screen animates in and out; OCR flickers) and vote per
    row, preferring reads whose length agrees with their points."""
    reads = [read_end_list(frame_at(recording, t_ms - dt), CAL) for dt in (0, 100, 200, 300, 400)]
    n = max(len(r) for r in reads)
    rows = []
    for i in range(n):
        cands = [r[i] for r in reads if i < len(r)]
        consistent = [c for c in cands if POINTS_TO_LEN.get(c[1]) == len(c[0])]
        rows.append(Counter(consistent or cands).most_common(1)[0][0])
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces", default="traces.json")
    args = ap.parse_args()
    trie = load_trie(DICT)
    auto = {
        (r["recording"], int(r["seq"])): r
        for r in csv.DictReader(open(WH_DATA / "labels/auto_boards.csv"))
    }
    out = []
    for b in json.loads((WH_DATA / "labels" / args.traces).read_text()):
        letters = b["letters"].lower()
        sol = solve(letters, trie)
        a = auto[(b["recording"], b["seq"])]
        rows = end_list_vote(b["recording"], int(a["end_last_ms"]))
        acc = [x for x in b["attempts"] if x["release_state"] == "valid_new"]
        observed = [x["tiles_seen"] for x in acc]
        # vocabulary for snapping: solver words + clean traces the dictionary lacks
        oov = {word_of(o, letters) for o in observed if len(o) >= 3 and path_is_contiguous(o)}
        visible = snap_visible(rows, set(sol) | oov)
        vis_words = {v["word"] for v in visible if v["word"]}
        res = resolve_board(observed, sol, letters, b["end_score"], vis_words)
        words = [r.chosen.word for r in res if r.chosen]
        rec = reconcile(words, b["end_words"], b["end_score"], visible)
        repaired = [
            (word_of(r.observed, letters), r.chosen.word, r.chosen.cost)
            for r in res
            if r.chosen and r.chosen.cost > 0
        ]
        out.append(
            {
                "recording": b["recording"],
                "seq": b["seq"],
                "letters": b["letters"],
                **rec,
                "words": [
                    {
                        "word": r.chosen.word if r.chosen else None,
                        "path": r.chosen.path if r.chosen else None,
                        "observed": r.observed,
                        "cost": r.chosen.cost if r.chosen else None,
                        "ambiguous": r.ambiguous,
                        "oov": r.chosen.oov if r.chosen else None,
                        "t_start_ms": x["t_start_ms"],
                    }
                    for r, x in zip(res, acc, strict=True)
                ],
                "visible": visible,
                "solver_words": len(sol),
            }
        )
        flag = "VERIFIED" if rec["verified"] else f"needs_review {rec['checks']}"
        print(
            f"{b['recording']} #{b['seq']}: {rec['count']}/{rec['end_words']} words, "
            f"{rec['points']}/{rec['end_score']} pts, visible missing {rec['visible_missing']} "
            f"repaired {len(repaired)} → {flag}"
        )
        if not rec["verified"]:
            print("   repairs:", repaired)
            print("   visible:", [(v["raw"], v["word"], v["points"]) for v in visible])
    name = args.traces.replace("traces", "reconciled")
    (WH_DATA / "labels" / name).write_text(json.dumps(out, indent=1, default=int))
    n = sum(r["verified"] for r in out)
    print(f"{n}/{len(out)} played boards verified")
    return 0 if n >= 4 else 1


if __name__ == "__main__":
    sys.exit(main())
