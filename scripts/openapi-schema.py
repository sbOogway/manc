"""Write the API's OpenAPI document to site/openapi.json; `npm run types` turns it into TypeScript.

A test fails when the committed file drifts from the app, so the site's types follow the API.
"""

import json
import sys
from pathlib import Path

from manc.api.app import create_app
from manc.config import load_config

TARGET = Path(__file__).resolve().parents[1] / "site" / "openapi.json"


def document() -> dict:
    return create_app(load_config(), store=None).openapi()  # type: ignore[arg-type]


def main() -> int:
    text = json.dumps(document(), indent=2, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        if TARGET.read_text() != text:
            print(f"{TARGET} is stale: run `uv run python scripts/openapi-schema.py`")
            return 1
        return 0
    TARGET.write_text(text)
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
