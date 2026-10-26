import csv
import gzip
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from whcore.oracle.machine import run
from whcore.oracle.traces import STATES

ROOT = Path(__file__).resolve().parents[2]
WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
SESSION = "0b7d9e10-2c3a-4f5b-8e6d-7a8b9c0d1e2f"
T0 = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)

SCREENS = {
    "board": {"banner": 205, "banner_std": 85, "timer": 92, "timer_std": 54},
    "end": {
        "banner": 87,
        "banner_std": 10,
        "end_banner": 160,
        "end_banner_std": 82,
        "end_list": 70,
    },
    "all_words": {"banner": 120, "banner_std": 50, "timer": 158, "timer_std": 72},
    "other": {"banner": 175, "banner_std": 62, "timer": 228, "timer_std": 48},
}


def row(screen, tiles=None, words=math.nan, shift=math.nan):
    base = {"banner": 60, "banner_std": 10, "timer": 60, "timer_std": 5, "end_banner": 100,
            "end_banner_std": 5, "end_list": 150}  # fmt: skip
    base.update(SCREENS[screen])
    r = {}
    for k, v in base.items():
        if k.endswith("_std"):
            r[k] = v
        else:
            r.update({f"{k}_r": v, f"{k}_g": v, f"{k}_b": v})
    tiles = tiles or {}
    for i in range(16):
        rgb = STATES[tiles.get(i, "resting")]
        r.update({f"t{i}_r": rgb[0], f"t{i}_g": rgb[1], f"t{i}_b": rgb[2]})
    r["words"], r["list_shift"] = words, shift
    return r


def stream(*parts):
    """parts: (count, row) pairs → rows with t_ms at 30 fps."""
    rows = [dict(r) for n, r in parts for _ in range(n)]
    for i, r in enumerate(rows):
        r["t_ms"] = round(i * 1000 / 30)
    return rows


def test_played_board_with_attempts_then_skip_then_all_words():
    sel = lambda *ts, c="white": {t: c for t in ts}  # noqa: E731
    rows = stream(
        (10, row("other")),
        (40, row("board", words=0)),  # opens, settles
        (2, row("board", sel(0), words=0)),
        (3, row("board", sel(0, 1, 2, c="green"), words=0)),
        (8, row("board", words=1)),  # accepted: WORDS 0 → 1
        (3, row("board", sel(5, 6, c="yellow"), words=1)),
        (8, row("board", words=1)),  # duplicate
        (3, row("board", sel(9, 10), words=1)),
        (8, row("board", words=1)),  # not a word
        (2, row("other")),  # 67 ms flicker: same board
        (20, row("board", words=1)),
        (6, row("other")),
        (30, row("end")),
        (150, row("other")),
        (15, row("board", words=0)),  # skipped after 0.5 s
        (150, row("other")),
        (1, row("all_words")),
        (8, row("all_words", shift=0)),  # list settles on screen
        *[(1, row("all_words", shift=s)) for s in [0, 300, 600, 900, 400, 100, -20, 5, 0, 0]],
        (12, row("all_words", shift=0)),  # user looks at the bottom before going back
        (60, row("other")),
    )
    records, crops = run(rows, SESSION, T0)
    boards = [r for r in records if r.kind == "board"]
    assert [b.status for b in boards] == ["played", "skipped"]
    played = boards[0]
    assert [a.release_state for a in played.attempts] == [
        "valid_new",
        "already_found",
        "not_a_word",
    ]
    assert [a.tiles_seen for a in played.attempts] == [[0, 1, 2], [5, 6], [9, 10]]
    assert played.attempts[0].banner_words_after == 1
    assert played.end_banner_image and played.end_list_image
    assert 2900 < played.view_ms < 3300  # board + flicker merged
    assert boards[1].view_ms < 600 and boards[1].end_list_image is None
    names = {c.name: c for c in crops}
    assert names["board_0.png"].frame >= 10 + 24  # ≥ 0.8 s after open
    aw = [r for r in records if r.kind == "all_words"]
    assert len(aw) == 1
    rec = aw[0]
    assert len(rec.frames) == len(rec.shifts_px) == len(rec.gap_flags) >= 3
    assert rec.shifts_px[0] == 0 and rec.shifts_px[-1] == sum([0, 300, 600, 900, 400, 100, -20, 5])
    assert rec.bounced_at_end and not any(rec.gap_flags)
    # deterministic ids
    again, _ = run(rows, SESSION, T0)
    assert [r.model_dump() for r in again] == [r.model_dump() for r in records]


SAMPLES = WH_DATA / "frames/session1/samples.csv.gz"


def load(name):
    with gzip.open(WH_DATA / "frames" / name / "samples.csv.gz", "rt") as f:
        return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]


@pytest.mark.skipif(
    not (WH_DATA / "labels/traces.json").exists() or not SAMPLES.exists(), reason="no S0 data"
)
def test_machine_matches_s0_labels():
    labels = {
        (r["recording"], int(r["seq"])): r
        for r in csv.DictReader(open(WH_DATA / "labels/boards.csv"))
    }
    traces = {
        (t["recording"], t["seq"]): t
        for t in json.loads((WH_DATA / "labels/traces.json").read_text())
    }
    for name in ("session1", "allwords1"):
        records, _ = run(load(name), SESSION, T0)
        boards = [r for r in records if r.kind == "board"]
        assert len(boards) == sum(k[0] == name for k in labels)
        for b in boards:
            assert b.status == labels[(name, b.seq)]["status"]
            if b.status == "played":
                t = traces[(name, b.seq)]
                accepted = sum(a.release_state == "valid_new" for a in b.attempts)
                assert accepted == t["end_words"], (name, b.seq)


FIX = ROOT / "fixtures"
FIXTURES = sorted(p.name.removesuffix(".csv.gz") for p in (FIX / "samples").glob("*.csv.gz"))
LABELS = json.loads((FIX / "expected/labels.json").read_text())


def load_fixture(name):
    with gzip.open(FIX / "samples" / f"{name}.csv.gz", "rt") as f:
        return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]


@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_output_matches_expected(name):
    expected = json.loads((FIX / "expected" / f"{name}.json").read_text())
    src = expected["source"]
    records, crops = run(
        load_fixture(name), src["session_id"], datetime.fromisoformat(src["started_at"])
    )
    got = [r.model_dump(mode="json", by_alias=True, exclude_none=True) for r in records]
    assert got == expected["records"]
    assert [{"name": c.name, "frame": c.frame, "rect": c.rect} for c in crops] == expected["crops"]


@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_output_agrees_with_s0_labels(name):
    expected = json.loads((FIX / "expected" / f"{name}.json").read_text())
    boards = [r for r in expected["records"] if r["kind"] == "board"]
    for b, truth in zip(boards, LABELS[name]["boards"], strict=True):
        assert b["status"] == truth["status"]
        if truth["status"] == "played":
            accepted = sum(a["release_state"] == "valid_new" for a in b["attempts"])
            assert accepted == truth["end_words"]
            assert b["end_list_image"] and b["end_banner_image"]
    assert any(r["kind"] == "all_words" for r in expected["records"]) == (
        "all_words" in LABELS[name]
    )
