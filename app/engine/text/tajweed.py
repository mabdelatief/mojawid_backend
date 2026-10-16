"""Tajweed colour classes for the Uthmani text, the way a colour-coded Mushaf marks them.

Ported from tajweed_ai `muaalem_lab/tajweed.py`. The Quran JSON is plain text, so the classes
come from the phonetizer output the recitation is checked against: each Uthmani character's slice
of the phonetic script, its madd and qalqalah rules, and the letters' sifat. Natural (2-count)
madd is left plain, as in the printed Mushaf. The colours always agree with what a recording is
checked against.
"""

import bisect
import re
import unicodedata
from typing import Any

from app.engine.text.qt import (
    AaredMaddRule,
    LazemMaddRule,
    LeenMaddRule,
    MonfaselMaddRule,
    MottaselMaddPauseRule,
    MottaselMaddRule,
    Qalqalah,
    alph,
)

# The phonetizer writes a held ghunnah as its letter repeated GHUNNAH_RUN times (one more in
# mid-word after a shadda); a single letter is a plain noon or meem.
GHUNNAH_RUN = 3
GHUNNAH_LETTERS: str = (
    alph.phonetics.noon + alph.phonetics.meem + alph.phonetics.noon_mokhfah
    + alph.phonetics.meem_mokhfah + alph.phonetics.yaa + alph.phonetics.waw
)  # fmt: skip
IDGHAM_LETTERS: str = alph.phonetics.yaa + alph.phonetics.waw
# a clear meem held in place of the hidden one still carries the ghunnah's length: lips closed or
# a slight gap are both correct (the teacher's ruling; moshaf meem_mokhfah). Not the noon: a clear
# noon where ikhfa is due is izhar, a mistake (audit 2026-10-16, C4)
GHUNNAH_HEARD_AS: dict[str, str] = {
    alph.phonetics.meem_mokhfah: alph.phonetics.meem_mokhfah + alph.phonetics.meem,
}
# a noon or tanween (the modgham and iqlab tanween forms start with one of these)
NOON_OR_TANWEEN: str = (
    alph.uthmani.noon + alph.uthmani.tanween_fath + alph.uthmani.tanween_dam
    + alph.uthmani.tanween_kasr
)  # fmt: skip
_GHUNNAH_RUNS = re.compile(f"([{GHUNNAH_LETTERS}])\\1{{{GHUNNAH_RUN - 1},}}")

# colour classes, strongest first: a letter gets the first one that applies
CLASSES = ("madd6", "wajib", "jaiz", "ghunnah", "qalqalah", "tafkheem", "silent")
_MADD_CLASS: tuple[tuple[Any, str], ...] = (
    (LazemMaddRule, "madd6"),
    ((MottaselMaddRule, MottaselMaddPauseRule), "wajib"),
    ((MonfaselMaddRule, AaredMaddRule, LeenMaddRule), "jaiz"),
)

Span = list[Any]  # [start, end, class]
Slice = tuple[int, int] | None


def run_length(text: str, chars: str) -> int:
    """How many of `text`'s first characters are in `chars`."""
    return len(text) - len(text.lstrip(chars))


def ghunnah_run(ph: str, uthmani: str) -> int:
    """Length of the held ghunnah that `ph` starts with, 0 if it doesn't start with one.
    `uthmani` is the text it comes from: a yaa or waw run counts only when it comes from a noon
    or tanween, since a leen madd at a stop is written the same way."""
    if not ph or ph[0] not in GHUNNAH_LETTERS:
        return 0
    n = run_length(ph, ph[0])
    if n < GHUNNAH_RUN or (ph[0] in IDGHAM_LETTERS and not set(uthmani) & set(NOON_OR_TANWEEN)):
        return 0
    return n


def _clusters(text: str) -> list[tuple[int, int]]:
    """Each letter with the marks, tatweel and small letters that sit on it. A pause mark
    standing alone between spaces is its own cluster with no letter."""
    out: list[tuple[int, int]] = []
    for i, ch in enumerate(text):
        if ch == " ":
            continue
        if unicodedata.category(ch) in ("Mn", "Me", "Lm") and out and out[-1][1] == i:
            out[-1] = (out[-1][0], i + 1)
        else:
            out.append((i, i + 1))
    return out


def _slices(clusters: list[tuple[int, int]], maps: Any) -> list[Slice]:
    """Each cluster's slice of the phonetic script (None: it maps to nothing)."""
    slices: list[Slice] = []
    for s, t in clusters:
        pos = [maps[k].pos for k in range(s, t) if maps[k].pos[1] > maps[k].pos[0]]
        slices.append((min(p[0] for p in pos), max(p[1] for p in pos)) if pos else None)
    return slices


def _ghunnah_clusters(
    text: str, ph: str, clusters: list[tuple[int, int]], slices: list[Slice]
) -> set[int]:
    owner: list[int | None] = [None] * len(ph)  # phonetic index -> the cluster it comes from
    for c, sl in enumerate(slices):
        for p in range(*sl) if sl else ():
            owner[p] = c
    ghunnah: set[int] = set()
    for m in _GHUNNAH_RUNS.finditer(ph):
        a, b = m.span()
        hit = sorted({o for o in owner[a:b] if o is not None})
        if ghunnah_run(ph[a:b], "".join(text[clusters[c][0] : clusters[c][1]] for c in hit)):
            ghunnah.update(hit)
    return ghunnah


class _Classifier:
    """Picks the class of one cluster."""

    def __init__(self, text: str, phonetic: Any, ghunnah: set[int]) -> None:
        self.text, self.maps, self.ghunnah = text, phonetic.mappings, ghunnah
        self.groups = phonetic.sifat
        self.starts, pos = [], 0
        for g in self.groups:
            self.starts.append(pos)
            pos += len(g.phonemes)

    def classify(self, c: int, cluster: tuple[int, int], sl: Slice) -> str | None:
        s, t = cluster
        rules = [r for k in range(s, t) for r in self.maps[k].tajweed_rules or []]
        for kinds, name in _MADD_CLASS:
            if any(isinstance(r, kinds) for r in rules):
                return name
        if c in self.ghunnah:
            return "ghunnah"
        if any(isinstance(r, Qalqalah) for r in rules):
            return "qalqalah"
        if self.text[s] == alph.uthmani.raa and sl and self.groups:
            g = self.groups[bisect.bisect_right(self.starts, sl[0]) - 1]
            return "tafkheem" if g.tafkheem_or_taqeeq == "mofakham" else None
        if sl is None and unicodedata.category(self.text[s]) == "Lo":
            return "silent"
        return None


def tajweed_spans(text: str, phonetic: Any) -> list[Span]:
    """[start, end, class] over `text` (a reference's Uthmani text, or any text passed to the
    phonetizer, with `phonetic` its output), sorted and not overlapping; uncoloured text has no
    span."""
    ph = phonetic.phonemes
    clusters = _clusters(text)
    slices = _slices(clusters, phonetic.mappings)
    classifier = _Classifier(text, phonetic, _ghunnah_clusters(text, ph, clusters, slices))
    spans: list[Span] = []
    for c, (cluster, sl) in enumerate(zip(clusters, slices, strict=True)):
        cls = classifier.classify(c, cluster, sl)
        if cls is None:
            continue
        s, t = cluster
        if spans and spans[-1][1] == s and spans[-1][2] == cls:
            spans[-1][1] = t
        else:
            spans.append([s, t, cls])
    return spans


def classes_present(spans: list[Span]) -> list[str]:
    """The classes that occur, in CLASSES order (the app's legend dims the others)."""
    found = {span[2] for span in spans}
    return [c for c in CLASSES if c in found]
