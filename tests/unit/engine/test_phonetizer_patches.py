"""The phonetizer (vendor/quran-transcript, the patched 0.6.4) against the published rules of Hafs
via al-Shatibiyya: the two patches, and the stop/start cases checked in the 2026-10-13 audit. All
text comes from the Quran JSON (never hand-typed). Ported from tajweed_ai
tests/test_phonetizer_patches.py."""

from __future__ import annotations

import unicodedata
from typing import Any

import pytest

from app.engine.text.moshaf import build_moshaf
from app.engine.text.qt import chunck_phonemes
from app.engine.text.quran_text import ayah_words
from app.engine.text.reference import phonetize

M = build_moshaf()


def _bare(text: str) -> str:
    """The letters only (no marks), to find a word without depending on how it was typed."""
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn" and c != "ـ"
    )


def _index(sura: int, aya: int, prefix: str) -> int:
    words = ayah_words(sura, aya)
    hits = [i for i, w in enumerate(words) if _bare(w) == _bare(prefix)]
    assert hits, (sura, aya, prefix, words)
    return hits[0]


def stop_after(sura: int, aya: int, prefix: str, **reading: str) -> Any:
    """The ayah read up to and including the word matching `prefix`, then a stop."""
    words = ayah_words(sura, aya)
    k = _index(sura, aya, prefix)
    return phonetize(" ".join(words[: k + 1]), M.model_copy(update=reading), sura)


def start_at(sura: int, aya: int, prefix: str) -> str:
    """The ayah read from the word matching `prefix` (a start after a stop)."""
    words = ayah_words(sura, aya)
    return str(phonetize(" ".join(words[_index(sura, aya, prefix) :]), M, sura).phonemes)


def whole(sura: int, aya: int) -> Any:
    return phonetize(" ".join(ayah_words(sura, aya)), M, sura)


def joined(sura: int, aya: int, n_next: int = 1) -> Any:
    """The ayah joined to the start of the next one."""
    text = " ".join(ayah_words(sura, aya) + ayah_words(sura, aya + 1)[:n_next])
    return phonetize(text, M, sura)


def last_raa(out: Any) -> str:
    k = max(i for i, g in enumerate(chunck_phonemes(out.phonemes)) if g[0] == "ر")
    return str(out.sifat[k].tafkheem_or_taqeeq)


# ---------- patch 1: a stop on a noon marked for iqlab is a clear noon ----------


@pytest.mark.parametrize(
    ("sura", "aya", "prefix", "clear"), [(2, 87, "مِنۢ", "مِن"), (36, 52, "مَنۢ", "مَن")]
)
def test_stop_on_iqlab_noon_is_clear(sura: int, aya: int, prefix: str, clear: str) -> None:
    assert stop_after(sura, aya, prefix).phonemes.endswith(clear)


def test_iqlab_connected_unchanged() -> None:
    words = ayah_words(2, 87)
    k = _index(2, 87, "مِنۢ")
    assert "۾۾۾ب" in phonetize(" ".join(words[: k + 2]), M, 2).phonemes


# ---------- patch 2: the raa options of ٱلْقِطْرِ and مِّصْرَ work mid-text ----------


@pytest.mark.parametrize(
    ("sura", "aya", "prefix", "attr"),
    [(34, 12, "ٱلْقِطْرِ", "raa_alqitr"), (12, 21, "مِّصْرَ", "raa_misr"), (10, 87, "بِمِصْرَ", "raa_misr")],
)
def test_raa_option_at_a_stop(sura: int, aya: int, prefix: str, attr: str) -> None:
    assert last_raa(stop_after(sura, aya, prefix, **{attr: "tarqeeq"})) == "moraqaq"
    assert last_raa(stop_after(sura, aya, prefix, **{attr: "tafkheem"})) == "mofakham"


# ---------- stops, starts and ghunnah: checked against the published rules ----------


def test_raa_at_a_stop() -> None:
    assert last_raa(whole(97, 1)) == "mofakham"  # ٱلْقَدْرِ
    assert last_raa(whole(89, 1)) == "mofakham"  # وَٱلْفَجْرِ
    assert last_raa(whole(89, 5)) == "moraqaq"  # حِجْرٍ


def test_raa_connected_with_kasra_is_tarqeeq() -> None:
    out = joined(97, 1)
    k = next(i for i, g in enumerate(chunck_phonemes(out.phonemes)) if g == "رِ")
    assert out.sifat[k].tafkheem_or_taqeeq == "moraqaq"


def test_tanween_fath_at_a_stop_is_an_alif() -> None:
    assert stop_after(13, 2, "مُّسَمًّۭى").phonemes.endswith("مَاا")
    assert stop_after(4, 17, "عَلِيمًا").phonemes.endswith("مَاا")


def test_qalqalah_at_a_stop() -> None:
    assert whole(112, 1).phonemes.endswith("ڇ")


@pytest.mark.parametrize(
    ("sura", "aya", "prefix", "start"),
    [
        (13, 2, "ٱسْتَوَىٰ", "ءِس"),  # verb, third letter not dammah: kasra
        (6, 11, "ٱنظُرُوا۟", "ءُںںں"),  # verb with an original dammah on the third letter
        (38, 6, "ٱمْشُوا۟", "ءِم"),  # the dammah is not original: kasra
        (55, 1, "ٱلرَّحْمَـٰنُ", "ءَ"),  # ال: fatha
    ],
)
def test_hamzat_wasl_when_starting(sura: int, aya: int, prefix: str, start: str) -> None:
    assert start_at(sura, aya, prefix).startswith(start)


def test_lam_of_allah() -> None:
    out = whole(1, 1)  # بِسْمِ ٱللَّهِ: after a kasra
    k = next(i for i, g in enumerate(chunck_phonemes(out.phonemes)) if g.startswith("لل"))
    assert out.sifat[k].tafkheem_or_taqeeq == "moraqaq"
    out = whole(112, 2)  # starting with ٱللَّهُ
    k = next(i for i, g in enumerate(chunck_phonemes(out.phonemes)) if g.startswith("لل"))
    assert out.sifat[k].tafkheem_or_taqeeq == "mofakham"


@pytest.mark.parametrize("n", [4, 5, 6])
def test_muttasil_at_a_stop(n: int) -> None:
    out = phonetize(
        " ".join(ayah_words(2, 19)[: _index(2, 19, "ٱلسَّمَآءِ") + 1]),
        M.model_copy(update={"madd_mottasel_waqf": n}),
        2,
    )
    assert "ا" * n + "ء" in out.phonemes
    assert "ا" * (n + 1) + "ء" not in out.phonemes


def test_stop_drops_the_last_haraka_and_the_silah() -> None:
    assert stop_after(2, 255, "لَّهُۥ").phonemes.endswith("لَه")
