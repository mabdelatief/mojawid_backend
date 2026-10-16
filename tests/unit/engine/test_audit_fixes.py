"""Fixes from the 2026-10-16 audit (docs/research/README.md), checked with constructed heard
scripts through the real analysis: idraj counted and named (R3), a stray haraka after a madd not
hidden, a leen madd of 3 harakat written as a madd (C7), and an insertion touching a row's edge
no longer making that row uncertain (C8)."""

from __future__ import annotations

from typing import Any

from app.engine.pipeline.analysis.marks import overlaps
from app.engine.pipeline.analysis.report import analyze
from app.engine.pipeline.heard import Heard
from app.engine.text.moshaf import moshaf_from_dict
from app.engine.text.qt import alph, chunck_phonemes
from app.engine.text.readable import describe
from app.engine.text.reference import Reference, build_reference_from_structure, phonetize
from app.engine.text.structure import TextSelection, default_structure

P = alph.phonetics


def ref_for(sura: int, aya: int, **reading: Any) -> Reference:
    m = moshaf_from_dict(reading or None)
    return build_reference_from_structure(default_structure(TextSelection(sura, aya), m), m)


def rows(ref: Reference, heard_text: str) -> list[dict[str, Any]]:
    h = Heard(text=heard_text, probs=[], ids=[], sifat=[], group_frames=[], sure=None, gaps={},
              n_frames=0)  # fmt: skip
    return list(analyze(h, ref)["errors"])


def counted(rs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rs if not r["likely_false_alarm"]]


def test_idraj_at_marqadina_is_counted_and_named() -> None:
    ref = ref_for(36, 52, sakt_marqdena="sakt")
    m_i = moshaf_from_dict({"sakt_marqdena": "sakt"}).model_copy(update={"sakt_marqdena": "idraj"})
    rs = counted(rows(ref, phonetize(ref.uthmani, m_i, 36).phonemes))
    assert rs, "idraj (no sakt) at «مَّرْقَدِنَا» must be a mistake (the teacher's ruling)"
    assert any("سكتة" in r["expected_text"] and "سكتة" not in r["heard_text"] for r in rs)


def test_sakt_heard_is_correct() -> None:
    ref = ref_for(36, 52, sakt_marqdena="sakt")
    assert counted(rows(ref, ref.phonetic.phonemes)) == []


def test_a_stray_haraka_after_a_madd_is_not_hidden() -> None:
    ref = ref_for(2, 4)
    groups = chunck_phonemes(ref.phonetic.phonemes)
    k = next(i for i, g in enumerate(groups) if g == P.alif * 4)  # the munfasil of «بِمَآ»
    heard = "".join(groups[:k]) + P.alif * 4 + P.fatha + "".join(groups[k + 1 :])
    assert counted(rows(ref, heard))


def test_right_madd_length_is_still_a_false_alarm() -> None:
    ref = ref_for(1, 1)  # an 'arid madd at the stop, read at the setting's length
    assert counted(rows(ref, ref.phonetic.phonemes)) == []


def test_leen_of_three_harakat_reads_as_a_madd() -> None:
    assert describe(P.waw * 2, leen=True) == "وْ (مد ٣ حركات)"
    assert describe(P.khaa + P.fatha + P.waw * 2 + P.faa) == "خَوْفْ (مد ٣ حركات)"  # after a fatha
    # a doubled waw at a stop after a damma is a shadda, not a leen («عَدُوّْ»)
    assert describe(P.daal + P.dama + P.waw * 2) == "دُوّْ"


def test_a_madd_ending_in_a_sakt_says_so() -> None:
    assert describe(P.alif * 2 + P.sakt) == "ا (مد حركتان، سكتة)"


def test_an_insertion_touching_a_row_is_not_part_of_it() -> None:
    assert overlaps(3, 5, 4, 4)  # inside the row
    assert not overlaps(3, 5, 5, 5)  # at its end: the next row's insertion
    assert not overlaps(3, 5, 3, 3)  # at its start
    assert overlaps(5, 5, 5, 5)  # an insertion row matches an insertion block at its point
    assert overlaps(3, 5, 4, 7)


def _madd_rows(sura: int, aya: int, edit: Any) -> list[dict[str, Any]]:
    ref = ref_for(sura, aya)
    rs = rows(ref, edit(ref.phonetic.phonemes))
    return [r for r in rs if any(x["en"] in ("Monfasel Madd", "Mottasel Madd") for x in r["rules"])]


def test_munfasil_5_with_muttasil_4_is_a_mistake() -> None:
    # 2:19 has a munfasil («فِىٓ ءَاذَانِهِم») and a muttasil («ٱلسَّمَآءِ»); the setting is 4/4
    rs = _madd_rows(2, 19, lambda ph: ph.replace("ۦۦۦۦء", "ۦۦۦۦۦء", 1))
    assert rs and not rs[0]["likely_false_alarm"] and "لا يصح الجمع" in rs[0]["consistency_ar"]


def test_munfasil_4_with_muttasil_5_is_allowed() -> None:
    rs = _madd_rows(2, 19, lambda ph: ph.replace("سَمَااااء", "سَمَاااااء", 1))
    assert rs and all(r["likely_false_alarm"] for r in rs)


def test_mixed_munfasil_lengths_are_a_mistake() -> None:
    # 2:4: two munfasil places; one read at 5, the other at the setting's 4 (taswiya)
    rs = _madd_rows(2, 4, lambda ph: ph.replace("ااااءُ", "اااااءُ", 1))
    assert (
        rs and not rs[0]["likely_false_alarm"] and "يخالف بقية التلاوة" in rs[0]["consistency_ar"]
    )
