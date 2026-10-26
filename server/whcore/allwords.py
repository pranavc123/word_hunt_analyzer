"""VIEW ALL WORDS capture → per-length counts, found words, board match, slot evidence
(S0.T12, PLAN §3.5–3.7).

Screen (measured on allwords1, 1206×2622): a pinned header (back, REVEAL ALL) above a scrolling
list. One row per valid word, longest first, alphabetical within a length; pitch ≈ 61 px.
A row is a bar at x≈344 (yellow with a single "?" when unfound, brown with the word when found)
and the word's points in white at x≈760–940. The masked length comes from the points column.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

import cv2
import numpy as np

from .letters import classify_glyph, ink_components, norm_glyph
from .scoring import word_points

LIST_Y0, LIST_Y1 = 612, 2600  # visible list band (below the pinned header)
BAR_X0, BAR_X1 = 330, 740
PTS_X0, PTS_X1 = 740, 960
PROFILE_X0, PROFILE_X1 = 330, 940
PITCH = 61.1
MIN_OVERLAP = 300  # px of profile two frames must share to estimate a shift
GAP_COST = 25  # mean |diff| above this = frames do not overlap (motion blur stays ~15–20)
POINTS_TO_LEN = {word_points(n): n for n in range(3, 17)}


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    d = np.diff(np.r_[0, mask.astype(int), 0])
    return list(zip(np.where(d == 1)[0].tolist(), np.where(d == -1)[0].tolist(), strict=True))


def profile(img: np.ndarray) -> np.ndarray:
    """1-D row-intensity profile of the scrolling band (PLAN §2.6)."""
    return img[LIST_Y0:LIST_Y1, PROFILE_X0:PROFILE_X1].mean(axis=(1, 2))


def estimate_shift(prev: np.ndarray, cur: np.ndarray, predicted: int = 0, max_shift: int = 1500,
                   min_overlap: int = MIN_OVERLAP, step: int = 1) -> tuple[int, float]:  # fmt: skip
    """Content shift s (cur[y] ≈ prev[y + s]; s > 0 = scrolled down) minimising mean |diff|,
    with a small pull towards the predicted shift (rows repeat every ~61 px)."""
    n = len(prev)
    best = (np.inf, 0, np.inf)
    for s in range(-max_shift, max_shift + 1, step):
        a0, a1 = max(0, -s), min(n, n - s)
        if a1 - a0 < min_overlap:
            continue
        cost = float(np.abs(cur[a0:a1] - prev[a0 + s : a1 + s]).mean())
        score = cost + 0.004 * abs(s - predicted)
        if score < best[0]:
            best = (score, s, cost)
    return best[1], best[2]


@dataclass
class Row:
    y: int  # centre, screen coordinates
    kind: str  # masked | found | unknown
    bar_w: int
    points: int | None
    points_conf: float
    word_crop: np.ndarray | None = field(default=None, repr=False)


def _bar_masks(img: np.ndarray):
    """Bright bar pixels split by hue: yellow (masked, ~(249,246,131)) vs tan (found,
    ~(228,183,118))."""
    r, g, b = (img[..., i].astype(int) for i in range(3))
    bar = (r > 170) & (r - b > 60)
    yellow = bar & (g > r - 20)
    tan = bar & (r - g > 30)
    return yellow, tan


def read_points(gray: np.ndarray, digits: dict) -> tuple[int | None, float]:
    """White digits on the dark panel → int via the (dark-ink) digit templates."""
    inv = 255 - gray
    boxes = [b for b in ink_components(inv) if b[3] >= 0.6 * gray.shape[0] * 0.5]
    if not boxes:
        return None, 0.0
    tall = max(b[3] for b in boxes)
    boxes = [b for b in boxes if b[3] >= 0.75 * tall]
    out, worst = [], 1.0
    for b in boxes:
        ch, score, _ = classify_glyph(norm_glyph(inv, b), digits)
        out.append(ch)
        worst = min(worst, score)
    return int("".join(out)), worst


def parse_rows(img: np.ndarray, digits: dict) -> list[Row]:
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    band = gray[LIST_Y0:LIST_Y1]
    white = band[:, PTS_X0:PTS_X1] > 200
    yellow, brown = _bar_masks(img[LIST_Y0:LIST_Y1, BAR_X0:BAR_X1])
    rows = []
    for a, b in _runs(white.any(1)):
        if b - a < 18 or a == 0 or b >= len(band) - 1:  # partial rows at the band edges
            continue
        yc = (a + b) // 2
        ys = slice(max(0, yc - 14), yc + 14)
        ny, nb = yellow[ys].sum(), brown[ys].sum()
        kind = "masked" if ny > nb and ny > 400 else "found" if nb > 400 else "unknown"
        cols = np.where(yellow[yc] if kind == "masked" else brown[yc])[0]
        bar_w = int(cols[-1] - cols[0]) if len(cols) else 0
        pts, conf = read_points(band[a - 4 : b + 4, PTS_X0:PTS_X1], digits)
        crop = None
        if kind == "found" and len(cols) > 20:  # tight crop inside the tan bar
            x0, x1 = BAR_X0 + int(cols[0]) + 8, BAR_X0 + int(cols[-1]) - 6
            crop = img[LIST_Y0 + yc - 20 : LIST_Y0 + yc + 20, x0:x1]
        rows.append(Row(LIST_Y0 + yc, kind, bar_w, pts, conf, crop))
    return rows


# ---- stitching ---------------------------------------------------------------


@dataclass
class Slot:
    kinds: Counter = field(default_factory=Counter)
    points: Counter = field(default_factory=Counter)
    widths: list[int] = field(default_factory=list)
    crops: list = field(default_factory=list)
    word: str | None = None

    @property
    def kind(self) -> str:
        return self.kinds.most_common(1)[0][0]

    @property
    def length(self) -> int | None:
        for pts, _ in self.points.most_common():
            if pts in POINTS_TO_LEN:
                return POINTS_TO_LEN[pts]
        return None


@dataclass
class Capture:
    slots: dict[int, Slot]
    shifts: list[int]
    costs: list[float]
    gap_flags: list[bool]
    bounced_at_end: bool
    offsets: list[int]

    def ordered(self) -> list[Slot]:
        return [self.slots[k] for k in sorted(self.slots)]


def stitch(frames, digits: dict, max_shift: int = 1500) -> Capture:
    """Track scroll offset frame to frame and pool row observations into list slots."""
    slots: dict[int, Slot] = defaultdict(Slot)
    shifts, costs, gaps, offsets = [], [], [], []
    prev, offset, velocity, y_ref = None, 0, 0, None
    reached_end = False
    for img in frames:
        prof = profile(img)
        if prev is not None:
            s, c = estimate_shift(prev, prof, velocity, max_shift)
            shifts.append(s)
            costs.append(c)
            gaps.append(abs(s) > (LIST_Y1 - LIST_Y0) - MIN_OVERLAP or c > GAP_COST)
            offset += s
            velocity = s
        still = prev is None or (shifts and shifts[-1] == 0)
        prev = prof
        offsets.append(offset)
        rows = parse_rows(img, digits)
        # end of list: rows on screen but the last one sits well above the band bottom
        if len(rows) >= 3 and rows[-1].y < LIST_Y1 - 2 * PITCH:
            reached_end = True
        for row in rows:
            abs_y = row.y + offset
            if y_ref is None:
                y_ref = abs_y
            k = int(round((abs_y - y_ref) / PITCH))
            sl = slots[k]
            sl.kinds[row.kind] += 1
            if row.points is not None and row.points_conf > 0.5:
                sl.points[row.points] += 1
            if row.bar_w:
                sl.widths.append(row.bar_w)
            # word crops only from still frames (no motion blur)
            if row.word_crop is not None and still and len(sl.crops) < 3:
                sl.crops.append(row.word_crop)
    return Capture(dict(slots), shifts, costs, gaps, reached_end, offsets)


# ---- analysis ----------------------------------------------------------------


def summarise(cap: Capture) -> dict:
    """Per-length counts (all / masked / found), self-checks, completeness (§3.5)."""
    rows = cap.ordered()
    lengths = [s.length for s in rows]
    total, masked, found = Counter(), Counter(), Counter()
    for s, n in zip(rows, lengths, strict=True):
        if n is None:
            continue
        total[n] += 1
        (masked if s.kind == "masked" else found)[n] += 1
    known = [n for n in lengths if n is not None]
    non_increasing = all(a >= b for a, b in zip(known, known[1:], strict=False))
    found_words = [(s.length, s.word) for s in rows if s.kind == "found" and s.word]
    alpha = all(
        w1 <= w2
        for (n1, w1), (n2, w2) in zip(found_words, found_words[1:], strict=False)
        if n1 == n2
    )
    order = sorted(total, reverse=True)
    # a length is complete once the next shorter one starts (and the shortest needs the bounce)
    complete = [n for i, n in enumerate(order) if i + 1 < len(order) or cap.bounced_at_end]
    status = "complete" if (cap.bounced_at_end and not any(cap.gap_flags)) else "partial"
    return {
        "counts_by_length": dict(sorted(total.items(), reverse=True)),
        "masked_counts_by_length": dict(sorted(masked.items(), reverse=True)),
        "found_counts_by_length": dict(sorted(found.items(), reverse=True)),
        "unknown_rows": sum(n is None for n in lengths),
        "lengths_non_increasing": non_increasing,
        "found_alphabetical": alpha,
        "status": status,
        "complete_down_to": min(complete) if complete and status == "complete" else None,
        "bounced_at_end": cap.bounced_at_end,
        "gap_frames": int(sum(cap.gap_flags)),
    }


def list_order(words) -> list[str]:
    """GamePigeon's all-words order: longest first, alphabetical within a length."""
    return sorted(words, key=lambda w: (-len(w), w))


