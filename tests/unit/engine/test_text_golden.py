"""L3 goldens: the port builds exactly the reference tajweed_ai builds, for every case in
tests/golden/references.json (made by tools/golden/make_text_golden.py in tajweed_ai's own
environment). Text, phonetic script, segments and tajweed spans must match verbatim; the sifat
and the character mappings by hash.

The lab stays on quran-transcript `+muaalem.1`; this repo uses `+muaalem.2` (vendor
MUAALEM_PATCHES.md, patch 3). Where patch 3 changes a golden case, it is listed below and checked
with that one change undone, so anything else that differs still fails."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.engine.text.moshaf import moshaf_from_dict
from app.engine.text.qt import alph
from app.engine.text.reference import build_reference
from app.engine.text.structure import TextSelection
from app.engine.text.tajweed import tajweed_spans
from tools.golden.summary import sha256_of, summarize

GOLDENS: list[dict[str, Any]] = json.loads(
    (Path(__file__).resolve().parents[2] / "golden" / "references.json").read_text()
)


# patch 3b: «بَسَطتَ» (5:28), a ط merged incompletely into ت, has no qalqalah here
PATCH_3B_CASES = {'5:28-29|istiaatha|{"madd_aared_len": 2}'}

# ways the lab offered that Hafs via al-Shatibiyya doesn't have (rules.FROM_SOURCES)
REMOVED_WAYS = {"yalhath_dhalik": "izhar", "irkab_maana": "izhar"}


def _sifat_without_patch_3b(sifat: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [dict(s) for s in sifat]
    for s, nxt in zip(out, out[1:], strict=False):
        if (
            s["phonemes"] == alph.phonetics.taa_mofakhama
            and nxt["phonemes"][0] == alph.phonetics.taa
        ):
            s["qalqla"] = "moqalqal"
    return out


def _id(golden: dict[str, Any]) -> str:
    c = golden["case"]
    extra = "+".join(c["prefixes"]) + ("|" + json.dumps(c["reading"]) if c["reading"] else "")
    return f"{c['sura']}:{c['aya_start']}-{c['aya_end']}{'|' + extra if extra else ''}"


@pytest.mark.parametrize("golden", GOLDENS, ids=_id)
def test_port_matches_lab(golden: dict[str, Any]) -> None:
    c = golden["case"]
    text = TextSelection(c["sura"], c["aya_start"], c["aya_end"], prefixes=tuple(c["prefixes"]))
    if c["reading"].items() & REMOVED_WAYS.items():
        # izhar at يلهث ذلك / اركب معنا: al-Tayyiba's only, so no longer a way to connect there
        with pytest.raises(ValueError, match="is not a way to connect"):
            build_reference(text, moshaf_from_dict(c["reading"], stored=True))
        return
    # read back as stored: idgham in ن والقلم is no longer offered, but still checks that the
    # port phonetizes it as the lab does
    ref = build_reference(text, moshaf_from_dict(c["reading"], stored=True))
    got = summarize(ref, tajweed_spans(ref.uthmani, ref.phonetic))
    if _id(golden) in PATCH_3B_CASES:
        sifat = _sifat_without_patch_3b([s.model_dump() for s in ref.phonetic.sifat])
        assert got["sifat_sha256"] != golden["expected"]["sifat_sha256"], "patch 3b not applied"
        got["sifat_sha256"] = sha256_of(sifat)
    for key, expected in golden["expected"].items():
        assert got[key] == expected, key


def test_goldens_cover_the_special_places() -> None:
    assert len(GOLDENS) >= 200
    sakt_cases = [g for g in GOLDENS if "sakt_man_raq" in g["case"]["reading"]]
    assert sakt_cases
