"""The sifat table: one row per aligned letter group, expected against heard on all 10 attributes.

Ported from tajweed_ai `muaalem_lab/analysis.py` (sifat_rows, _label, SIFAT_LEVEL_AR). Missing
reference letters are kept as rows. The lab's `_unreliable_levels` (for analyses made before its
own decoder) never applies to our decoder and is dropped.

New for Mojawid (user's decision, 2026-10-15): `allowed`. Where the rules count every value as
correct at that letter (rules.both_valid: e.g. the raa of «مِصْرَ» at a stop), a differing value
is marked allowed, so the app shows it as correct, the way allowed madd lengths are never counted.

Fixed in Mojawid (audit 2026-10-16, docs/research/README.md C1): the rows are paired by our own
alignment of whole letter groups, expected against heard. The lab used quran-muaalem's
segment_groups, whose merge_same_phoneme_group pairs a letter with its neighbour whenever one
group's text is inside the next (the lam of «ٱللَّهُ» with the lam before it): on a perfect
recitation it dropped 1,200 rows over the whole Quran and showed 227 made-up tafkheem
mismatches.
"""

from typing import Any

import Levenshtein

from app.engine.pipeline.analysis.words import Row
from app.engine.pipeline.heard import Heard
from app.engine.pipeline.qm import SIFAT_ATTR_TO_ARABIC_WITHOUT_BRACKETS
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


def tag_of(ref: str, out: str) -> str:
    """exact / changed / insert / delete; the same madd letter at another length is exact (its
    length is judged by the error rows, not the sifat table)."""
    if ref == out:
        return "exact"
    if not out:
        return "delete"
    if not ref:
        return "insert"
    return "exact" if ref[0] == out[0] and ref[0] in MADD_CHARS else "changed"


def pair_groups(ref: list[str], heard: list[str]) -> list[tuple[int | None, int | None]]:
    """Expected and heard letter groups lined up by a minimal edit of whole groups: equal groups
    pair one to one, changed runs pair by position, and the rest are missing or extra."""
    codes: dict[str, str] = {}
    a = "".join(codes.setdefault(g, chr(0xE000 + len(codes))) for g in ref)
    b = "".join(codes.setdefault(g, chr(0xE000 + len(codes))) for g in heard)
    pairs: list[tuple[int | None, int | None]] = []
    for _, i1, i2, j1, j2 in Levenshtein.opcodes(a, b):
        for k in range(max(i2 - i1, j2 - j1)):
            pairs.append((i1 + k if i1 + k < i2 else None, j1 + k if j1 + k < j2 else None))
    return pairs


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
    ref_g = [s.phonemes for s in exp_sifat]
    heard_g = [s.phonemes_group for s in heard.sifat]
    groups = ref_groups(ref)
    rows = []
    for ri, hi in pair_groups(ref_g, heard_g):
        r, o = (ref_g[ri] if ri is not None else ""), (heard_g[hi] if hi is not None else "")
        exp = exp_sifat[ri] if ri is not None else None
        got = heard.sifat[hi] if hi is not None else None
        allowed = _allowed_levels(ref, groups, ri)
        ctx = (exp, got, heard, hi)
        rows.append(
            {"tag": tag_of(r, o), "ref": r, "pred": o, "ref_text": describe(r),
             "pred_text": describe(o), "ref_idx": ri,
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
