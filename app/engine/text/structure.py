"""What was recited and where the reciter stopped: the selected words and their segments.

Ported from tajweed_ai `muaalem_lab/quran.py` (Word, select_words, Structure, default_structure,
validate_structure, prefixes) and `collect_api._structure_from`.
"""

import dataclasses
from collections.abc import Iterable, Mapping
from typing import Any

from app.engine.text.boundaries import STOP_OPTION, special_boundaries
from app.engine.text.quran_text import MAX_AYAT_PER_REQUEST, ayah_words, get_aya

PREFIX_ORDER = ("istiaatha", "basmala")  # the order a reciter says them in


@dataclasses.dataclass(frozen=True)
class Word:
    """One selected word."""

    sura: int
    aya: int
    word: int  # index within the ayah's Uthmani words
    text: str
    ayah_last: bool  # the last word of its ayah


def _word_bounds(
    place: tuple[int, int, int], first: tuple[int, int], last: tuple[int, int | None]
) -> range:
    """The word indexes taken from ayah `place` = (sura, aya, word count)."""
    sura, a, n = place
    lo = first[1] if a == first[0] else 0
    hi = (n - 1 if last[1] is None else last[1]) if a == last[0] else n - 1
    if not (0 <= lo < n) or not (0 <= hi < n):
        raise ValueError(f"Ayah {sura}:{a} has {n} words")
    return range(lo, hi + 1)


def select_words(
    sura: int,
    aya_start: int,
    aya_end: int | None = None,
    word_start: int = 0,
    word_end: int | None = None,
) -> list[Word]:
    """Words aya_start:word_start .. aya_end:word_end (inclusive), in mushaf order."""
    aya_end = aya_start if aya_end is None else aya_end
    get_aya(sura, aya_start)
    get_aya(sura, aya_end)
    if aya_end < aya_start:
        raise ValueError(f"Ayah range {aya_start}-{aya_end} runs backwards")
    if aya_end - aya_start + 1 > MAX_AYAT_PER_REQUEST:
        raise ValueError(f"At most {MAX_AYAT_PER_REQUEST} ayat per check")
    out: list[Word] = []
    for a in range(aya_start, aya_end + 1):
        ws = ayah_words(sura, a)
        for w in _word_bounds((sura, a, len(ws)), (aya_start, word_start), (aya_end, word_end)):
            out.append(Word(sura, a, w, ws[w], w == len(ws) - 1))
    if not out:
        raise ValueError("The word range is empty")
    return out


def normalize_prefixes(prefixes: Iterable[str]) -> tuple[str, ...]:
    """The openings, validated and in recitation order."""
    wanted = {p.strip() for p in prefixes if p and p.strip()}
    unknown = wanted - set(PREFIX_ORDER)
    if unknown:
        raise ValueError(f"Unknown opening: {', '.join(sorted(unknown))}")
    return tuple(p for p in PREFIX_ORDER if p in wanted)


@dataclasses.dataclass
class Structure:
    """What was recited and where the reciter stopped.

    `segments` are inclusive ranges of word indices into the selected words, in the order they
    were recited. A new segment means the reciter stopped; it may start at an earlier word
    (going back to repeat) but never skips one (a skipped word is a mistake, marked separately).
    `special` holds the choice at each special boundary inside a segment (e.g. sakt at
    "مَنْ رَاقٍۢ").
    """

    sura: int
    aya_start: int
    aya_end: int
    word_start: int = 0
    word_end: int | None = None
    prefixes: tuple[str, ...] = ()
    segments: list[tuple[int, int]] | None = None
    special: dict[int, str] = dataclasses.field(default_factory=dict)

    def words(self) -> list[Word]:
        return select_words(self.sura, self.aya_start, self.aya_end, self.word_start, self.word_end)

    def to_json(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["prefixes"] = list(self.prefixes)
        d["segments"] = [list(x) for x in (self.segments or [])]
        d["special"] = {str(k): v for k, v in self.special.items()}
        return d

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> "Structure":
        return cls(
            sura=int(d["sura"]),
            aya_start=int(d["aya_start"]),
            aya_end=int(d["aya_end"]),
            word_start=int(d.get("word_start") or 0),
            word_end=None if d.get("word_end") is None else int(d["word_end"]),
            prefixes=normalize_prefixes(d.get("prefixes") or ()),
            segments=[(int(a), int(b)) for a, b in d["segments"]] if d.get("segments") else None,
            special={int(k): str(v) for k, v in (d.get("special") or {}).items()},
        )


@dataclasses.dataclass(frozen=True)
class TextSelection:
    """The text a reciter chose: ayat aya_start..aya_end of a surah (optionally from or to a
    word), with openings."""

    sura: int
    aya_start: int
    aya_end: int | None = None
    word_start: int = 0
    word_end: int | None = None
    prefixes: tuple[str, ...] = ()


def default_structure(text: TextSelection, moshaf: Any) -> Structure:
    """A stop at the end of every ayah, and at special boundaries whose setting is waqf."""
    aya_end = text.aya_start if text.aya_end is None else text.aya_end
    st = Structure(
        text.sura, text.aya_start, aya_end, text.word_start, text.word_end,
        normalize_prefixes(text.prefixes),
    )  # fmt: skip
    words = st.words()
    specials = special_boundaries()
    segments, start = [], 0
    for g, w in enumerate(words):
        sb = specials.get((w.sura, w.aya, w.word))
        stop = w.ayah_last
        if sb is not None and g < len(words) - 1:
            choice = getattr(moshaf, sb.attr)
            if STOP_OPTION in sb.options:
                stop = choice == STOP_OPTION
            # a field without a stop option (يس / ن) still stops at an ayah end by default
            if not stop:
                st.special[g] = choice
        if stop or g == len(words) - 1:
            segments.append((start, g))
            start = g + 1
    st.segments = segments
    return st


def segment_overrides(st: Structure, words: list[Word], a: int, b: int) -> dict[str, str]:
    """The reading-setting overrides for segment a..b: the choice at each special boundary
    inside it. ValueError if a choice is missing or isn't a way to connect."""
    overrides = {}
    specials = special_boundaries()
    for g in range(a, b):  # boundaries inside the segment
        w = words[g]
        sb = specials.get((w.sura, w.aya, w.word))
        if sb is None:
            continue
        choice = st.special.get(g)
        if choice is None:
            raise ValueError(f"No choice given for the special boundary after word {g} ({w.text})")
        if choice not in sb.options or choice == STOP_OPTION:
            raise ValueError(f"{choice!r} is not a way to connect at {w.text} ({sb.attr})")
        overrides[sb.attr] = choice
    return overrides


def validate_structure(st: Structure, words: list[Word]) -> None:
    """The segments start at the first word, end at the last, and never skip one."""
    n = len(words)
    segs = st.segments or []
    if not segs:
        raise ValueError("No segments")
    if segs[0][0] != 0:
        raise ValueError("The recitation must start at the first selected word")
    if segs[-1][1] != n - 1:
        raise ValueError("The recitation must end at the last selected word")
    reached = -1
    for a, b in segs:
        if not (0 <= a <= b < n):
            raise ValueError(f"Segment {a}-{b} is outside the {n} selected words")
        if a > reached + 1:
            raise ValueError(f"Segment {a}-{b} skips words; mark skipped words as mistakes instead")
        reached = max(reached, b)
