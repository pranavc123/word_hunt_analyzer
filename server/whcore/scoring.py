"""Word Hunt scoring (PLAN §1)."""

MIN_LEN = 3
MAX_LEN = 16
_BASE = {3: 100, 4: 400, 5: 800, 6: 1400}


def word_points(n: int) -> int:
    """Points for a word of n letters (n = 3..16)."""
    if n < MIN_LEN or n > MAX_LEN:
        raise ValueError(f"word length {n} outside {MIN_LEN}..{MAX_LEN}")
    return _BASE.get(n, 1400 + 400 * (n - 6))


def score(word: str) -> int:
    return word_points(len(word))
