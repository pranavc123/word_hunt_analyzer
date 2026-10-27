"""Letter templates that improve with use (S4).

Starts from the committed S0 templates (each worth BASE_WEIGHT samples) and adds the 16 tile
glyphs of every board whose letters are known for sure: verified played boards and boards a person
confirmed. Persisted as running sums + counts in one .npz, so adding a board is cheap.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import letters as lt
from .calibration import glyphs

BASE_WEIGHT = 20


class TemplateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.sums: dict[str, np.ndarray] = {}
        self.counts: dict[str, float] = {}
        self.boards: set[str] = set()
        if self.path.exists():
            with np.load(self.path, allow_pickle=False) as z:
                for k in z.files:
                    if k.startswith("sum_"):
                        self.sums[k[4:]] = z[k].astype(np.float64)
                    elif k.startswith("n_"):
                        self.counts[k[2:]] = float(z[k])
                if "boards" in z.files:
                    self.boards = set(str(b) for b in z["boards"])
        else:
            for ch, t in lt.default_templates("letters").items():
                self.sums[ch] = t.astype(np.float64) * BASE_WEIGHT
                self.counts[ch] = float(BASE_WEIGHT)

    def templates(self) -> dict[str, np.ndarray]:
        return {ch: (self.sums[ch] / self.counts[ch]).astype(np.float32) for ch in self.sums}

    def add_board(self, board_id: str, img: np.ndarray, local_cal: dict, letters: str) -> bool:
        """Add a board's glyphs once (by id). img at calibration scale, local_cal relative to it."""
        if board_id in self.boards or len(letters) != 16:
            return False
        for ch, g in zip(letters.upper(), glyphs(img, local_cal), strict=True):
            self.sums[ch] = self.sums.get(ch, np.zeros_like(g, dtype=np.float64)) + g
            self.counts[ch] = self.counts.get(ch, 0.0) + 1.0
        self.boards.add(board_id)
        return True

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {f"sum_{k}": v for k, v in self.sums.items()}
        arrays.update({f"n_{k}": np.array(v) for k, v in self.counts.items()})
        arrays["boards"] = np.array(sorted(self.boards))
        tmp = self.path.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, **arrays)
        tmp.replace(self.path)