def match_revealed(revealed: list[str], boards: list[dict], min_frac: float = 0.8):
    """§3.6 as observed: VIEW ALL WORDS reveals only the player's first K found words in list
    order (K=20 on allwords1); later found words look masked. A board matches when the revealed
    words are exactly the first K of its accepted words in list order.
    boards: [{"id", "words", "t"}]. Returns (match_state, board_id or None, candidate ids)."""
    if not revealed:
        return "unmatched", None, []
    scored = []
    for b in boards:
        prefix = list_order(b["words"])[: len(revealed)]
        hits = len(set(revealed) & set(prefix))
        if hits >= min_frac * len(revealed):
            scored.append((hits, b))
    if not scored:
        return "unmatched", None, []
    top = max(h for h, _ in scored)
    cands = [b for h, b in scored if h == top]
    if len(cands) == 1:
        return "matched", cands[0]["id"], [b["id"] for _, b in scored]
    best = max(cands, key=lambda b: b["t"])  # prefer the most recent
    return "ambiguous", best["id"], [b["id"] for b in cands]


def snap_revealed(raw: list[tuple[int | None, str]], boards: list[dict], max_dist: int = 2):
    """Snap OCR'd revealed words to accepted words of the right length on any candidate board."""
    from .reconcile import levenshtein

    vocab = {w for b in boards for w in b["words"]}
    out = []
    for n, w in raw:
        pool = [v for v in vocab if n is None or len(v) == n] or list(vocab)
        best = min(pool, key=lambda v: (levenshtein(w, v), v)) if pool else w
        out.append(best if levenshtein(w, best) <= max_dist else w)
    return out


