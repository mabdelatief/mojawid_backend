"""The reference's letter groups, each placed in the Uthmani text, its segment and its word.

Ported from tajweed_ai `muaalem_lab/labels.py` (RefGroup, ref_groups) and
`collect_api._both_valid` (here `both_valid_for`).
"""

import dataclasses
from typing import Any

from app.engine.text import rules as R
from app.engine.text.qt import (
    alph,
    chunck_phonemes,
    extract_ref_phonetic_to_uthmani,
    get_ref_phonetic_groups_tajweed_rules,
)
from app.engine.text.readable import split_group
from app.engine.text.reference import Reference

_PH = alph.phonetics
MADD_CHARS: str = _PH.alif + _PH.waw_madd + _PH.yaa_madd
GHUNNAH_CHARS: str = _PH.noon_mokhfah + _PH.meem_mokhfah
MADD_RULES = {
    "Normal Madd", "Monfasel Madd", "Mottasel Madd", "Mottasel Madd at Pause",
    "Lazem Madd", "Aared Madd", "Leen Madd",
}  # fmt: skip


@dataclasses.dataclass
class RefGroup:
    """One letter group of the reference."""

    index: int
    text: str
    start: int  # span in the reference phonetic script
    end: int
    uth_start: int  # span in the reference Uthmani text
    uth_end: int
    uth_char: str  # the Uthmani letter the group starts from
    segment: int
    word: int | None  # index into the segment's words
    kind: str  # "madd" | "ghunnah" | "letter"
    core: str
    count: int  # how many times the core character repeats (madd/ghunnah length, shadda)
    residual: str  # trailing haraka / mark, or ""
    rules: list[str]
    # harakat = count + harakat_offset for a madd: a leen madd of N harakat is written as N-1
    # letters (2 → و, 4 → ووو, 6 → ووووو); every other madd is one letter per haraka
    harakat_offset: int = 0

    def to_json(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _kind(core: str, count: int, residual: str, names: list[str]) -> str:
    if core in MADD_CHARS or (core in "وي" and not residual and MADD_RULES & set(names)):
        return "madd"  # also leen and the ayn of the opening letters: a repeated و/ي (never a
        # voweled و/ي, which is a consonant next to a madd)
    if core in GHUNNAH_CHARS or (core in "نموي" and count >= 3):
        return "ghunnah"  # ikhfaa, iqlab, mushaddad noon/meem, idgham with ghunnah
    return "letter"


def ref_groups(ref: Reference) -> list[RefGroup]:
    """Every letter group of the reference, placed."""
    phon = ref.phonetic.phonemes
    groups = chunck_phonemes(phon)
    ph_to_uth = extract_ref_phonetic_to_uthmani(ref.phonetic.mappings)
    rules = get_ref_phonetic_groups_tajweed_rules(groups, ref.phonetic.mappings, ph_to_uth)
    out, pos = [], 0
    for i, g in enumerate(groups):
        start, end = pos, pos + len(g)
        pos = end
        first = min(ph_to_uth[k] for k in range(start, end))
        last = max(ph_to_uth[k] for k in range(start, end))
        core, count, residual = split_group(g)
        names = sorted({r.name.en for r in rules[i]})
        kind = _kind(core, count, residual, names)
        seg_i = ref.segment_at(first)
        seg = ref.segments[seg_i]
        word = next((k for k, w in enumerate(seg.words) if w.start <= first < w.end + 1), None)
        leen = kind == "madd" and core in "وي" and "Leen Madd" in names
        out.append(
            RefGroup(i, g, start, end, first, last + 1, ref.uthmani[first], seg_i, word, kind,
                     core, count, residual, names, 1 if leen else 0)
        )  # fmt: skip
    return out


def both_valid_for(ref: Reference, g: RefGroup, level: str) -> R.BothValid | None:
    """Whether the rules count every value of this sifa as correct at this letter (e.g. the raa
    of «وَنُذُرِ» at a stop)."""
    seg = ref.segments[g.segment]
    if g.word is None or seg.kind != "recitation":
        return None
    w = seg.words[g.word]
    place = R.LetterPlace(w.sura, w.aya, w.word, g.word == len(seg.words) - 1, g.uth_char)
    return R.DEFAULT.both_valid_at(level, place)
