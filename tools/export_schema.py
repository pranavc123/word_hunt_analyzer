"""Export the event JSON Schema to fixtures/schema/v1.json (--check: fail if stale)."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from whcore.schema import SCHEMA_VERSION, json_schema  # noqa: E402

OUT = ROOT / "fixtures" / "schema" / f"{SCHEMA_VERSION}.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = json.dumps(json_schema(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT} is stale; run tools/export_schema.py", file=sys.stderr)
            return 1
        print("schema up to date")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
