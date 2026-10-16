"""How a recitation's structure (stops, connected ayat, restarts, special places) turns into the
reference phonetic script. Ported from tajweed_ai tests/test_structure.py."""

from __future__ import annotations

from typing import Any

import pytest

from app.engine.text.boundaries import special_boundaries
from app.engine.text.moshaf import build_moshaf
from app.engine.text.qt import explain_error, quran_phonetizer
from app.engine.text.quran_text import ayah_words, surah_list
from app.engine.text.reference import Reference, build_reference, build_reference_from_structure
from app.engine.text.structure import Structure, TextSelection, default_structure

MOSHAF = build_moshaf()


def sel(sura: int, aya: int, aya_end: int | None = None, **kw: Any) -> TextSelection:
    return TextSelection(sura, aya, aya_end, **kw)


def upstream(text: str, moshaf: Any = MOSHAF, sura: int = 0) -> str:
    """Exactly what the upstream trainer's collator produces for one segment."""
    return str(quran_phonetizer(text, moshaf, remove_spaces=True, sura_idx=sura).phonemes)


def assert_consistent(ref: Reference) -> None:
    assert len(ref.phonetic.mappings) == len(ref.uthmani)
    ph = ref.phonetic.phonemes
    assert explain_error(ref.uthmani, ph, ph, ref.phonetic.mappings) == []
    joined = "".join(
        upstream(seg.uthmani, ref.segment_moshaf(i), ref.sura if seg.kind == "recitation" else 0)
        for i, seg in enumerate(ref.segments)
    )
    assert ph == joined
    for seg in ref.segments:
        assert ref.uthmani[seg.start : seg.end] == seg.uthmani
        for w in seg.words:
            assert " " not in ref.uthmani[w.start : w.end]


def test_default_is_one_stop_per_ayah() -> None:
    ref = build_reference(sel(1, 2, 4), MOSHAF)
    assert [len(s.words) for s in ref.segments] == [4, 2, 3]
    assert all(s.words[-1].ayah_last for s in ref.segments)
    assert_consistent(ref)


def test_connected_ayat_are_wasl() -> None:
    st = default_structure(sel(1, 2, 3), MOSHAF)
    st.segments = [(0, 5)]
    ref = build_reference_from_structure(st, MOSHAF)
    assert len(ref.segments) == 1
    assert ref.phonetic.phonemes == upstream(ref.segments[0].uthmani, sura=1)
    stopped = build_reference(sel(1, 2, 3), MOSHAF).phonetic.phonemes
    assert ref.phonetic.phonemes != stopped  # ...لَمِۦۦنَ ررَ... vs ...لَمِۦۦۦۦن ءَررَ...
    assert_consistent(ref)


def test_restart_repeats_words() -> None:
    st = default_structure(sel(1, 2), MOSHAF)  # 4 words
    st.segments = [(0, 1), (1, 3)]  # stopped after word 1, went back to word 1
    ref = build_reference_from_structure(st, MOSHAF)
    assert [[w.word for w in s.words] for s in ref.segments] == [[0, 1], [1, 2, 3]]
    assert ref.uthmani.split(" ").count(ayah_words(1, 2)[1]) == 2
    assert_consistent(ref)


def test_mid_ayah_stop_and_word_range() -> None:
    st = default_structure(sel(2, 255, word_end=9), MOSHAF)
    assert st.segments == [(0, 9)]
    st.segments = [(0, 4), (5, 9)]
    ref = build_reference_from_structure(st, MOSHAF)
    assert len(ref.segments) == 2
    assert_consistent(ref)


def test_special_boundary_connected() -> None:
    st = default_structure(sel(75, 27), MOSHAF)  # وَقِيلَ مَنْ رَاقٍۢ — default sakt
    assert st.segments == [(0, 2)]
    assert st.special == {1: "sakt"}
    ref = build_reference_from_structure(st, MOSHAF)
    assert "ۜ" in ref.phonetic.phonemes
    assert ref.segments[0].moshaf_overrides == {"sakt_man_raq": "sakt"}
    assert_consistent(ref)


