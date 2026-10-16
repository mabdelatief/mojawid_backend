"""The Quran text: Tanzil's Uthmani, as bundled by quran-transcript, passed through unmodified.

Ported from tajweed_ai `muaalem_lab/quran.py` (text lookups).
"""

import dataclasses
from functools import lru_cache
from typing import Any

from app.engine.text.qt import Aya, alph

ISTIAATHA: str = alph.istiaatha.uthmani
MAX_AYAT_PER_REQUEST = 50  # the engine's own ceiling; the API applies a lower one in manual mode


@dataclasses.dataclass(frozen=True)
class Surah:
    """A surah: its number, Arabic name and ayah count."""

    index: int
    name: str
    ayat: int


@lru_cache(maxsize=1)
def _quran_dict() -> dict[str, Any]:
    # One Aya object loads the whole Quran JSON; reuse its dict for every lookup.
    loaded: dict[str, Any] = Aya(1, 1).quran_dict
    return loaded


@lru_cache(maxsize=1)
def surah_list() -> tuple[Surah, ...]:
    """All 114 surahs."""
    a = Aya(1, 1, quran_dict=_quran_dict())
    out = []
    for s in range(1, 115):
        a.set(s, 1)
        f = a.get()
        out.append(Surah(index=s, name=str(f.sura_name), ayat=int(f.num_ayat_in_sura)))
    return tuple(out)


def get_aya(sura: int, aya: int) -> Any:
    """quran-transcript's AyaFormat for one ayah. ValueError for a place that doesn't exist."""
    if not 1 <= sura <= 114:
        raise ValueError(f"Surah must be 1-114, got {sura}")
    count = surah_list()[sura - 1].ayat
    if not 1 <= aya <= count:
        raise ValueError(f"Surah {sura} has {count} ayat, got {aya}")
    return Aya(sura, aya, quran_dict=_quran_dict()).get()


@lru_cache(maxsize=1)
def basmala_text() -> str:
    """The basmala, as written before a surah."""
    return str(get_aya(2, 1).bismillah_uthmani)


@lru_cache(maxsize=8192)
def ayah_words(sura: int, aya: int) -> tuple[str, ...]:
    """The ayah's Uthmani words: the text split on spaces. Word indexes everywhere (and the
    reciters' word timings) count these."""
    return tuple(str(get_aya(sura, aya).uthmani).split(" "))
