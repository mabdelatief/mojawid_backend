"""Write the API's OpenAPI document to docs/contracts/openapi.json.

Run after changing a route or a wire model; tests/unit/test_openapi_snapshot.py fails until the
committed snapshot matches, so contract changes are always deliberate and reviewable.

    .venv/bin/python -m tools.export_openapi
"""

import json
import pathlib

from app.main import create_app

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "contracts" / "openapi.json"


def render() -> str:
    """The OpenAPI document as stable, pretty JSON."""
    return json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render())
    print(f"wrote {OUT.relative_to(REPO)}")
