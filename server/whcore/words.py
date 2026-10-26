"""Traced tiles → words (S0.T11, PLAN §3.2).

Accepted attempts sometimes miss a tile (fast swipes: often the last one) or pick up a spurious
one (sliding past a neighbour). Each observed tile sequence is aligned against solver paths;
cost = missing + extra tiles (order preserved). Ties prefer the straighter path. A small search
then makes the board-level choice consistent: distinct words, total points == end SCORE, and the
visible end-screen words present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

from .oracle.traces import path_is_contiguous
from .scoring import word_points
from .solver import direction_changes

MAX_COST = 3
OOV_COST = 1
TOP_K = 6
MAX_SEARCH = 1_000_000


def word_of(path: list[int], letters: str) -> str:
    return "".join(letters[i] for i in path).lower()


def lcs(a: list[int], b: list[int]) -> int:
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def align_cost(observed: list[int], path: list[int]) -> int:
    """Missing + extra tiles to turn the observed sequence into the path."""
    return len(observed) + len(path) - 2 * lcs(observed, path)


@dataclass
class Choice:
    word: str
    path: list[int]
    cost: int
    turns: int
    oov: bool = False  # traced cleanly but not in the dictionary (evidence for the ledger)


@dataclass
class Resolved:
    observed: list[int]
    choices: list[Choice] = field(default_factory=list)  # ranked candidates
    pick: int = 0

    @property
    def chosen(self) -> Choice | None:
        return self.choices[self.pick] if self.choices else None

    @property
    def exact(self) -> bool:
        return bool(self.choices) and self.choices[0].cost == 0

    @property
    def ambiguous(self) -> bool:
        c = self.choices
        return len(c) > 1 and (c[0].cost, c[0].turns) == (c[1].cost, c[1].turns)


def candidates(observed: list[int], solution: dict, letters: str = "") -> list[Choice]:
    out = []
    for word, info in solution.items():
        best = None
        for p in info["paths"]:
            c = align_cost(observed, p)
            if c <= MAX_COST and (best is None or (c, direction_changes(p)) < best[:2]):
                best = (c, direction_changes(p), p)
        if best:
            out.append(Choice(word, best[2], best[0], best[1]))
    # a clean contiguous trace of a word the dictionary lacks: the game may know it (§6)
    raw = word_of(observed, letters) if letters else ""
    if raw and len(observed) >= 3 and raw not in solution and path_is_contiguous(observed):
        out.append(Choice(raw, list(observed), OOV_COST, direction_changes(observed), oov=True))
    out.sort(key=lambda ch: (ch.cost, ch.oov, ch.turns, ch.word))
    return out


def resolve_board(
    observed: list[list[int]],
    solution: dict,
    letters: str = "",
    end_score: int | None = None,
    visible: set[str] | None = None,
) -> list[Resolved]:
    """One word per accepted attempt, distinct across the board."""
    visible = visible or set()
    res = [Resolved(o, candidates(o, solution, letters)[: TOP_K * 3]) for o in observed]
    # exact, unique reads are fixed; the rest take their best unused candidate
    used: set[str] = set()
    for r in res:  # a repeated exact read can't be a second acceptance: re-resolve it
        if r.exact and not r.ambiguous and r.chosen.word in used:
            r.choices = [c for c in r.choices if c.cost > 0]
        elif r.exact and not r.ambiguous:
            used.add(r.chosen.word)
    for r in res:
        if r.exact and not r.ambiguous:
            continue
        r.choices = [c for c in r.choices if c.word not in used][:TOP_K]
        r.pick = 0
        if r.chosen:
            used.add(r.chosen.word)
    _fix_duplicates(res)
    if end_score is not None:
        _search(res, end_score, visible)
    return res


def _fix_duplicates(res: list[Resolved]) -> None:
    seen: set[str] = set()
    for r in res:
        while r.chosen and r.chosen.word in seen and r.pick + 1 < len(r.choices):
            r.pick += 1
        if r.chosen:
            seen.add(r.chosen.word)


def total_points(res: list[Resolved]) -> int:
    return sum(word_points(len(r.chosen.word)) for r in res if r.chosen)


def _search(res: list[Resolved], end_score: int, visible: set[str]) -> None:
    """Re-pick non-exact attempts so words stay distinct, the total matches, and visible words
    are covered; minimise total alignment cost."""
    free = [i for i, r in enumerate(res) if not r.exact or r.ambiguous]
    if not free:
        return
    fixed = {res[i].chosen.word for i in range(len(res)) if i not in free and res[i].chosen}
    fixed_pts = sum(word_points(len(w)) for w in fixed)

    def score(combo) -> tuple:
        words = [res[i].choices[k].word for i, k in zip(free, combo, strict=True)]
        if len(set(words)) < len(words) or fixed & set(words):
            return None
        pts = fixed_pts + sum(word_points(len(w)) for w in words)
        missing_visible = len(visible - fixed - set(words))
        cost = sum(
            res[i].choices[k].cost * 10 + res[i].choices[k].turns
            for i, k in zip(free, combo, strict=True)
        )
        return (pts != end_score, missing_visible, cost)

    ranges = [range(len(res[i].choices)) for i in free]
    n = 1
    for r in ranges:
        n *= max(1, len(r))
    if n > MAX_SEARCH or any(len(r) == 0 for r in ranges):
        return
    best = None
    for combo in product(*ranges):
        s = score(combo)
        if s is not None and (best is None or s < best[0]):
            best = (s, combo)
    if best:
        for i, k in zip(free, best[1], strict=True):
            res[i].pick = k


def build_words(attempts, letters: str, solution: dict, end_score: int | None = None,
                visible: set[str] | None = None) -> list[dict]:  # fmt: skip
    """S1 signature: accepted attempts (schema Attempt or dicts with tiles_seen/release_state) →
    one resolved word per accepted attempt, in order."""

    def get(a, k):
        return a[k] if isinstance(a, dict) else getattr(a, k)

    acc = [a for a in attempts if get(a, "release_state") == "valid_new"]
    res = resolve_board([list(get(a, "tiles_seen")) for a in acc], solution, letters.lower(),
                        end_score, visible)  # fmt: skip
    return [
        {
            "word": r.chosen.word if r.chosen else None,
            "path": r.chosen.path if r.chosen else None,
            "observed": r.observed,
            "cost": r.chosen.cost if r.chosen else None,
            "oov": r.chosen.oov if r.chosen else None,
            "ambiguous": r.ambiguous,
            "t_start_ms": get(a, "t_start_ms"),
        }
        for r, a in zip(res, acc, strict=True)
    ]
