"""Export the generated OpenAPI document to docs/openapi.json.

Run from backend/:  python scripts/export_openapi.py
"""

from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("SECRET_KEY", "openapi-export")

from app.main import app  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "openapi.json")


def main() -> int:
    schema = app.openapi()
    assert schema.get("openapi", "").startswith("3.1"), "expected OpenAPI 3.1"
    path = os.path.abspath(OUT)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(schema, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {path} ({len(schema.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
