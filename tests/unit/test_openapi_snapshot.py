"""The committed contract (docs/contracts/openapi.json) matches the running API. When this fails
after a deliberate change, regenerate it: `.venv/bin/python -m tools.export_openapi`, and tell
the app side (docs/contracts/api.md)."""

from __future__ import annotations

from pathlib import Path

from tools.export_openapi import OUT, render


def test_openapi_matches_committed_snapshot() -> None:
    assert Path(OUT).exists(), "run: .venv/bin/python -m tools.export_openapi"
    assert render() == Path(OUT).read_text(), (
        "API contract changed: run `.venv/bin/python -m tools.export_openapi`, review the diff, "
        "and update docs/contracts/api.md"
    )
