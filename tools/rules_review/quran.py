"""The Quran text, phonetized at the default reading settings, as the review's examples come
from it: every ayah once, with its letter clusters, each cluster's slice of the phonetic script,
its sifat group and tajweed rules. Nothing here is typed by hand.

Each ayah is phonetized on its own, so it is read connected within the ayah and stopped at its
end, the way the app's expected reading treats an ayah recited alone.
"""

from __future__ import annotations

import bisect
import dataclasses
import unicodedata
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from app.engine.text.moshaf import build_moshaf
from app.engine.text.qt import alph
from app.engine.text.quran_text import ayah_words, surah_list
from app.engine.text.readable import ar_num, describe
from app.engine.text.reference import phonetize
from app.engine.text.tajweed import tajweed_spans

CONTEXT_WORDS = 2  # words shown on each side of an example


@dataclasses.dataclass(frozen=True)
class Cluster:
    """A letter with its marks."""

    start: int
    end: int
    base: str
    marks: str
    word: int
    slice: tuple[int, int] | None  # its part of the phonetic script; None: not pronounced
    rules: tuple[Any, ...]  # quran-transcript TajweedRule objects


@dataclasses.dataclass
class Ayah:
    """One ayah, phonetized."""

    sura: int
    aya: int
    text: str
    words: tuple[str, ...]
    phonemes: str
    clusters: list[Cluster]
    sifat: list[Any]
    _starts: list[int]
    _word_starts: list[int]
    truncated: bool = False  # cut after a word, to read it at a stop

    def sifa_at(self, cluster: Cluster) -> Any:
        """The sifat group a pronounced cluster starts in."""
        if cluster.slice is None or not self.sifat:
            return None
        return self.sifat[bisect.bisect_right(self._starts, cluster.slice[0]) - 1]

    def word_span(self, first: int, last: int) -> tuple[int, int]:
        """Character span of words first..last."""
        return self._word_starts[first], self._word_starts[last] + len(self.words[last])

    def phonemes_of(self, start: int, end: int) -> str:
        """The phonetic script of the clusters inside [start, end)."""
        spans = [c.slice for c in self.clusters if start <= c.start < end and c.slice]
        return self.phonemes[min(s[0] for s in spans) : max(s[1] for s in spans)] if spans else ""

    def next_letter(self, i: int) -> Cluster | None:
        """The cluster after cluster i (spaces are not clusters)."""
        return self.clusters[i + 1] if i + 1 < len(self.clusters) else None


def _clusters(text: str, maps: list[Any]) -> list[Cluster]:
    out: list[Cluster] = []
    word = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == " ":
            word += 1
            i += 1
            continue
        j = i + 1
        while j < len(text) and unicodedata.category(text[j]) == "Mn":
            j += 1
        spans = [
            maps[k].pos
            for k in range(i, j)
            if not maps[k].deleted and maps[k].pos[1] > maps[k].pos[0]
        ]
        sl = (min(s[0] for s in spans), max(s[1] for s in spans)) if spans else None
        rules = tuple(r for k in range(i, j) for r in maps[k].tajweed_rules or [])
        out.append(Cluster(i, j, ch, text[i + 1 : j], word, sl, rules))
        i = j
    return out


def load_ayah(sura: int, aya: int, upto: int | None = None) -> Ayah:
    """The ayah phonetized; with `upto`, only its words up to that one, so the reading stops
    there."""
    words = ayah_words(sura, aya)
    truncated = upto is not None and upto < len(words) - 1
    words = words[: upto + 1] if upto is not None else words
    text = " ".join(words)
    out = phonetize(text, build_moshaf(), sura - 1)
    starts, pos = [], 0
    for g in out.sifat:
        starts.append(pos)
        pos += len(g.phonemes)
    word_starts, p = [], 0
    for w in words:
        word_starts.append(p)
        p += len(w) + 1
    return Ayah(
        sura, aya, text, words, out.phonemes, _clusters(text, out.mappings), out.sifat, starts,
        word_starts, truncated,
    )  # fmt: skip


