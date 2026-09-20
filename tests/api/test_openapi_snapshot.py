"""site/openapi.json is the app's OpenAPI document; the site's types are generated from it."""

import json
import runpy
from pathlib import Path

from manc.api.app import create_app
from manc.config import load_config

SNAPSHOT = Path(__file__).resolve().parents[2] / "site" / "openapi.json"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "openapi-schema.py"


def test_snapshot_matches_the_app() -> None:
    document = create_app(load_config(), store=None).openapi()  # type: ignore[arg-type]
    assert json.loads(SNAPSHOT.read_text()) == document, (
        "site/openapi.json is stale: run scripts/openapi-schema.py, then `npm run types` in site/"
    )


def test_script_check_mode_agrees(capsys: object) -> None:
    module = runpy.run_path(str(SCRIPT))
    assert module["document"]() == json.loads(SNAPSHOT.read_text())
