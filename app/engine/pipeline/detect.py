"""Work out which ayah (or ayat) a recitation is, from the phonemes the model heard.

Ported from tajweed_ai `muaalem_lab/detect.py`. quran-transcript's PhoneticSearch finds where a
phonetic string occurs in the whole Quran, tolerating mistakes; searching a whole long recitation
at a high tolerance is very slow (minutes for 2:282), so the search only anchors the *start* on
the first part of the recording, and the end is found by scoring whole-ayah ranges against
everything heard. The lab changed candidates in place (`c.aya = 1`); here they're frozen and
replaced, same results.
"""

import dataclasses
import threading
import time
from functools import lru_cache
from typing import Any

import Levenshtein

from app.engine.text.qt import NoPhonemesSearchResult, PhoneticSearch
from app.engine.text.quran_text import ISTIAATHA, MAX_AYAT_PER_REQUEST, basmala_text, surah_list
from app.engine.text.reference import ayah_phonemes, phonetize

WINDOWS = (120, 240)  # phoneme characters searched to anchor the start
TOLERANCES = (0.1, 0.2, 0.3)  # share of the window allowed to differ
MAX_STARTS = 40  # distinct start ayat scored before asking for a longer window
MAX_CANDIDATES = 12
MIN_WINDOW = 30  # the shortest opening searched alone
MAX_RANGES = 8  # ayah ranges kept for a caller that scores them with the stops in view

Start = tuple[int, int]


@dataclasses.dataclass(frozen=True)
class Candidate:
    """A range of ayat and how far what was heard is from it."""

    sura: int
    aya: int
    aya_end: int
    distance: int


@dataclasses.dataclass(frozen=True)
class Detection:
    candidates: list[Candidate]  # best first
    clear: bool  # True when the runner-up is clearly worse
    prefixes: tuple[str, ...]  # openings heard before the ayah: istiaatha, basmala
    tolerance: float
    ms: int
    # every range scored (several ends per start), closest first: a reciter who went back to
    # repeat words is further from the right range than its letters suggest, so a caller that
    # can see the stops (choose_range) chooses among these
    ranges: list[Candidate] = dataclasses.field(default_factory=list)


_search_lock = threading.Lock()


@lru_cache(maxsize=1)
def _searcher() -> Any:
    return PhoneticSearch()


def warm_up() -> None:
    """Load the phonetic search index (once, a few seconds)."""
    _searcher()


