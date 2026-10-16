"""The reference: the expected reading of a structure, in the phonetic script the model writes.

Ported from tajweed_ai `muaalem_lab/quran.py` (Segment*, Reference, phonetize,
build_reference_from_structure). A stretch is phonetized as a whole, never stitched from single
words: idgham, iqlab, hamzat al-wasl, silah, the 'arid madd and the lam of Allah depend on the
neighbouring words. Each segment ends in a stop.
"""

import dataclasses
from functools import lru_cache
from typing import Any

from app.engine.text.qt import (
    MappingPos,
    MoshafAttributes,
    QuranPhoneticScriptOutput,
    quran_phonetizer,
)
from app.engine.text.quran_text import ISTIAATHA, basmala_text, get_aya
from app.engine.text.structure import (
    Structure,
    TextSelection,
    Word,
    default_structure,
    segment_overrides,
    validate_structure,
)


@dataclasses.dataclass
class SegmentWord:
    """A word inside a segment, with its place in the Quran and in Reference.uthmani."""

    sura: int
    aya: int
    word: int
    start: int  # character offsets into Reference.uthmani, end exclusive
    end: int
    ayah_last: bool


@dataclasses.dataclass
class Segment:
    """One stretch read without stopping (or an opening)."""

    kind: str  # "istiaatha" | "basmala" | "recitation"
    start: int  # character offsets into Reference.uthmani, end exclusive
    end: int
    words: list[SegmentWord]
    moshaf_overrides: dict[str, str]
    uthmani: str  # the exact text phonetized for this segment


@dataclasses.dataclass
class Reference:
    """The expected reading of a structure."""

    uthmani: str  # exactly the string that was phonetized; error positions index into it
    segments: list[Segment]
    phonetic: Any  # QuranPhoneticScriptOutput
    structure: Structure
    moshaf: Any  # MoshafAttributes

    @property
    def sura(self) -> int:
        return self.structure.sura

    @property
    def aya(self) -> int:
        return self.structure.aya_start

    @property
    def aya_end(self) -> int:
        return self.structure.aya_end

    @property
    def prefixes(self) -> tuple[str, ...]:
        return self.structure.prefixes

    def segment_at(self, pos: int) -> int:
        for i, seg in enumerate(self.segments):
            if pos < seg.end or i == len(self.segments) - 1:
                return i
        return 0

    def segment_moshaf(self, i: int) -> Any:
        return self.moshaf.model_copy(update=self.segments[i].moshaf_overrides)


def _moshaf_key(moshaf: Any) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted(moshaf.model_dump().items()))


@lru_cache(maxsize=8192)
def _phonetize_cached(text: str, sura_idx: int, moshaf_key: tuple[tuple[str, Any], ...]) -> Any:
    moshaf = MoshafAttributes(**dict(moshaf_key))
    return quran_phonetizer(text, moshaf, remove_spaces=True, sura_idx=sura_idx)


def phonetize(text: str, moshaf: Any, sura_idx: int = 0) -> Any:
    """quran_phonetizer with remove_spaces=True, cached. The end of `text` is treated as a stop."""
    return _phonetize_cached(text, sura_idx, _moshaf_key(moshaf))


def ayah_phonemes(sura: int, aya: int, moshaf: Any) -> str:
    return str(phonetize(get_aya(sura, aya).uthmani, moshaf, sura).phonemes)


@dataclasses.dataclass(frozen=True)
class _Part:
    kind: str
    words: list[Word]
    overrides: dict[str, str]
    text: str
    out: Any  # QuranPhoneticScriptOutput


def _parts(st: Structure, moshaf: Any) -> list[_Part]:
    """Each opening and each segment, phonetized on its own."""
    words = st.words()
    parts = []
    for p in st.prefixes:
        text = ISTIAATHA if p == "istiaatha" else basmala_text()
        parts.append(_Part(p, [], {}, text, phonetize(text, moshaf)))
    for a, b in st.segments or []:
        overrides = segment_overrides(st, words, a, b)
        seg_words = words[a : b + 1]
        text = " ".join(w.text for w in seg_words)
        out = phonetize(text, moshaf.model_copy(update=overrides), st.sura)
        parts.append(_Part("recitation", seg_words, overrides, text, out))
    return parts


def _segment(part: _Part, offset: int) -> Segment:
    infos, pos = [], offset
    for w in part.words:
        infos.append(SegmentWord(w.sura, w.aya, w.word, pos, pos + len(w.text), w.ayah_last))
        pos += len(w.text) + 1
    return Segment(part.kind, offset, offset + len(part.text), infos, part.overrides, part.text)


def _join(parts: list[_Part], st: Structure, moshaf: Any) -> Reference:
    """Join the parts, shifting positions past the earlier ones."""
    texts: list[str] = []
    segments: list[Segment] = []
    phonemes, sifat, mappings = "", [], []
    offset = 0
    for part in parts:
        shift = len(phonemes)
        if texts:
            # the space between two parts maps to nothing in the phonetic script
            mappings.append(MappingPos(pos=(shift, shift), deleted=True))
            offset += 1
        segments.append(_segment(part, offset))
        mappings.extend(
            dataclasses.replace(m, pos=(m.pos[0] + shift, m.pos[1] + shift))
            for m in part.out.mappings
        )
        texts.append(part.text)
        phonemes += part.out.phonemes
        sifat.extend(part.out.sifat)
        offset += len(part.text)
    phonetic = QuranPhoneticScriptOutput(phonemes=phonemes, sifat=sifat, mappings=mappings)
    return Reference(" ".join(texts), segments, phonetic, st, moshaf)


def build_reference_from_structure(st: Structure, moshaf: Any) -> Reference:
    """Each segment is phonetized on its own, so each one ends in a stop and the next one starts
    the way a reciter starts after a pause; ayat inside one segment are connected. This is
    exactly what the upstream trainer does per segment:
    quran_phonetizer(segment_uthmani, moshaf, remove_spaces=True). ValueError for an invalid
    structure."""
    validate_structure(st, st.words())
    if st.sura == 1 and st.aya_start == 1 and st.word_start == 0:
        # in Al-Fatiha the basmala is ayah 1 itself
        st = dataclasses.replace(st, prefixes=tuple(p for p in st.prefixes if p != "basmala"))
    return _join(_parts(st, moshaf), st, moshaf)


def build_reference(text: TextSelection, moshaf: Any) -> Reference:
    """Whole ayat, with a stop at the end of each ayah (and at special boundaries set to waqf)."""
    return build_reference_from_structure(default_structure(text, moshaf), moshaf)