def all_ayat() -> Iterator[Ayah]:
    """Every ayah, in order (about 30 s for the whole Quran)."""
    for s in surah_list():
        for a in range(1, s.ayat + 1):
            yield load_ayah(s.index, a)


@lru_cache(maxsize=1)
def _sura_names() -> dict[int, str]:
    return {s.index: s.name for s in surah_list()}


def ref_ar(sura: int, aya: int) -> str:
    """«البقرة ٢٥٥»."""
    return f"{_sura_names()[sura]} {ar_num(aya)}"


def example(ayah: Ayah, start: int, end: int, context: int = CONTEXT_WORDS) -> dict[str, Any]:
    """An example for the page: the marked characters [start, end) of the ayah with a few words
    around them, the tajweed colours over that piece, and what the app expects to hear for the
    marked words (with the raa's and the lam of the Name's tafkheem, which letters can't show)."""
    first = ayah.text.count(" ", 0, start)
    last = ayah.text.count(" ", 0, max(start, end - 1))
    lo, hi = max(0, first - context), min(len(ayah.words) - 1, last + context)
    a, b = ayah.word_span(lo, hi)
    wa, wb = ayah.word_span(first, last)
    spans = [
        [max(s, a) - a, min(t, b) - a, cls]
        for s, t, cls in tajweed_spans(ayah.text, _phonetic(ayah))
        if t > a and s < b
    ]
    return {
        "sura": ayah.sura,
        "aya": ayah.aya,
        "ref": ref_ar(ayah.sura, ayah.aya),
        "text": ayah.text[a:b],
        "mark": [start - a, end - a],
        "cut_before": lo > 0,
        "cut_after": hi < len(ayah.words) - 1 or ayah.truncated,
        "at_stop": last == len(ayah.words) - 1,
        "spans": spans,
        "expect": describe(ayah.phonemes_of(wa, wb)),
        "notes": _tafkheem_notes(ayah, start, end),
    }


def _tafkheem_notes(ayah: Ayah, start: int, end: int) -> list[str]:
    notes = []
    for c in ayah.clusters:
        if not start <= c.start < end or c.slice is None:
            continue
        sifa = ayah.sifa_at(c)
        heavy = sifa is not None and sifa.tafkheem_or_taqeeq == "mofakham"
        if c.base == alph.uthmani.raa:
            notes.append("الراء مفخمة" if heavy else "الراء مرققة")
        elif c.base == alph.uthmani.lam and alph.uthmani.shadda in c.marks and _is_name(ayah, c):
            notes.append("لام لفظ الجلالة مفخمة" if heavy else "لام لفظ الجلالة مرققة")
    return list(dict.fromkeys(notes))


def _is_name(ayah: Ayah, c: Cluster) -> bool:
    plain = "".join(
        ch for ch in ayah.words[c.word] if ch.isalpha() and ch != alph.uthmani.hamzat_wasl
    )
    return plain.endswith(("لله", "للهم"))


def word_example(
    sura: int, aya: int, word: int, context: int = CONTEXT_WORDS, stop: bool = False
) -> dict[str, Any]:
    """An example marking one whole word; `stop`: read with a stop on it."""
    ayah = load_ayah(sura, aya, upto=word if stop else None)
    s, e = ayah.word_span(word, word)
    return example(ayah, s, e, context)


def opening_example(sura: int, aya: int, words: int = 1) -> dict[str, Any]:
    """The first word(s) of an ayah, marked."""
    ayah = load_ayah(sura, aya)
    s, e = ayah.word_span(0, min(words, len(ayah.words)) - 1)
    return example(ayah, s, e)


def ayah_example(sura: int, aya: int) -> dict[str, Any]:
    """A whole ayah, nothing marked."""
    ayah = load_ayah(sura, aya)
    ex = example(ayah, 0, 0, context=len(ayah.words))
    ex["mark"] = None
    ex["expect"] = None
    ex["notes"] = []
    return ex


def _phonetic(ayah: Ayah) -> Any:
    return phonetize(ayah.text, build_moshaf(), ayah.sura - 1)