def slot_evidence(rows: list[tuple[int | None, str, str | None]], accepted: set[str],
                  solver_words: set[str]) -> dict:  # fmt: skip
    """§3.7 inside the revealed stretch (rows up to the last revealed word, where every row's
    identity is pinned): a masked run between two known neighbours of its length must be exactly
    the unfound valid words sorting into that gap.
    rows: [(length, kind, word|None)] in list order. Returns confirmed/rejected/unknown_extra."""
    last = max((i for i, (_, k, w) in enumerate(rows) if k == "found" and w), default=-1)
    confirmed, rejected, extra = set(), set(), 0
    i = 0
    while i <= last:
        n, kind, word = rows[i]
        if kind != "masked" or n is None:
            i += 1
            continue
        j = i
        while j <= last and rows[j][1] == "masked" and rows[j][0] == n:
            j += 1
        lo = next((w for m, k, w in reversed(rows[:i]) if m == n and w), "")
        hi = next((w for m, k, w in rows[j : last + 1] if m == n and w), None)
        if hi is None:  # gap runs past the revealed stretch: unbounded above
            i = j
            continue
        gap = sorted(w for w in solver_words if len(w) == n and lo < w < hi and w not in accepted)
        if len(gap) == j - i:
            confirmed.update(gap)
        elif not gap:
            extra += j - i
        elif len(gap) > j - i and j - i == 0:
            rejected.update(gap)
        i = j
    # known neighbours with no masked row between them reject every solver word in that gap
    known = [(n, w) for n, k, w in rows[: last + 1] if k == "found" and w]
    for (n1, w1), (n2, w2) in zip(known, known[1:], strict=False):
        idx1 = rows.index((n1, "found", w1))
        idx2 = rows.index((n2, "found", w2))
        if n1 == n2 and idx2 == idx1 + 1:
            rejected.update(
                w for w in solver_words if len(w) == n1 and w1 < w < w2 and w not in accepted
            )
    return {"confirmed": sorted(confirmed), "rejected": sorted(rejected), "unknown_extra": extra}
