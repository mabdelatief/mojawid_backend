"""The Mushaf's waqf signs on our words (app/engine/text/waqf.py, made by
tools/import_waqf_signs.py from Tanzil's full edition of our text)."""

from __future__ import annotations

import collections
import unicodedata

from app.engine.text.moshaf import moshaf_from_dict
from app.engine.text.quran_text import ayah_words, surah_list
from app.engine.text.reference import build_reference
from app.engine.text.structure import TextSelection
from app.engine.text.waqf import _signs, waqf_signs

MUANAQA, QILA, SAKT = "ۛ", "ۗ", "ۜ"


def test_known_places() -> None:
    assert ayah_words(2, 2)[3:5] == ("رَيْبَ", "فِيهِ")
    assert waqf_signs(2, 2, 3) == MUANAQA and waqf_signs(2, 2, 4) == MUANAQA
    assert unicodedata.normalize("NFC", ayah_words(36, 52)[5]) == unicodedata.normalize(
        "NFC", "مَّرْقَدِنَا"
    )
    assert waqf_signs(36, 52, 5) == SAKT + QILA  # two signs, in Mushaf order
    assert waqf_signs(18, 1, len(ayah_words(18, 1)) - 1) == SAKT  # «عِوَجَا» ends the ayah
    assert all(
        waqf_signs(1, a, w) is None for a in range(1, 8) for w in range(len(ayah_words(1, a)))
    )


def test_totals_per_sign() -> None:
    totals = collections.Counter(c for v in _signs().values() for c in v)
    assert len(_signs()) == 4363
    assert totals == {
        "ۖ": 1682, "ۗ": 603, "ۘ": 22, "ۙ": 68,
        "ۚ": 1972, "ۛ": 12, "ۜ": 5,
    }  # fmt: skip


def test_every_entry_is_a_real_word_with_only_signs() -> None:
    ayat = {s.index: s.ayat for s in surah_list()}
    for key, value in _signs().items():
        s, a, w = (int(x) for x in key.split(":"))
        assert 1 <= a <= ayat[s] and 0 <= w < len(ayah_words(s, a)), key
        assert value and all("ۖ" <= c <= "ۜ" for c in value), key


def test_the_reference_words_carry_them() -> None:
    m = moshaf_from_dict(None)
    words = build_reference(TextSelection(2, 2, 2), m).segments[0].words
    assert [w.word for w in words if w.waqf] == [3, 4]
    assert build_reference(TextSelection(112, 1, 4), m).uthmani.count(MUANAQA) == 0
