"""The path search: a dynamic programme over the silences (cuts.py) and the selected words.

Ported from tajweed_ai `muaalem_lab/path.py` (infer). The lab's ~170-line function of closures is
the PathSearch class here; the loops, costs and strict `<` comparisons are unchanged, so ties
break the same way (dict order, then the first cheaper candidate wins).
"""

import dataclasses
import itertools
from typing import Any

import Levenshtein

from app.engine.pipeline.path.cuts import Cut, split_points
from app.engine.pipeline.path.result import Inferred, boundaries
from app.engine.pipeline.pauses import Pauses
from app.engine.text import rules as R
from app.engine.text.boundaries import STOP_OPTION, SpecialBoundary, special_boundaries
from app.engine.text.quran_text import ISTIAATHA, basmala_text
from app.engine.text.reference import Reference, build_reference_from_structure, phonetize
from app.engine.text.structure import Structure, TextSelection, default_structure

BACK_PENALTY = 0.5  # per word gone back: with equal fit, carrying on wins
LENGTH_SLACK = 0.35  # a candidate whose script length is this far off what was heard is skipped
WRONG_TEXT = 0.3  # heard this far from the default reference (share of its length): another text
INF = float("inf")

Choices = tuple[tuple[int, str], ...]  # (word, choice) at special boundaries inside a segment
Back = tuple[int, int, int, Choices]  # (cut, previous segment's last word, first word, choices)
Cell = tuple[float, Back | None]


class PathSearch:
    """The search state for one selection and one recording."""

    def __init__(
        self, st0: Structure, moshaf: Any, heard_groups: list[str], cuts: list[Cut]
    ) -> None:
        self.st0, self.moshaf, self.heard_groups, self.cuts = st0, moshaf, heard_groups, cuts
        self.words = st0.words()
        self.n_words = len(self.words)
        selection = TextSelection(
            st0.sura, st0.aya_start, st0.aya_end, st0.word_start, st0.word_end
        )
        self.default = default_structure(selection, moshaf)
        self.specials = special_boundaries()
        self._scripts: dict[tuple[int, int], tuple[tuple[str, Choices], ...]] = {}
        self.word_len = [len(self.scripts(g, g)[0][0]) for g in range(self.n_words)]

    # ---- the words and their special boundaries ----

    def special_at(self, g: int) -> SpecialBoundary | None:
        w = self.words[g]
        return self.specials.get((w.sura, w.aya, w.word))

    def connected_choices(self, g: int) -> tuple[str, ...]:
        """The correct ways to connect across the special boundary after word g (none: not one)."""
        sb = self.special_at(g)
        if sb is None:
            return ()
        if sb.attr in R.DEFAULT.connected_alternatives:
            return tuple(c for c in R.DEFAULT.connected_alternatives[sb.attr] if c in sb.options)
        choice = getattr(self.moshaf, sb.attr)
        if choice == STOP_OPTION or choice not in sb.options:
            choice = next(o for o in sb.options if o != STOP_OPTION)
        return (choice,)

    def scripts(self, a: int, b: int) -> tuple[tuple[str, Choices], ...]:
        """Words a..b phonetized as one stretch ending in a stop, once per combination of the
        connected choices at the special boundaries inside, with that combination: exactly what
        build_reference_from_structure gives a segment."""
        if (a, b) not in self._scripts:
            text = " ".join(w.text for w in self.words[a : b + 1])
            places = [
                (g, self.connected_choices(g)) for g in range(a, b) if self.connected_choices(g)
            ]
            attrs = [
                self.specials[(self.words[g].sura, self.words[g].aya, self.words[g].word)].attr
                for g, _ in places
            ]
            out = []
            for combo in itertools.product(*(cs for _, cs in places)):
                overrides = dict(zip(attrs, combo, strict=True))
                ph = phonetize(
                    text, self.moshaf.model_copy(update=overrides), self.st0.sura
                ).phonemes
                out.append((ph, tuple((g, c) for (g, _), c in zip(places, combo, strict=True))))
            self._scripts[(a, b)] = tuple(out)
        return self._scripts[(a, b)]

    def ayah_start_of(self, g: int) -> int:
        while g > 0 and not self.words[g - 1].ayah_last:
            g -= 1
        return g

    def back_limit(self, b: int) -> int:
        """The earliest word a reciter may resume from after stopping at word b."""
        s = (
            self.ayah_start_of(min(b + 1, self.n_words - 1))
            if b + 1 < self.n_words
            else self.ayah_start_of(b)
        )
        return self.ayah_start_of(s - 1) if s > 0 else 0

    # ---- the cuts ----

    def heard_at(self, i: int, j: int) -> str:
        return "".join(self.heard_groups[self.cuts[i][0] : self.cuts[j][0]])

    def no_hard_between(self, i: int, j: int) -> bool:
        return not any(self.cuts[k][1] == "hard" for k in range(i + 1, j))

    # ---- the search ----

    def start_costs(self) -> dict[int, float]:
        """The openings (isti'adha, basmala) come first, each its own part ending at a pause:
        cost of reaching each cut after them."""
        start_cost = {0: 0.0}
        for pre in self.st0.prefixes:
            text = ISTIAATHA if pre == "istiaatha" else basmala_text()
            want = phonetize(text, self.moshaf).phonemes
            nxt: dict[int, float] = {}
            for i, c in start_cost.items():
                for j in range(i + 1, len(self.cuts) - 1):
                    if not self.no_hard_between(i, j):
                        break
                    cost = c + Levenshtein.distance(self.heard_at(i, j), want)
                    if cost < nxt.get(j, INF):
                        nxt[j] = cost
            start_cost = nxt
        return start_cost

    def _starts(self, i: int, b_prev: int) -> range | list[int]:
        """Where a segment after cut i may start, given the previous one ended at b_prev."""
        if b_prev < 0:
            return [0]
        if self.cuts[i][1] == "soft":
            # a soft pause can only be a stop at an ayah end
            return [b_prev + 1] if self.words[b_prev].ayah_last else []
        return range(self.back_limit(b_prev), b_prev + 2)

    def _try_segments(
        self, best: list[dict[int, Cell]], i: int, j: int, b_prev: int, a: int
    ) -> None:
        """Every segment a..b heard between cuts i and j, after a segment ending at b_prev."""
        heard = self.heard_at(i, j)
        c_prev = best[i][b_prev][0]
        est = 0
        for b in range(a, self.n_words):
            est += self.word_len[b]
            if est < len(heard) * (1 - LENGTH_SLACK) - 6:
                continue
            if est > len(heard) * (1 + LENGTH_SLACK) + 6:
                break
            if j == len(self.cuts) - 1 and b != self.n_words - 1:
                continue
            fit, chosen = min(
                (Levenshtein.distance(heard, ph), ch) for ph, ch in self.scripts(a, b)
            )
            cost = c_prev + fit
            if b_prev >= 0 and a <= b_prev:
                cost += BACK_PENALTY * (b_prev + 1 - a)
            if cost < (best[j][b][0] if b in best[j] else INF):
                best[j][b] = (cost, (i, b_prev, a, chosen))

    def table(self, start_cost: dict[int, float]) -> list[dict[int, Cell]]:
        """best[i][b] = (cost, back-pointer) for a segment ending at word b exactly at cut i."""
        best: list[dict[int, Cell]] = [{} for _ in self.cuts]
        for i, c in start_cost.items():
            best[i][-1] = (c, None)
        for i in range(len(self.cuts) - 1):
            if not best[i]:
                continue
            for j in range(i + 1, len(self.cuts)):
                if not self.no_hard_between(i, j):
                    break  # a segment may not run across a hard pause
                for b_prev in list(best[i]):
                    for a in self._starts(i, b_prev):
                        if a < self.n_words:
                            self._try_segments(best, i, j, b_prev, a)
        return best

    def trace(
        self, best: list[dict[int, Cell]]
    ) -> tuple[list[tuple[int, int]], list[int], dict[int, str]]:
        """Segments, the cut each started at, and the choices at special boundaries."""
        segs: list[tuple[int, int]] = []
        used_cuts: list[int] = []
        special: dict[int, str] = {}
        j, b = len(self.cuts) - 1, self.n_words - 1
        while b >= 0:
            back = best[j][b][1]
            if back is None:
                raise RuntimeError("path trace reached an opening before word 0")
            i, b_prev, a, chosen = back
            segs.append((a, b))
            used_cuts.append(i)
            special.update(chosen)
            j, b = i, b_prev
        segs.reverse()
        used_cuts.reverse()
        return segs, used_cuts, special

    def default_reference(self) -> Reference:
        return build_reference_from_structure(
            dataclasses.replace(self.default, prefixes=self.st0.prefixes), self.moshaf
        )


