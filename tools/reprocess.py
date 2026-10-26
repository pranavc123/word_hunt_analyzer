"""Re-run the worker pipeline over stored records (after a pipeline change).

uv run python tools/reprocess.py [--session ID] [--allwords]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from sqlmodel import select  # noqa: E402

from app import worker  # noqa: E402
from app.db import session  # noqa: E402
from app.models import AllWordsCapture, Board  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session")
    ap.add_argument("--allwords", action="store_true", help="also re-match all-words captures")
    args = ap.parse_args()
    with session() as s:
        q = select(Board).order_by(Board.opened_at)
        if args.session:
            q = q.where(Board.session_id == args.session)
        ids = [b.id for b in s.exec(q).all()]
        caps = [c.id for c in s.exec(select(AllWordsCapture)).all()] if args.allwords else []
    for i, bid in enumerate(ids, 1):
        print(f"[{i}/{len(ids)}] {bid}: {worker.run_board(bid)}")
    for rid in caps:
        print(f"all-words {rid}: {worker.run_allwords(rid)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
