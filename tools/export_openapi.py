"""Write the FastAPI OpenAPI spec to web/openapi.json (then: pnpm -C web gen:api)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.main import app  # noqa: E402

OUT = ROOT / "web" / "openapi.json"
OUT.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
print(f"wrote {OUT.relative_to(ROOT)}")
