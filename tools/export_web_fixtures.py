"""Dump real API responses from the dev database for the web tests (S4).

uv run python tools/seed_fixture_db.py && uv run python tools/export_web_fixtures.py
→ web/src/test/fixtures/{sessions,session,board_verified,board_letter_fix}.json
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL = Path(os.environ.get("WH_DATA", ROOT / "wordhunt-data"))
os.environ.update(
    WH_DATA=str(REAL / "dev"), WH_DB_URL=f"sqlite:///{REAL / 'dev.db'}", WH_TOKEN="dev"
)
sys.path.insert(0, str(ROOT / "server"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

OUT = ROOT / "web/src/test/fixtures"
AUTH = {"Authorization": "Bearer dev"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with TestClient(app) as c:
        sessions = c.get("/v1/sessions", headers=AUTH).json()
        # the session with letter fixes to do, for the summary + confirm screens
        sess = next(s for s in sessions if s["needs_letter_fix"])
        full = c.get(f"/v1/sessions/{sess['id']}", headers=AUTH).json()
        verified = next(b for b in full["boards"] if b["review_status"] == "verified")
        fix = next(b for b in full["boards"] if b["review_status"] == "needs_letter_fix")
        dumps = {
            "sessions": sessions,
            "session": full,
            "board_verified": c.get(f"/v1/boards/{verified['id']}", headers=AUTH).json(),
            "board_letter_fix": c.get(f"/v1/boards/{fix['id']}", headers=AUTH).json(),
        }
    for name, data in dumps.items():
        (OUT / f"{name}.json").write_text(json.dumps(data, indent=1) + "\n")
    print(f"wrote {len(dumps)} fixtures to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
