"""Auto mode: which detected range was recited, judged with the stops in view.

Ported from tajweed_ai `muaalem_lab/collect_api.py` (_choose_range, _infer_path, _infer_from).
Detection compares whole ayat with everything heard, so words said again after going back count
against the right range, and an extra ayah can soak them up. Each of the closest ranges is scored
instead by how far what was heard is from its best path: a repeat after a pause then costs
nothing.
"""

from typing import Any

from app.engine.pipeline.detect import Candidate, Detection
from app.engine.pipeline.heard import Heard
from app.engine.pipeline.path import Inferred, infer
from app.engine.text.qt import chunck_phonemes
from app.engine.text.quran_text import surah_list
from app.engine.text.structure import Structure, TextSelection, normalize_prefixes

RESCORE_RANGES = 4  # detected ayah ranges scored again with the stops in view


def infer_path(text: TextSelection, moshaf: Any, heard: Heard) -> Inferred | None:
    """The recitation path for a selection, from the pauses and what was heard; None leaves the
    default (also when the path search finds the selection invalid)."""
    aya_end = text.aya_start if text.aya_end is None else text.aya_end
    selection = Structure(
        text.sura,
        text.aya_start,
        aya_end,
        text.word_start,
        text.word_end,
        normalize_prefixes(text.prefixes),
    )
    try:
        groups = chunck_phonemes(heard.text) if heard.text else []
        return infer(selection, moshaf, groups, list(heard.group_frames), heard.pauses)
    except ValueError:
        return None


def _candidate(c: Candidate, path_distance: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "sura": c.sura,
        "sura_name": surah_list()[c.sura - 1].name,
        "aya_start": c.aya,
        "aya_end": c.aya_end,
        "distance": c.distance,
    }
    return d if path_distance is None else {**d, "path_distance": path_distance}


def choose_range(
    det: Detection, moshaf: Any, heard: Heard
) -> tuple[TextSelection, list[dict[str, Any]], bool, Inferred | None]:
    """The chosen text, the candidates for the screen (closest first, each with `path_distance`
    when rescored), whether the choice is clear, and the chosen range's inferred path (None: none
    was found, or nothing was rescored)."""

    def text_of(c: Candidate) -> TextSelection:
        return TextSelection(c.sura, c.aya, c.aya_end, prefixes=det.prefixes)

    best = det.candidates[0]
    margin = max(3, round(0.05 * len(heard.text)))
    if best.distance <= margin or not det.ranges:
        # nearly exact already: nothing was repeated that another range could explain better
        return text_of(best), [_candidate(c) for c in det.candidates], det.clear, None
    scored = []
    for k, c in enumerate(det.ranges[:RESCORE_RANGES]):
        inferred = infer_path(text_of(c), moshaf, heard)
        # the path search only stops at pauses, so its reading can be a little further than the
        # plain one: a range is never scored worse than its plain distance
        score = min(c.distance, inferred.distance) if inferred else c.distance
        scored.append((score, k, c, inferred))
    scored.sort(key=lambda x: (x[0], x[1]))  # ties keep detection's order (and its hint)
    top = scored[0][0]
    near = [x for x in scored if x[0] - top < margin]
    _, _, chosen, inferred = scored[0]
    return text_of(chosen), [_candidate(c, s) for s, _, c, _ in near], len(near) == 1, inferred
