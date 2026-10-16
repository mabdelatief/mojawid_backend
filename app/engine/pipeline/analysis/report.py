"""The report for one recording: what the result screen needs.

Ported from tajweed_ai `muaalem_lab/analysis.py` (analyze). The lab also returned a "raw" record
for its stored recordings; Mojawid stores nothing, so only the report is built, once per request
(the lab built it twice). Its `sifat_unreliable_probs` (always empty with its own decoder) is
dropped.
"""

import dataclasses
from typing import Any

from app.engine.pipeline.analysis.marks import mark_doubt, mark_raum
from app.engine.pipeline.analysis.missed import rows_explain_error_missed
from app.engine.pipeline.analysis.rows import error_row
from app.engine.pipeline.analysis.sifat import SIFAT_LEVEL_AR, all_missing_rows, sifat_rows
from app.engine.pipeline.analysis.words import cluster_span, uthmani_segments
from app.engine.pipeline.heard import Heard
from app.engine.text.letter_sifat import SIFAT_LEVELS
from app.engine.text.phonetic_diff import phoneme_diff
from app.engine.text.qt import explain_error
from app.engine.text.reference import Reference
from app.engine.text.tajweed import tajweed_spans


def analyze(heard: Heard, ref: Reference, raum_practice: bool = False) -> dict[str, Any]:
    """The report. `raum_practice`: the reciter turned raum practice on, so a haraka heard at a
    stop may be raum."""
    predicted = heard.text
    ref_ph = ref.phonetic.phonemes
    errors = explain_error(
        uthmani_text=ref.uthmani,
        ref_ph_text=ref_ph,
        predicted_ph_text=predicted,
        mappings=ref.phonetic.mappings,
    )
    rows = [
        error_row(i, e, ref, cluster_span(ref.uthmani, *e.uthmani_pos))
        for i, e in enumerate(errors)
    ]
    if raum_practice:
        mark_raum(errors, rows, ref)
    rows += rows_explain_error_missed(ref, predicted, rows)
    diff = phoneme_diff(ref_ph, predicted)
    mark_doubt(rows, diff, heard)
    shown = [r for r in rows if not r["likely_false_alarm"]]  # mistakes and uncertain places
    return {
        "uthmani": ref.uthmani,
        "segments": [dataclasses.asdict(seg) for seg in ref.segments],
        "words": uthmani_segments(ref.uthmani, shown),
        "tajweed": tajweed_spans(ref.uthmani, ref.phonetic),
        "reference_phonemes": ref_ph,
        "predicted_phonemes": predicted,
        "exact_match": predicted == ref_ph,
        "diff": diff,
        "errors": rows,
        "sifat_levels": [{"name": n, "ar": SIFAT_LEVEL_AR[n]} for n in SIFAT_LEVELS],
        "sifat": sifat_rows(heard, ref) if heard.sifat else all_missing_rows(ref),
    }
