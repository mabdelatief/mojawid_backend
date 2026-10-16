"""Two marks on the error rows: raum (with raum practice on) and how sure the model was.

Ported from tajweed_ai `muaalem_lab/analysis.py` (_mark_raum, _overlaps, _mark_doubt).
"""

from typing import Any

from app.engine.pipeline import doubt as DOUBT
from app.engine.pipeline.analysis.words import Row
from app.engine.pipeline.heard import Heard
from app.engine.text.groups import ref_groups
from app.engine.text.qt import alph
from app.engine.text.reference import Reference

RAUM_VARIANT = {"reason": "raum", "ar": "قد يكون رومًا، وهو جائز إن قصدته"}


def mark_raum(errors: list[Any], rows: list[Row], ref: Reference) -> None:
    """With raum practice on (rules.practices), a damma or kasra heard on the last letter before a
    stop may be the reciter's raum: shown as a valid way, not a mistake. The model can't tell raum
    from a full haraka, so it says "may be"."""
    groups = ref_groups(ref)
    stop_ends = {
        g.end
        for g in groups
        if not g.residual and all(x.segment != g.segment or x.index <= g.index for x in groups)
    }
    harakat = (alph.phonetics.dama, alph.phonetics.kasra)
    for e, row in zip(errors, rows, strict=False):
        got, exp = e.preditected_ph, e.expected_ph
        if (
            not row["likely_false_alarm"]
            and e.ph_pos[1] in stop_ends
            and exp
            and got[:-1] == exp
            and got[-1:] in harakat
        ):
            row.update(valid_variant=dict(RAUM_VARIANT), likely_false_alarm=True)


def overlaps(a: int, b: int, ra: int, rb: int) -> bool:
    """Two reference spans share a place; an empty span (an insertion) is a point."""
    lo, hi = max(a, ra), min(b, rb)
    return lo < hi or (lo == hi and (a == b or ra == rb))


def mark_doubt(rows: list[Row], diff: list[Row], heard: Heard) -> None:
    """`doubt_ratio` per row (how many times more likely what was heard is than the expected
    reading; None: not known), and `uncertain` when that is under doubt.DOUBT_RATIO."""
    ratios = None
    if heard.phoneme_probs is not None and heard.phoneme_vocab:
        ratios = DOUBT.ratios(heard.phoneme_probs, heard.phoneme_vocab, heard.text, diff)
    for row in rows:
        r = None
        if ratios is not None:
            a, b = row["ph_pos"]
            hit = [
                x
                for blk, x in zip(diff, ratios, strict=True)
                if blk["op"] != "equal" and overlaps(a, b, *blk["ref_span"])
            ]
            r = min(hit) if hit else None
        row["doubt_ratio"] = None if r is None else round(min(r, 1e6), 2)
        row["uncertain"] = not row["likely_false_alarm"] and DOUBT.is_uncertain(r)
