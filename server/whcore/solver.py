"""Trie + DFS solver for a 4x4 Word Hunt board (PLAN §1, §3.4, §6)."""

from __future__ import annotations

from pathlib import Path

from .scoring import MAX_LEN, MIN_LEN, word_points

SIZE = 4
END = "$"  # trie terminal marker


def neighbours(i: int) -> list[int]:
    r, c = divmod(i, SIZE)
    out = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if (dr or dc) and 0 <= r + dr < SIZE and 0 <= c + dc < SIZE:
                out.append((r + dr) * SIZE + c + dc)
    return out


ADJ = [neighbours(i) for i in range(SIZE * SIZE)]


def normalise(word: str) -> str | None:
    """Lowercase a–z word of 3–16 letters, else None."""
    w = word.strip().lower()
    if MIN_LEN <= len(w) <= MAX_LEN and w.isascii() and w.isalpha():
        return w
    return None


def load_words(path: str | Path) -> set[str]:
    words = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            w = normalise(line)
            if w:
                words.add(w)
    return words


def build_trie(words) -> dict:
    root: dict = {}
    for w in words:
        node = root
        for ch in w:
            node = node.setdefault(ch, {})
        node[END] = True
    return root


def load_trie(path: str | Path) -> dict:
    return build_trie(load_words(path))


def direction_changes(path: list[int]) -> int:
    dirs = [
        (b // SIZE - a // SIZE, b % SIZE - a % SIZE) for a, b in zip(path, path[1:], strict=False)
    ]
    return sum(1 for d0, d1 in zip(dirs, dirs[1:], strict=False) if d0 != d1)


def solve_paths(letters: str, trie: dict) -> dict[str, list[list[int]]]:
    """Every dictionary word on the board → all tile paths that spell it."""
    board = letters.lower()
    if len(board) != SIZE * SIZE:
        raise ValueError("board must have 16 letters")
    found: dict[str, list[list[int]]] = {}
    path: list[int] = []
    used = [False] * (SIZE * SIZE)

    def dfs(i: int, node: dict, prefix: str) -> None:
        nxt = node.get(board[i])
        if nxt is None:
            return
        used[i] = True
        path.append(i)
        word = prefix + board[i]
        if END in nxt and len(word) >= MIN_LEN:
            found.setdefault(word, []).append(path.copy())
        for j in ADJ[i]:
            if not used[j]:
                dfs(j, nxt, word)
        path.pop()
        used[i] = False

    for i in range(SIZE * SIZE):
        dfs(i, trie, "")
    return found


def best_path(paths: list[list[int]]) -> list[int]:
    """Path with the fewest direction changes (ties: lexicographically smallest)."""
    return min(paths, key=lambda p: (direction_changes(p), p))


def solve(letters: str, trie: dict) -> dict[str, dict]:
    """word → {"paths", "best_path", "points"}."""
    return {
        w: {"paths": ps, "best_path": best_path(ps), "points": word_points(len(w))}
        for w, ps in solve_paths(letters, trie).items()
    }


def max_points(solution: dict) -> int:
    return sum(word_points(len(w)) for w in solution)
