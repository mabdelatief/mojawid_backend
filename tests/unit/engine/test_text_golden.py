"""L3 goldens: the port builds exactly the reference tajweed_ai builds, for every case in
tests/golden/references.json (made by tools/golden/make_text_golden.py in tajweed_ai's own
environment). Text, phonetic script, segments and tajweed spans must match verbatim; the sifat
and the character mappings by hash."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.engine.text.moshaf import moshaf_from_dict
from app.engine.text.reference import build_reference
from app.engine.text.structure import TextSelection
from app.engine.text.tajweed import tajweed_spans
from tools.golden.summary import summarize

GOLDENS: list[dict[str, Any]] = json.loads(
    (Path(__file__).resolve().parents[2] / "golden" / "references.json").read_text()
)


def _id(golden: dict[str, Any]) -> str:
    c = golden["case"]
    extra = "+".join(c["prefixes"]) + ("|" + json.dumps(c["reading"]) if c["reading"] else "")
    return f"{c['sura']}:{c['aya_start']}-{c['aya_end']}{'|' + extra if extra else ''}"


@pytest.mark.parametrize("golden", GOLDENS, ids=_id)
def test_port_matches_lab(golden: dict[str, Any]) -> None:
    c = golden["case"]
    text = TextSelection(c["sura"], c["aya_start"], c["aya_end"], prefixes=tuple(c["prefixes"]))
    ref = build_reference(text, moshaf_from_dict(c["reading"]))
    got = summarize(ref, tajweed_spans(ref.uthmani, ref.phonetic))
    for key, expected in golden["expected"].items():
        assert got[key] == expected, key


def test_goldens_cover_the_special_places() -> None:
    assert len(GOLDENS) >= 200
    sakt_cases = [g for g in GOLDENS if "sakt_man_raq" in g["case"]["reading"]]
    assert sakt_cases