def _another_text(heard: str, ref_ph: str, allow_extra: bool) -> bool:
    """Most of what was heard doesn't match: words said again after going back are extra letters
    heard, so beyond the reference's length they aren't counted when `allow_extra`."""
    extra = max(0, len(heard) - len(ref_ph)) if allow_extra else 0
    return Levenshtein.distance(heard, ref_ph) - extra > WRONG_TEXT * len(ref_ph)


def infer(
    st0: Structure,
    moshaf: Any,
    heard_groups: list[str],
    group_frames: list[tuple[int, int]],
    pauses: Pauses | None,
) -> Inferred | None:
    """The most likely path, or None when there is nothing to infer from."""
    if not heard_groups or pauses is None:
        return None
    cuts: list[Cut] = [(0, "start", None), *split_points(group_frames, pauses)]
    cuts.append((len(heard_groups), "end", None))
    search = PathSearch(st0, moshaf, heard_groups, cuts)
    heard_all = "".join(heard_groups)
    default_ph = search.default_reference().phonetic.phonemes
    if _another_text(heard_all, default_ph, allow_extra=True):
        return None  # another text: nothing to infer a path from
    start_cost = search.start_costs()
    if not start_cost:
        return None  # an opening joined to the ayah without a pause: left to the reciter
    best = search.table(start_cost)
    if best[-1].get(search.n_words - 1) is None:
        return None
    segs, used_cuts, special = search.trace(best)
    structure = dataclasses.replace(
        search.default, prefixes=st0.prefixes, segments=segs, special=special
    )
    ref = build_reference_from_structure(structure, moshaf)
    distance = Levenshtein.distance(heard_all, ref.phonetic.phonemes)
    if distance > WRONG_TEXT * len(ref.phonetic.phonemes):
        return None  # even the best path leaves most of it unmatched: another text
    bounds = boundaries(segs, used_cuts, cuts, search.words)
    differs = (
        segs != search.default.segments
        or special != search.default.special
        or any(b.kind.startswith("uncertain") for b in bounds)
    )
    return Inferred(
        structure, bounds, distance, Levenshtein.distance(heard_all, default_ph), differs
    )
