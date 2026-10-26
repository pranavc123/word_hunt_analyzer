"""Sprint reports and gates.

uv run python tools/report.py --gate s0     → prints PASS or FAIL with reasons
uv run python tools/report.py --diag        → device probe summary (diag.jsonl)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
LABELS = WH_DATA / "labels"


def load_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def diag_runs(path: Path) -> list[list[dict]]:
    """Broadcast runs in diag.jsonl, split on 'start' events."""
    if not path.exists():
        return []
    runs: list[list[dict]] = []
    for line in path.read_text().splitlines():
        d = json.loads(line)
        if d.get("event") == "start" or not runs:
            runs.append([])
        runs[-1].append(d)
    return runs


def summarise_run(run: list[dict]) -> dict:
    ticks = [d for d in run if d.get("event") == "tick"]
    fps = np.array([d["fps_processed"] for d in ticks]) if ticks else np.array([0.0])
    last = run[-1]
    tiles = [t for d in run for t in (d.get("tiles_rgb") or [])]
    resting = None
    if tiles:
        arr = np.array(tiles, float)
        keys, inv, counts = np.unique(
            (arr // 6).astype(int), axis=0, return_inverse=True, return_counts=True
        )
        centre = arr[inv.ravel() == counts.argmax()].mean(0)
        resting = np.median(arr[np.abs(arr - centre).max(1) <= 12], axis=0).round(1).tolist()
    return {
        "started": run[0].get("received_at"),
        "duration_min": round(last.get("uptime_s", 0) / 60, 1),
        "finished_cleanly": last.get("event") == "finish",
        "fps_p5": round(float(np.percentile(fps, 5)), 1),
        "fps_p50": round(float(np.percentile(fps, 50)), 1),
        "ticks_below_30fps": int((fps < 30).sum()),
        "frames_received": last.get("frames_received", 0),
        "frames_dropped": last.get("frames_dropped", 0),
        "mem_peak_mb": max(d.get("mem_peak_mb", 0) for d in run),
        "app_group_configured": any(d.get("app_group_configured") for d in run),
        "app_group_available": any(d.get("app_group_available") for d in run),
        "buffer": Counter(
            f"{d.get('buffer_w')}x{d.get('buffer_h')} {d.get('pixel_format')}"
            for d in run
            if d.get("buffer_w")
        ).most_common(1)[0][0]
        if any(d.get("buffer_w") for d in run)
        else None,
        "resting_rgb_phone": resting,
    }


def segmentation_accuracy() -> tuple[float, int] | None:
    auto_path, lab_path = LABELS / "auto_boards.csv", LABELS / "boards.csv"
    if not (auto_path.exists() and lab_path.exists()):
        return None
    auto = {(r["recording"], r["seq"]): r["status"] for r in csv.DictReader(open(auto_path))}
    lab = {(r["recording"], r["seq"]): r["status"] for r in csv.DictReader(open(lab_path))}
    keys = [k for k in lab if k in auto]
    if not keys:
        return None
    return sum(auto[k] == lab[k] for k in keys) / len(keys), len(keys)


def gate_s0() -> tuple[bool, list[str]]:
    checks: list[tuple[bool, str]] = []

    seg = segmentation_accuracy()
    checks.append(
        (
            seg is not None and seg[0] >= 0.95,
            f"board segmentation vs labels: {seg[0]:.0%} of {seg[1]}"
            if seg
            else "board segmentation: no labels",
        )
    )

    rec = load_json(LABELS / "reconciled.json") or []
    v = sum(r["verified"] for r in rec)
    checks.append(
        (v >= 4 and rec and v / len(rec) >= 0.8, f"played boards reconciled (§3.3): {v}/{len(rec)}")
    )

    aw = load_json(LABELS / "allwords.json") or []
    m = sum(c["match_state"] == "matched" for c in aw)
    checks.append((m >= 3, f"all-words captures matched to the right board: {m}/{len(aw)}"))

    runs = [summarise_run(r) for r in diag_runs(WH_DATA / "diag.jsonl")]
    long_runs = [r for r in runs if r["duration_min"] >= 30]
    if long_runs:
        r = max(long_runs, key=lambda x: x["duration_min"])
        checks.append(
            (
                r["mem_peak_mb"] < 45,
                f"extension memory peak over {r['duration_min']} min: {r['mem_peak_mb']} MB (< 45)",
            )
        )
        checks.append(
            (
                r["fps_p5"] >= 30,
                f"extension fps p5/p50: {r['fps_p5']}/{r['fps_p50']} (≥ 30 needed in play)",
            )
        )
    else:
        checks.append((False, "device probe: no broadcast run ≥ 30 min in diag.jsonl"))

    shifts = [c.get("shift_abs_max", 0) for c in aw]
    checks.append(
        (
            bool(shifts),
            f"max overlapping flick recorded: {max(shifts, default=0)} px/frame at 30 fps",
        )
    )
    return all(ok for ok, _ in checks), [("ok   " if ok else "FAIL ") + msg for ok, msg in checks]


def oracle_vs_labels() -> tuple[bool, str]:
    """Run the state machine over the S0 samples and compare with the labels."""
    import gzip
    from datetime import UTC, datetime

    sys.path.insert(0, str(ROOT / "server"))
    from whcore.oracle.machine import run

    labels = {
        (r["recording"], int(r["seq"])): r for r in csv.DictReader(open(LABELS / "boards.csv"))
    }
    traces = {(t["recording"], t["seq"]): t for t in load_json(LABELS / "traces.json") or []}
    total = ok = 0
    for name in sorted({k[0] for k in labels}):
        path = WH_DATA / "frames" / name / "samples.csv.gz"
        if not path.exists():
            return False, f"oracle vs labels: no samples for {name}"
        with gzip.open(path, "rt") as f:
            rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]
        records, _ = run(
            rows, "0b7d9e10-2c3a-4f5b-8e6d-7a8b9c0d1e2f", datetime(2026, 1, 1, tzinfo=UTC)
        )
        boards = [r for r in records if r.kind == "board"]
        for b in boards:
            total += 1
            truth = labels.get((name, b.seq))
            good = truth is not None and b.status == truth["status"]
            if good and b.status == "played":
                acc = sum(a.release_state == "valid_new" for a in b.attempts)
                good = acc == traces[(name, b.seq)]["end_words"]
            ok += good
        total += max(0, sum(k[0] == name for k in labels) - len(boards))  # missed boards
    return (
        total > 0 and ok == total,
        f"oracle events vs S0 labels (status + accepted == WORDS): {ok}/{total}",
    )


def ci_status() -> tuple[bool, str]:
    import subprocess

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT
    ).stdout.strip()
    try:
        out = subprocess.run(
            ["gh", "run", "list", "--commit", sha, "--json", "conclusion,status,name"],
            capture_output=True, text=True, cwd=ROOT, timeout=30,
        )  # fmt: skip
        runs = json.loads(out.stdout or "[]")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        runs = []
    if not runs:
        return False, f"CI: no workflow run for HEAD {sha[:7]} (push it first)"
    good = all(r.get("conclusion") == "success" for r in runs)
    states = ", ".join(f"{r['name']}={r.get('conclusion') or r.get('status')}" for r in runs)
    return good, f"CI on {sha[:7]}: {states}"


def fixtures_size() -> tuple[bool, str]:
    size = sum(p.stat().st_size for p in (ROOT / "fixtures").rglob("*") if p.is_file())
    return size < 2 * 1024 * 1024, f"fixtures size: {size / 1024 / 1024:.2f} MB (< 2)"


def gate_s1() -> tuple[bool, list[str]]:
    checks = [oracle_vs_labels(), fixtures_size(), ci_status()]
    return all(ok for ok, _ in checks), [("ok   " if ok else "FAIL ") + msg for ok, msg in checks]


GATES = {"s0": gate_s0, "s1": gate_s1}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", choices=sorted(GATES))
    ap.add_argument("--diag", action="store_true")
    args = ap.parse_args()
    if args.diag:
        for r in diag_runs(WH_DATA / "diag.jsonl"):
            print(json.dumps(summarise_run(r)))
    if args.gate:
        ok, lines = GATES[args.gate]()
        print("\n".join(lines))
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
