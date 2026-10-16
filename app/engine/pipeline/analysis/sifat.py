"""The sifat table: one row per aligned letter group, expected against heard on all 10 attributes.

Ported from tajweed_ai `muaalem_lab/analysis.py` (sifat_rows, _label, SIFAT_LEVEL_AR), using
quran-muaalem's own alignment (segment_groups on a diff_match_patch diff). Missing reference
letters are kept as rows. The lab's `_unreliable_levels` (for analyses made before its own
decoder) never applies to our decoder and is dropped.

New for Mojawid (user's decision, 2026-10-15): `allowed`. Where the rules count every value as
correct at that letter (rules.both_valid: e.g. the raa of «مِصْرَ» at a stop), a differing value
is marked allowed, so the app shows it as correct, the way allowed madd lengths are never counted.

Fixed in Mojawid (user's decision, 2026-10-16): a row's tag follows what the main (phonemes)
output heard on that stretch, not only the sifat outputs' letter groups. Those can split the
letters differently from the phonemes output (one lam where it heard the doubled lam of «ٱللَّهُ»),
and the lab then shows «حرف مختلف» on a letter read exactly as expected.
"""

from typing import Any

import diff_match_patch as dmp

from app.engine.pipeline.analysis.words import Row
from app.engine.pipeline.heard import Heard
from app.engine.pipeline.qm import SIFAT_ATTR_TO_ARABIC_WITHOUT_BRACKETS, segment_groups
from app.engine.text.groups import MADD_CHARS, RefGroup, both_valid_for, ref_groups
from app.engine.text.letter_sifat import SIFAT_LEVELS
from app.engine.text.readable import describe
from app.engine.text.reference import Reference

SIFAT_LEVEL_AR = {
    "hams_or_jahr": "الهمس / الجهر",
    "shidda_or_rakhawa": "الشدة / الرخاوة",
    "tafkheem_or_taqeeq": "التفخيم / الترقيق",
    "itbaq": "الإطباق",
    "safeer": "الصفير",
    "qalqla": "القلقلة",
    "tikraar": "التكرار",
    "tafashie": "التفشي",
    "istitala": "الاستطالة",
    "ghonna": "الغنة",
}


def label(v: str | None) -> dict[str, str] | None:
    if v is None or v in ("[PAD]", "None", ""):
        return None
    return {"en": v, "ar": SIFAT_ATTR_TO_ARABIC_WITHOUT_BRACKETS.get(v, v)}


def _tag(g: Any) -> str:
    tag = str(g.get_tag())
    if tag == "partial":
        return "exact" if g.ref[0] in MADD_CHARS else "changed"  # same madd letter, other length
    return tag


def heard_at(diffs: list[tuple[int, str]], start: int, end: int) -> str:
    """The heard text the diff lines up with expected[start:end]; an insertion right after the
    span counts toward it (as the row alignment gives it to that row)."""
    out, pos = [], 0
    for op, text in diffs:
        if op == dmp.diff_match_patch.DIFF_INSERT:
            if start < pos <= end:
                out.append(text)
            continue
        a, pos = pos, pos + len(text)
        if op == dmp.diff_match_patch.DIFF_EQUAL and max(a, start) < min(pos, end):
            out.append(text[max(a, start) - a : min(pos, end) - a])
    return "".join(out)


def _read_as_expected(g: Any, tag: str, diffs: list[tuple[int, str]], starts: list[int]) -> bool:
    """A changed or missing row whose stretch the phonemes output heard exactly as expected."""
    if tag not in ("changed", "delete") or g.ref_idx is None:
        return False
    start = starts[g.ref_idx]
    return bool(heard_at(diffs, start, start + len(g.ref)) == g.ref)


def _attr(level: str, ctx: tuple[Any, Any, Heard, Any], allowed: bool) -> dict[str, Any]:
    exp, got, heard, out_idx = ctx
    e = label(getattr(exp, level)) if exp is not None else None
    unit = got.values.get(level) if got is not None else None
    p = label(unit.text) if unit is not None else None
    prob = round(unit.prob, 4) if unit is not None and p is not None else None
    mismatch = bool(e and p and e["en"] != p["en"])
    sure = heard.sure
    return {
        "expected": e,
        "predicted": p,
        "prob": prob,
        "mismatch": mismatch,
        # may this value become a question: the decoder's own check (or a usable probability)
        "sure": bool(sure[level][out_idx])
        if sure is not None and out_idx is not None
        else prob is not None,
        "allowed": mismatch and allowed,
    }


def _allowed_levels(ref: Reference, groups: list[RefGroup], ref_idx: int | None) -> set[str]:
    if ref_idx is None:
        return set()
    return {lv for lv in SIFAT_LEVELS if both_valid_for(ref, groups[ref_idx], lv) is not None}


def sifat_rows(heard: Heard, ref: Reference) -> list[Row]:
    """One row per aligned letter group (heard must have sifat)."""
    exp_sifat = ref.phonetic.sifat
    diffs = dmp.diff_match_patch().diff_main(ref.phonetic.phonemes, heard.text)
    aligned = segment_groups(
        ref_groups=[s.phonemes for s in exp_sifat],
        groups=[s.phonemes_group for s in heard.sifat],
        diffs=diffs,
    )
    groups = ref_groups(ref)
    starts = [0]
    for s in exp_sifat:
        starts.append(starts[-1] + len(s.phonemes))
    rows = []
    for g in aligned:
        exp = exp_sifat[g.ref_idx] if g.ref_idx is not None else None
        got = heard.sifat[g.out_idx] if g.out_idx is not None else None
        allowed = _allowed_levels(ref, groups, g.ref_idx)
        ctx = (exp, got, heard, g.out_idx)
        tag, pred = _tag(g), g.out
        if _read_as_expected(g, tag, diffs, starts):
            tag, pred = "exact", g.ref
        rows.append(
            {"tag": tag, "ref": g.ref, "pred": pred, "ref_text": describe(g.ref),
             "pred_text": describe(pred), "ref_idx": g.ref_idx,
             "attrs": {lv: _attr(lv, ctx, lv in allowed) for lv in SIFAT_LEVELS}}
        )  # fmt: skip
    return rows


def all_missing_rows(ref: Reference) -> list[Row]:
    """Silence or nothing recognised: every reference letter is missing."""
    return [
        {"tag": "delete", "ref": s.phonemes, "pred": "", "attrs": {
            n: {"expected": label(getattr(s, n)), "predicted": None, "prob": None,
                "mismatch": False, "sure": False, "allowed": False}
            for n in SIFAT_LEVELS}}
        for s in ref.phonetic.sifat
    ]  # fmt: skip
