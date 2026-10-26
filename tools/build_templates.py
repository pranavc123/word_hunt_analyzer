"""Build letter + digit templates from labelled boards (S0.T10).

uv run python tools/build_templates.py
Letters: glyphs of every labelled board (several resting frames each) + IMG_0717.
Digits: banner/end-screen digits bootstrapped from tesseract reads that agree with the blob count.
Writes $WH_DATA/templates/{letters,digits}.npz and copies them to fixtures/templates/.
Prints leave-one-board-out (LOBO) letter accuracy and the banner reads of every played board.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pytesseract

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))

from extract_frames import frame_at, frames, probe, recording_path  # noqa: E402

from whcore import letters as lt  # noqa: E402
from whcore.calibration import glyphs, load_calibration, load_rgb  # noqa: E402

WH_DATA = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
CAL = load_calibration(ROOT / "fixtures/calibration/iphone-1206x2622.json")
OUT = WH_DATA / "templates"
FIX = ROOT / "fixtures/templates"
FRAMES_PER_BOARD = 5


def tesseract_digits(gray: np.ndarray) -> str:
    """Digits after the colon of a 'LABEL: 123' line, read by tesseract."""
    big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, b = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if b.mean() < 128:
        b = 255 - b
    b = cv2.copyMakeBorder(b, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    txt = pytesseract.image_to_string(
        b, config="--psm 7 -c tessedit_char_whitelist=WORDSCE:0123456789"
    )
    m = re.search(r":\s*(\d+)", txt)
    return m.group(1) if m else ""


def load_boards() -> list[dict]:
    auto = {
        (r["recording"], r["seq"]): r
        for r in csv.DictReader(open(WH_DATA / "labels/auto_boards.csv"))
    }
    out = []
    for r in csv.DictReader(open(WH_DATA / "labels/boards.csv")):
        if len(r["letters"]) == 16:
            out.append({**auto[(r["recording"], r["seq"])], **r})
    return out


def letter_samples(boards: list[dict]) -> dict[str, list[tuple[str, np.ndarray]]]:
    """board key → [(letter, glyph)] from several frames spread over the board's run."""
    samples: dict[str, list] = defaultdict(list)
    png = load_rgb(WH_DATA / "recordings/IMG_0717.PNG")
    img0717 = json.loads((ROOT / "fixtures/boards/img0717.json").read_text())["letters"]
    samples["img0717"] = list(zip(img0717, glyphs(png, CAL), strict=True))
    for b in boards:
        key = f"{b['recording']}-{b['seq']}"
        t0, t1 = int(b["t_start_ms"]), int(b["t_end_ms"])
        times = [int(b["board_frame_ms"])]
        if t1 - t0 > 2000:
            times += list(np.linspace(t0 + 1000, t1 - 300, FRAMES_PER_BOARD - 1).astype(int))
        for t in times:
            img = frame_at(b["recording"], t)
            samples[key] += list(zip(b["letters"], glyphs(img, CAL), strict=True))
    return samples


def lobo(samples) -> tuple[float, list]:
    """Leave-one-board-out accuracy on each board's first (clearest) frame."""
    correct = total = 0
    errors = []
    for key, items in samples.items():
        train: dict[str, list] = defaultdict(list)
        for k2, it2 in samples.items():
            if k2 != key:
                for ch, g in it2:
                    train[ch].append(g)
        tpl = lt.build_letter_templates(train)
        for i, (ch, g) in enumerate(items[:16]):
            pred, _, margin = lt.classify_glyph(g, tpl)
            total += 1
            if pred == ch:
                correct += 1
            else:
                errors.append((key, i, ch, pred, round(margin, 3), ch in train))
    return correct / total, errors


def digit_samples(boards: list[dict]) -> dict[str, list[np.ndarray]]:
    acc: dict[str, list] = defaultdict(list)
    for b in boards:
        if b["status"] != "played":
            continue
        path = recording_path(b["recording"])
        meta = probe(path)
        t0 = int(b["t_start_ms"]) / 1000
        dur = (int(b["t_end_ms"]) - int(b["t_start_ms"])) / 1000
        imgs = [
            f
            for i, f in enumerate(frames(path, meta["width"], meta["height"], 0.5, t0, dur))
            if i % 2 == 0
        ]
        imgs.append(frame_at(b["recording"], int(b["t_end_ms"]) - 100))
        rects = [CAL["roi_banner_words"], CAL["roi_banner_score"]]
        pairs = [(img, r) for img in imgs for r in rects]
        end = frame_at(b["recording"], int(b["end_t_ms"]))
        pairs += [(end, CAL["roi_end_words"]), (end, CAL["roi_end_score"])]
        for img, rect in pairs:
            gray = lt.gray_roi(img, rect)
            boxes = lt.line_digit_boxes(gray)
            txt = tesseract_digits(gray)
            if txt and len(txt) == len(boxes):
                for ch, box in zip(txt, boxes, strict=True):
                    acc[ch].append(lt.norm_glyph(gray, box))
    return acc


def main() -> int:
    boards = load_boards()
    print(f"{len(boards)} labelled boards")
    samples = letter_samples(boards)
    acc, errors = lobo(samples)
    n = sum(len(v[:16]) for v in samples.values())
    print(f"LOBO letter accuracy {acc:.4f} on {n} tiles; errors: {errors}")
    pooled: dict[str, list] = defaultdict(list)
    for items in samples.values():
        for ch, g in items:
            pooled[ch].append(g)
    letters = lt.build_letter_templates(pooled)
    print(
        "letters with templates:", "".join(sorted(letters)), {k: len(v) for k, v in pooled.items()}
    )

    dsamp = digit_samples(boards)
    print("digit samples:", {k: len(v) for k, v in sorted(dsamp.items())})
    digits = {k: np.mean(v, axis=0).astype(np.float32) for k, v in dsamp.items()}

    for name, tpl in (("letters", letters), ("digits", digits)):
        lt.save_templates(tpl, OUT / f"{name}.npz")
        FIX.mkdir(parents=True, exist_ok=True)
        shutil.copy(OUT / f"{name}.npz", FIX / f"{name}.npz")

    # banner reads with the new templates
    for b in boards:
        if b["status"] != "played":
            continue
        live = lt.read_banner(frame_at(b["recording"], int(b["t_end_ms"]) - 100), CAL, digits)
        end = lt.read_banner(frame_at(b["recording"], int(b["end_t_ms"])), CAL, digits, end=True)
        conf = min(live[2], end[2])
        print(f"{b['recording']} #{b['seq']}: live {live[:2]} end {end[:2]} conf {conf:.3f}")
    return 0 if acc >= 0.99 else 1


if __name__ == "__main__":
    sys.exit(main())
