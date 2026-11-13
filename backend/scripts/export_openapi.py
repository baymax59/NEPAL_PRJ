"""Write the API description (OpenAPI) to a file, for generating the frontend's TypeScript types.

Needs no database and no real secrets:

    uv run python -m scripts.export_openapi ../docs/case-management/openapi.json
    cd ../frontend && npm run gen:api

The frontend's `src/api/schema.d.ts` is generated from it, so the screens use exactly the shapes the backend returns.
"""

import argparse
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    # Placeholders so the settings load; nothing is signed or stored.
    os.environ.setdefault("JWT_SECRET", "openapi-export-only-0123456789abcdefghijklmnop")
    os.environ.setdefault("AUDIT_SECRET", "openapi-export-only-0123456789abcdefghijklmnop")
    from app.main import app

    args.output.write_text(json.dumps(app.openapi(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(app.openapi()['paths'])} paths)")


if __name__ == "__main__":
    main()