def _strip_prefix(heard: str, prefix: str) -> str | None:
    """If `heard` starts with something close to `prefix`, return the rest."""
    slack = max(3, len(prefix) // 5)
    best_cut, best_d = None, None
    for cut in range(max(1, len(prefix) - slack), min(len(heard), len(prefix) + slack) + 1):
        d = Levenshtein.distance(heard[:cut], prefix)
        if best_d is None or d < best_d:
            best_cut, best_d = cut, d
    if best_d is not None and best_d <= max(3, len(prefix) // 5):
        return heard[best_cut:]
    return None


def _openings(heard: str, moshaf: Any) -> tuple[str, tuple[str, ...]]:
    found = []
    rest = heard
    for kind, text in (("istiaatha", ISTIAATHA), ("basmala", basmala_text())):
        after = _strip_prefix(rest, phonetize(text, moshaf).phonemes)
        # Something has to be left over: a basmala on its own is ayah 1:1.
        if after is not None and len(after) >= 4:
            found.append(kind)
            rest = after
    return rest, tuple(found)


def _search(query: str, tol: float) -> set[Start] | None:
    try:
        with _search_lock:
            hits = _searcher().search(query, error_ratio=tol)
    except NoPhonemesSearchResult:
        return None
    return {(h.start.sura_idx, h.start.aya_idx) for h in hits}


def _search_windows(core: str) -> tuple[set[Start], float] | None:
    """The start search over the windows; None when nothing was found."""
    too_many: tuple[set[Start], float] | None = None
    for window in WINDOWS:
        query = core[:window]
        for tol in TOLERANCES:
            if tol >= 0.3 and len(query) > 160:
                break  # too slow on long queries; see module docstring
            starts = _search(query, tol)
            if starts is None:
                continue
            if len(starts) <= MAX_STARTS or len(core) <= window:
                return starts, tol
            too_many = (starts, tol)
            break  # the opening words occur in too many places: try a longer window
        if len(core) <= window:
            break
    # Still many places after the longest window: score them all; it is only slower.
    return too_many


def _search_starts(core: str) -> tuple[set[Start], float]:
    """Distinct (sura, aya) where the start of `core` occurs, and the tolerance used."""
    found = _search_windows(core)
    if found:
        return found
    # Nowhere near the whole opening: a reciter who went back and said the first words again
    # makes it unlike any stretch of the Quran. Search its first half.
    half = core[: max(MIN_WINDOW, min(len(core), WINDOWS[0]) // 2)]
    if len(half) < min(len(core), WINDOWS[0]):
        for tol in TOLERANCES:
            starts = _search(half, tol)
            if starts is not None:
                return starts, tol
    return set(), 0.0


def _ranges(core: str, sura: int, aya: int, moshaf: Any) -> list[Candidate]:
    """Every range from `aya` whose length is not far past what was heard, each scored."""
    count = surah_list()[sura - 1].ayat
    ref = ""
    out = []
    for end in range(aya, min(count, aya + MAX_AYAT_PER_REQUEST - 1) + 1):
        ref += ayah_phonemes(sura, end, moshaf)
        out.append(Candidate(sura, aya, end, Levenshtein.distance(core, ref)))
        if len(ref) > len(core) * 1.25 + 10:
            break
    return out


def _with_next(starts: set[Start]) -> set[Start]:
    """The starts found, and the ayah after each. A search hit can begin a word or two early in
    the previous ayah, and starting from an ayah that was not recited costs its whole length, so
    adding the next one never pulls a real start away."""
    names = surah_list()
    return starts | {(s, a + 1) for s, a in starts if a + 1 <= names[s - 1].ayat}


def _hint_rank(c: Candidate, hint: Start | None) -> int:
    if not hint:
        return 3
    if c.sura == hint[0] and c.aya == hint[1] + 1:
        return 0  # the next ayah: reading in order
    if c.sura == hint[0] and c.aya == hint[1]:
        return 1
    return 2 if c.sura == hint[0] else 3


def _matched_by_chance(core: str, best: Candidate, moshaf: Any) -> bool:
    # Letters heard beyond the range's length may be words said again after going back, so they
    # are not held against it here; choose_range scores the ranges with the stops in view.
    ref_len = sum(
        len(ayah_phonemes(best.sura, a, moshaf)) for a in range(best.aya, best.aya_end + 1)
    )
    extra = max(0, len(core) - ref_len)
    return best.distance - extra > 0.5 * min(len(core), ref_len)


def _fatiha_basmala(c: Candidate) -> Candidate:
    """In Al-Fatiha the basmala is ayah 1, not an opening."""
    return dataclasses.replace(c, aya=1) if c.sura == 1 and c.aya == 2 else c


def detect(heard: str, moshaf: Any, hint: Start | None = None) -> Detection | None:
    """The detected ayat, or None when the recitation does not match anywhere."""
    t0 = time.perf_counter()
    core, prefixes = _openings(heard, moshaf)
    if len(core) < 2:
        return None
    starts, tol = _search_starts(core)
    if not starts:
        return None

    def order(c: Candidate) -> tuple[int, int, int, int, int]:
        return (c.distance, _hint_rank(c, hint), c.sura, c.aya, c.aya_end)

    scored = {s: _ranges(core, *s, moshaf) for s in _with_next(starts)}
    cands = sorted((min(rs, key=order) for rs in scored.values()), key=order)
    ranges = sorted((c for rs in scored.values() for c in rs), key=order)[:MAX_RANGES]
    best = cands[0]
    if _matched_by_chance(core, best, moshaf):
        return None  # the start matched by chance; most of the recording does not

    margin = max(3, round(0.05 * len(core)))
    near = [c for c in cands if c.distance - best.distance < margin]
    # An exact match that nothing else equals counts as clear, even when another ayah is only a
    # letter away (1:2 against 37:182, which adds a waw).
    if best.distance == 0 and all(c.distance > 0 for c in near[1:]):
        near = [best]
    if "basmala" in prefixes and best.sura == 1 and best.aya == 2:
        prefixes = tuple(p for p in prefixes if p != "basmala")
        near = [_fatiha_basmala(c) if c is best else c for c in near]
        ranges = [_fatiha_basmala(c) for c in ranges]
    return Detection(
        candidates=near[:MAX_CANDIDATES],
        ranges=ranges,
        clear=len(near) == 1,
        prefixes=prefixes,
        tolerance=tol,
        ms=round((time.perf_counter() - t0) * 1000),
    )