def test_connecting_without_sakt_is_refused() -> None:
    # teachers' ruling (Hafs via al-Shatibiyya): sakt is obligatory when connecting at the four
    # places, so idraj is never a correct reference
    st = default_structure(sel(75, 27), MOSHAF)
    st.special = {1: "idraj"}
    with pytest.raises(ValueError):
        build_reference_from_structure(st, MOSHAF)


def test_special_boundary_stop_splits() -> None:
    st = default_structure(sel(75, 27), MOSHAF)
    st.segments, st.special = [(0, 1), (2, 2)], {}
    ref = build_reference_from_structure(st, MOSHAF)
    assert len(ref.segments) == 2
    assert "ۜ" not in ref.phonetic.phonemes
    assert_consistent(ref)


def test_default_waqf_place_splits_mid_ayah() -> None:
    st = default_structure(sel(36, 52), MOSHAF)  # sakt_marqdena defaults to waqf
    assert st.segments is not None
    assert len(st.segments) == 2
    assert_consistent(build_reference_from_structure(st, MOSHAF))


def test_yaseen_connects_only_with_a_choice() -> None:
    st = default_structure(sel(36, 1, 2), MOSHAF)
    assert st.segments == [(0, 0), (1, 2)]  # ayah end without a stop option still stops
    st.segments = [(0, 2)]
    with pytest.raises(ValueError):
        build_reference_from_structure(st, MOSHAF)
    st.special = {0: "idgham"}
    ref = build_reference_from_structure(st, MOSHAF)
    assert ref.segments[0].moshaf_overrides == {"noon_and_yaseen": "idgham"}
    assert_consistent(ref)


@pytest.mark.parametrize("segments", [[(0, 1), (3, 3)], [(1, 3)], [(0, 2)], []])
def test_invalid_segments(segments: list[tuple[int, int]]) -> None:
    st = default_structure(sel(1, 2), MOSHAF)
    st.segments = segments
    with pytest.raises(ValueError):
        build_reference_from_structure(st, MOSHAF)


def test_stop_choice_inside_a_segment_is_rejected() -> None:
    st = default_structure(sel(75, 27), MOSHAF)
    st.special = {1: "waqf"}
    with pytest.raises(ValueError):
        build_reference_from_structure(st, MOSHAF)


def test_prefixes_and_fatiha() -> None:
    ref = build_reference(sel(67, 1, prefixes=("istiaatha", "basmala")), MOSHAF)
    assert [s.kind for s in ref.segments] == ["istiaatha", "basmala", "recitation"]
    assert_consistent(ref)
    ref = build_reference(sel(1, 1, prefixes=("basmala",)), MOSHAF)
    assert [s.kind for s in ref.segments] == ["recitation"]


def test_structure_json_round_trip() -> None:
    st = default_structure(sel(75, 27, prefixes=("basmala",)), MOSHAF)
    assert Structure.from_json(st.to_json()) == st


def test_special_places_found() -> None:
    attrs = sorted(b.attr for b in special_boundaries().values())
    assert attrs == sorted(
        ["yalhath_dhalik", "irkab_maana", "sakt_iwaja", "noon_and_yaseen", "sakt_marqdena",
         "noon_and_yaseen", "sakt_maleeyah", "sakt_man_raq", "sakt_bal_ran"]
    )  # fmt: skip


@pytest.mark.parametrize("bad", [sel(0, 1), sel(1, 8), sel(2, 5, 4), sel(1, 1, prefixes=("x",))])
def test_impossible_selections(bad: TextSelection) -> None:
    with pytest.raises(ValueError):
        build_reference(bad, MOSHAF)


@pytest.mark.slow
def test_every_ayah_builds_and_is_self_consistent() -> None:
    for s in surah_list():
        for a in range(1, s.ayat + 1):
            ref = build_reference(sel(s.index, a), MOSHAF)
            assert ref.phonetic.phonemes, (s.index, a)
            assert len(ref.phonetic.mappings) == len(ref.uthmani)
