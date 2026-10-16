"""The rules table for Hafs via al-Shatibiyya: the teachers' rulings reach the reading settings
and the reference. Ported from tajweed_ai tests/test_rules.py (the both-valid letter checks need
the analysis side and move with it, phase 4)."""

from __future__ import annotations

import re

import pytest

from app.engine.text import moshaf as M
from app.engine.text.quran_text import ayah_words
from app.engine.text.reference import build_reference_from_structure
from app.engine.text.rules import DEFAULT, RAA, LetterPlace
from app.engine.text.structure import TextSelection, default_structure


def options() -> dict[str, M.ReadingOption]:
    return {o.name: o for o in M.moshaf_all_options()}


def test_madd_pairs() -> None:
    for a, b in [(4, 4), (5, 5), (4, 5)]:
        M.moshaf_from_dict({"madd_monfasel_len": a, "madd_mottasel_len": b})
    for a, b in [(5, 4), (2, 4), (3, 4), (4, 6)]:
        with pytest.raises(ValueError):
            M.moshaf_from_dict({"madd_monfasel_len": a, "madd_mottasel_len": b})


def test_muttasil_at_a_stop_may_be_4_to_6() -> None:
    for n in (4, 5, 6):
        assert M.moshaf_from_dict({"madd_mottasel_waqf": n}).madd_mottasel_waqf == n


def test_no_idraj_offered_at_the_four_sakt_places() -> None:
    opts = options()
    for f in ("sakt_iwaja", "sakt_marqdena", "sakt_man_raq", "sakt_bal_ran"):
        assert opts[f].choices == ["sakt", "waqf"]
    with pytest.raises(ValueError):
        M.moshaf_from_dict({"sakt_man_raq": "idraj"})


def test_fixed_settings_cannot_be_changed_and_are_not_offered() -> None:
    m = M.moshaf_from_dict({"alif_salasila": "hadhf", "yaa_ataan": "hadhf"})
    assert (m.alif_salasila, m.yaa_ataan) == ("ithbat", "ithbat")
    assert not set(options()) & set(DEFAULT.fixed)


def _stop_after(sura: int, aya: int, word_prefix: str) -> str:
    words = ayah_words(sura, aya)
    k = next(i for i, w in enumerate(words) if w.startswith(word_prefix))
    m = M.build_moshaf()
    st = default_structure(TextSelection(sura, aya, word_end=k), m)
    return str(build_reference_from_structure(st, m).phonetic.phonemes)


def test_stop_on_salasila_keeps_the_alif() -> None:
    assert _stop_after(76, 4, "سَلَـٰسِلَا").endswith("سِلَاا")


def test_stop_on_ataan_keeps_the_yaa() -> None:
    assert _stop_after(27, 36, "ءَاتَىٰنِ").endswith("نِۦۦ")


def bare(w: str) -> str:
    """The letters of a word without harakat and marks."""
    return re.sub(
        "[ً-ٰٟۖ-ۭٱ]",
        lambda m: "ا" if m.group() == "ٱ" else "",
        w,
    )


def word_index(sura: int, aya: int, letters: str) -> int:
    return next(i for i, w in enumerate(ayah_words(sura, aya)) if bare(w).endswith(letters))


def test_misr_and_qitr_defaults_and_choices() -> None:
    m = M.build_moshaf()
    assert (m.raa_misr, m.raa_alqitr) == ("tafkheem", "tarqeeq")
    opts = options()
    for f in ("raa_misr", "raa_alqitr"):
        assert opts[f].choices == ["tafkheem", "tarqeeq"]
    assert opts["raa_alqitr"].default == "tarqeeq"


def test_stored_wasl_raa_setting_still_prepares() -> None:
    # recordings saved before 2026-10-14 hold the phonetizer's old default "wasl"
    stored = M.build_moshaf().model_dump() | {"raa_misr": "wasl", "raa_alqitr": "wasl"}
    m = M.moshaf_from_dict(stored)
    assert (m.raa_misr, m.raa_alqitr) == ("tafkheem", "tarqeeq")
    exact = M.moshaf_from_dict(stored, stored=True)
    assert (exact.raa_misr, exact.raa_alqitr) == ("wasl", "wasl")


@pytest.mark.parametrize(
    ("sura", "aya", "letters", "value"),
    [(34, 12, "القطر", "moraqaq"), (12, 21, "مصر", "mofakham"), (10, 87, "مصر", "mofakham")],
)
def test_misr_and_qitr_at_a_stop_show_the_preferred_way(
    sura: int, aya: int, letters: str, value: str
) -> None:
    k = word_index(sura, aya, letters)
    m = M.build_moshaf()
    ref = build_reference_from_structure(
        default_structure(TextSelection(sura, aya, word_end=k), m), m
    )
    assert ref.phonetic.sifat[-1].tafkheem_or_taqeeq == value


def test_both_valid_entries_name_the_right_words() -> None:
    for b in DEFAULT.both_valid:
        if b.letter == RAA and b.word is not None:
            word = bare(ayah_words(b.sura, b.aya)[b.word])
            assert word.endswith(("مصر", "القطر", "نذر", "فرق")), (b, word)


def test_both_valid_lookup_respects_stop_and_letter() -> None:
    level = "tafkheem_or_taqeeq"
    assert DEFAULT.both_valid_at(level, LetterPlace(12, 21, 4, True, RAA)) is not None
    assert DEFAULT.both_valid_at(level, LetterPlace(12, 21, 4, False, RAA)) is None
    assert DEFAULT.both_valid_at(level, LetterPlace(12, 21, 4, True, "م")) is None
    assert DEFAULT.both_valid_at(level, LetterPlace(26, 63, 10, False, RAA)) is not None  # فِرْقٍ


def test_maleeyah_and_anfal_tawba_choices() -> None:
    opts = options()
    assert opts["sakt_maleeyah"].choices == ["sakt", "waqf", "idgham"]
    assert opts["between_anfal_and_tawba"].choices == ["waqf", "sakt", "wasl"]
    assert DEFAULT.connected_alternatives["sakt_maleeyah"] == ("sakt", "idgham")


def test_raum_practice_is_off_by_default() -> None:
    assert DEFAULT.practices == {"raum": False}
