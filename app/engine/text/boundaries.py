"""Special boundaries: gaps between two words where the reciter stops, connects, or (for some)
makes a sakt, and the choice changes the phonetic script.

Ported from tajweed_ai `muaalem_lab/quran.py` (special_boundaries). The lab's asserts are
explicit checks here, so they hold under `python -O` too.
"""

import dataclasses
from functools import lru_cache
from typing import Any

from app.engine.text.moshaf import allowed_choices
from app.engine.text.qt import alph
from app.engine.text.quran_text import ayah_words, surah_list

# MoshafAttributes fields whose special pattern spans the gap between two words. "waqf" means a
# stop, so the text is split there.
BOUNDARY_ATTRS = (
    "sakt_iwaja", "sakt_marqdena", "sakt_man_raq", "sakt_bal_ran", "sakt_maleeyah",
    "yalhath_dhalik", "irkab_maana", "noon_and_yaseen",
)  # fmt: skip
STOP_OPTION = "waqf"

Place = tuple[int, int, int]  # (sura, aya, word index in the ayah)


@dataclasses.dataclass(frozen=True)
class SpecialBoundary:
    """The special boundary right after a word."""

    attr: str  # the MoshafAttributes field
    options: tuple[str, ...]  # its allowed values; "waqf" (if present) is a stop


def _noon_and_yaseen() -> dict[Place, SpecialBoundary]:
    # noon_and_yaseen's patterns match the spelled-out letters (يَا سِيٓنْ), not the Uthmani
    # text, so its two places are listed directly and checked.
    options = tuple(str(c) for c in allowed_choices("noon_and_yaseen"))
    found = {}
    for sura, aya, word, head in ((36, 1, 0, "يس"), (68, 1, 0, "ن")):
        if not ayah_words(sura, aya)[word].startswith(head):
            raise RuntimeError(f"noon_and_yaseen place {sura}:{aya} changed in the Quran text")
        found[(sura, aya, word)] = SpecialBoundary("noon_and_yaseen", options)
    return found


def _pattern_cases() -> list[Any]:
    cases = [
        c
        for c in alph.uthmani.special_patterns
        if c.attr_name in BOUNDARY_ATTRS and c.attr_name != "noon_and_yaseen"
    ]
    for c in cases:
        if c.pattern.count(" ") != 1:
            raise RuntimeError(f"special pattern {c.pattern!r} doesn't span exactly one gap")
    return cases


def _find_in_ayah(sura: int, aya: int, last_aya: int, case: Any) -> Place | None:
    """Where `case`'s pattern sits in this ayah (or across its end into the next one)."""
    words = ayah_words(sura, aya)
    text = " ".join(words)
    idx = text.find(case.pattern)
    if idx >= 0:
        return (sura, aya, text.count(" ", 0, idx))
    if aya < last_aya:
        # the pattern may span the end of this ayah and the start of the next
        idx = (text + " " + " ".join(ayah_words(sura, aya + 1))).find(case.pattern)
        if 0 <= idx < len(text) and text.count(" ", 0, idx) == len(words) - 1:
            return (sura, aya, len(words) - 1)
    return None


@lru_cache(maxsize=1)
def special_boundaries() -> dict[Place, SpecialBoundary]:
    """(sura, aya, word) -> the special boundary right after that word. Scans the whole Quran
    once (cached; the API warms it at startup)."""
    found = _noon_and_yaseen()
    cases = [(c, tuple(str(o) for o in allowed_choices(c.attr_name))) for c in _pattern_cases()]
    for s in surah_list():
        for a in range(1, s.ayat + 1):
            for case, options in cases:
                place = _find_in_ayah(s.index, a, s.ayat, case)
                if place is not None:
                    found[place] = SpecialBoundary(case.attr_name, options)
    return found
