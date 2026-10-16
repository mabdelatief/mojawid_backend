"""Rows for differences explain_error doesn't report at all.

Ported from tajweed_ai `muaalem_lab/analysis.py` (_rows_explain_error_missed). explain_error skips
changed groups that end in an imala, sakt or mukhtalasa mark (its own TODO), so a missed sakt
showed in the review but not on the result screen. Our diff is the list of places; explain_error
only names them.
"""

from app.engine.pipeline.analysis.words import Row, cluster_span, word_index
from app.engine.text.phonetic_diff import phoneme_diff
from app.engine.text.qt import extract_ref_phonetic_to_uthmani
from app.engine.text.readable import describe
from app.engine.text.reference import Reference


def _taken(rows: list[Row]) -> set[int]:
    taken: set[int] = set()
    for r in rows:
        a, b = r["ph_pos"]
        taken.update(range(a, max(b, a + 1)))
    return taken


def _row(i: int, blk: Row, ref: Reference, uth: tuple[int, int]) -> Row:
    u0, u1 = uth
    s, t = cluster_span(ref.uthmani, u0, u1)
    return {
        "id": i, "error_type": "normal", "operation": blk["op"],
        "uthmani_pos": [u0, u1], "uthmani_span": [s, t], "uthmani_text": ref.uthmani[s:t],
        "word_index": word_index(ref.uthmani, u0), "segment": ref.segment_at(u0),
        "ph_pos": list(blk["ref_span"]), "expected_ph": blk["ref"], "predicted_ph": blk["pred"],
        "expected_text": describe(blk["ref"]), "heard_text": describe(blk["pred"]),
        "expected_len": None, "predicted_len": None, "rules": [], "inserted_rules": [],
        "replaced_rules": [], "missing_rules": [], "likely_false_alarm": False,
        "valid_variant": None, "ghunnah": None,
    }  # fmt: skip


def rows_explain_error_missed(ref: Reference, predicted: str, rows: list[Row]) -> list[Row]:
    """A normal row for every differing block no explain_error row covers."""
    taken = _taken(rows)
    ph_to_uth = extract_ref_phonetic_to_uthmani(ref.phonetic.mappings)
    out: list[Row] = []
    for blk in phoneme_diff(ref.phonetic.phonemes, predicted):
        if blk["op"] == "equal":
            continue
        a, b = blk["ref_span"]
        if any(i in taken for i in range(a, max(b, a + 1))):
            continue
        k = min(a, len(ph_to_uth) - 1)
        if k < 0:
            continue
        u0 = ph_to_uth[k]
        u1 = (ph_to_uth[b - 1] + 1) if b > a else u0
        out.append(_row(len(rows) + len(out), blk, ref, (u0, u1)))
    return out
