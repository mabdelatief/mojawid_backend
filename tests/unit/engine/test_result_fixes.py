"""Places where Mojawid's result differs from the lab on purpose (user's decisions, 2026-10-16),
found on the user's recording of al-Najm 23 and in the 2026-10-16 audit: the sifat table paired by
our own group alignment, a ghunnah where none is due named as a tajweed mistake, and a leen madd
written as a madd rather than a ghunnah."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.engine.pipeline.analysis.rows import GHUNNAH_OPERATION, ghunnah_state
from app.engine.pipeline.analysis.sifat import pair_groups, sifat_rows, tag_of
from app.engine.pipeline.heard import Heard, HeardGroup, SifaValue
from app.engine.text.letter_sifat import SIFAT_LEVELS
from app.engine.text.moshaf import build_moshaf
from app.engine.text.qt import alph
from app.engine.text.readable import SHADDA, describe
from app.engine.text.reference import build_reference_from_structure
from app.engine.text.structure import TextSelection, default_structure

P = alph.phonetics
M = build_moshaf()


def _perfect(sura: int, aya: int) -> tuple[Any, list[dict[str, Any]]]:
    """The sifat table for a perfect recitation of an ayah: heard script and sifat as expected."""
    ref = build_reference_from_structure(default_structure(TextSelection(sura, aya), M), M)
    sifat = [
        HeardGroup(s.phonemes, {lv: SifaValue(getattr(s, lv), 0.99, 1) for lv in SIFAT_LEVELS})
        for s in ref.phonetic.sifat
    ]
    sure = {lv: [True] * len(sifat) for lv in SIFAT_LEVELS}
    heard = Heard(
        text=ref.phonetic.phonemes,
        probs=[],
        ids=[],
        sifat=sifat,
        group_frames=[],
        sure=sure,
        gaps={},
        n_frames=0,
    )
    return ref, sifat_rows(heard, ref)


@pytest.mark.parametrize(
    ("sura", "aya"), [(53, 23), (1, 1), (2, 255), (3, 18), (24, 35), (112, 2), (59, 23)]
)
def test_a_perfect_recitation_gives_a_clean_sifat_table(sura: int, aya: int) -> None:
    # the lam of «ٱللَّهُ» was paired with the lam before it (quran-muaalem segment_groups): a
    # row lost and a made-up tafkheem mismatch on a perfect reading of 53:23
    ref, rows = _perfect(sura, aya)
    assert len(rows) == len(ref.phonetic.sifat)
    assert all(r["tag"] == "exact" and r["ref"] == r["pred"] for r in rows)
    assert not [lv for r in rows for lv, v in r["attrs"].items() if v["mismatch"]]


def test_pair_groups() -> None:
    assert pair_groups(["لَ", "للَ", "اا"], ["لَ", "للَ", "اا"]) == [(0, 0), (1, 1), (2, 2)]
    assert pair_groups(["كُ", "م", "سَ"], ["كُ", "ممم", "سَ"]) == [(0, 0), (1, 1), (2, 2)]
    assert pair_groups(["ءِ", "ييَ", "كَ"], ["ءِ", "كَ"]) == [(0, 0), (1, None), (2, 1)]
    assert pair_groups(["بَ"], ["بَ", "هْ"]) == [(0, 0), (None, 1)]
    assert tag_of("اااا", "ااااا") == "exact"  # a madd length is judged by the error rows
    assert tag_of("للَ", "لَ") == "changed"


def _explained(exp: str, got: str) -> SimpleNamespace:
    return SimpleNamespace(expected_ph=exp, preditected_ph=got, ref_tajweed_rules=None)


def test_a_ghunnah_where_none_is_due_is_unexpected() -> None:
    assert ghunnah_state(_explained(P.meem, P.meem * 3), "م") == "unexpected"
    assert ghunnah_state(_explained(P.noon + P.fatha, P.noon * 3 + P.fatha), "نَ") == "unexpected"
    assert GHUNNAH_OPERATION["unexpected"] == "insert"
    # a meem doubled but not held is not a ghunnah
    assert ghunnah_state(_explained(P.meem, P.meem * 2), "م") is None
    # a held ghunnah heard short is still "short"
    assert ghunnah_state(_explained(P.noon * 3 + P.fatha, P.noon + P.fatha), "نَّ") == "short"


def test_leen_madd_is_written_as_a_madd() -> None:
    leen = P.qaf + P.dama + P.raa + P.fatha + P.yaa * 3 + P.sheen
    assert describe(leen) == "قُرَيْشْ (مد ٤ حركات)"
    assert "غنة" not in describe(P.waw * 5)
    # a ghunnah held into a yaa still reads as a ghunnah: it has a haraka after it
    assert describe(P.yaa * 3 + P.fatha) == P.yaa + SHADDA + P.fatha + " (غنة)"
