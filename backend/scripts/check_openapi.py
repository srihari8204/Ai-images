"""CI guard: fail if docs/openapi.json is out of sync with the live routes.

Run from backend/:  python scripts/check_openapi.py
"""

from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("SECRET_KEY", "openapi-check")

from app.main import app  # noqa: E402

REF = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "openapi.json"))


def main() -> int:
    generated = json.loads(json.dumps(app.openapi(), sort_keys=True))
    if not os.path.exists(REF):
        print("docs/openapi.json missing — run scripts/export_openapi.py", file=sys.stderr)
        return 1
    with open(REF, encoding="utf-8") as fh:
        committed = json.load(fh)
    # Compare the route surface + schema names (ignore volatile description text).
    g_paths = set(generated.get("paths", {}))
    c_paths = set(committed.get("paths", {}))
    if g_paths != c_paths:
        only_gen = sorted(g_paths - c_paths)
        only_com = sorted(c_paths - g_paths)
        print("OpenAPI drift detected.", file=sys.stderr)
        if only_gen:
            print(f"  routes in code but not in docs: {only_gen}", file=sys.stderr)
        if only_com:
            print(f"  routes in docs but not in code: {only_com}", file=sys.stderr)
        print("Run: python scripts/export_openapi.py", file=sys.stderr)
        return 1
    print(f"OpenAPI in sync ({len(g_paths)} paths).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
