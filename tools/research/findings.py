"""Reproduce the findings in docs/research/ (2026-10-16 audit). Each check feeds a hand-made
"heard" phonetic script, or the exact Quran text, through the real engine code. Read-only:
nothing is written and no model is loaded.

    .venv/bin/python -m tools.research.findings            # every check except the slow one
    .venv/bin/python -m tools.research.findings sifat_quran   # whole-Quran sifat sweep (~1 min)
    .venv/bin/python -m tools.research.findings <name> ...    # chosen checks

The output says what the engine does today; docs/research/README.md says what it should do.
"""

from __future__ import annotations

import collections
import dataclasses
import sys
import time
from collections.abc import Callable
from typing import Any

from app.engine.pipeline.analysis.report import analyze
from app.engine.pipeline.analysis.sifat import sifat_rows
from app.engine.pipeline.heard import Heard, HeardGroup, SifaValue
from app.engine.text.letter_sifat import SIFAT_LEVELS
from app.engine.text.moshaf import build_moshaf, moshaf_from_dict
from app.engine.text.qt import (
    alph,
    chunck_phonemes,
    extract_ref_phonetic_to_uthmani,
    get_ref_phonetic_groups_tajweed_rules,
    quran_phonetizer,
)
from app.engine.text.quran_text import ayah_words, surah_list
from app.engine.text.reference import Reference, build_reference_from_structure, phonetize
from app.engine.text.structure import TextSelection, default_structure

P = alph.phonetics


def ref_for(sura: int, aya: int, **reading: Any) -> Reference:
    m = moshaf_from_dict(reading or None)
    return build_reference_from_structure(default_structure(TextSelection(sura, aya), m), m)


def heard(text: str, sifat: list[HeardGroup] | None = None) -> Heard:
    sure = {lv: [True] * len(sifat) for lv in SIFAT_LEVELS} if sifat else None
    return Heard(text=text, probs=[], ids=[], sifat=sifat or [], group_frames=[], sure=sure,
                 gaps={}, n_frames=0)  # fmt: skip


def rows_of(ref: Reference, heard_text: str) -> list[str]:
    out = []
    for r in analyze(heard(heard_text), ref)["errors"]:
        state = "not counted" if r["likely_false_alarm"] else "COUNTED"
        out.append(f"{r['error_type']:8} {r['operation']:7} «{r['uthmani_text']}» "
                   f"{r['expected_text']} -> {r['heard_text']}  [{state}]"
                   f"{' ghunnah=' + r['ghunnah'] if r['ghunnah'] else ''}")  # fmt: skip
    return out or ["(no rows: read as correct)"]


def groups_with_rules(ref: Reference) -> tuple[list[str], list[list[str]]]:
    g = chunck_phonemes(ref.phonetic.phonemes)
    maps = extract_ref_phonetic_to_uthmani(ref.phonetic.mappings)
    rules = get_ref_phonetic_groups_tajweed_rules(g, ref.phonetic.mappings, maps)
    return list(g), [[r.name.en for r in rs] for rs in rules]


def perfect_sifat(ref: Reference) -> list[HeardGroup]:
    """A perfect reciter: every heard group and sifa equal to the expected one."""
    return [
        HeardGroup(s.phonemes, {lv: SifaValue(getattr(s, lv), 0.99, 1) for lv in SIFAT_LEVELS})
        for s in ref.phonetic.sifat
    ]


# --- the checks -----------------------------------------------------------------------------


def sifat_najm23() -> None:
    """Sifat table on a perfect reading of 53:23 (the user's lab recording's ayah)."""
    ref = ref_for(53, 23)
    rows = sifat_rows(heard(ref.phonetic.phonemes, perfect_sifat(ref)), ref)
    print(f"expected letter groups {len(ref.phonetic.sifat)}, table rows {len(rows)}")
    for r in rows:
        mm = {k: (v["expected"]["en"], v["predicted"]["en"])
              for k, v in r["attrs"].items() if v["mismatch"]}  # fmt: skip
        if r["tag"] != "exact" or mm:
            print(f"  row tag={r['tag']} ref={r['ref']!r} pred={r['pred']!r} mismatches={mm}")


def sifat_quran() -> None:
    """Whole Quran, perfect reading: rows dropped and made-up sifa mismatches."""
    m = build_moshaf()
    t0, ayat, lost_ayat, lost, bad_ayat, bad = time.time(), 0, 0, 0, 0, 0
    kinds: collections.Counter[tuple[str, str, str]] = collections.Counter()
    for s in surah_list():
        for a in range(1, s.ayat + 1):
            ref = build_reference_from_structure(default_structure(TextSelection(s.index, a), m), m)
            rows = sifat_rows(heard(ref.phonetic.phonemes, perfect_sifat(ref)), ref)
            ayat += 1
            d = len(ref.phonetic.sifat) - len(rows)
            lost_ayat, lost = lost_ayat + bool(d), lost + d
            mism = [(lv, v["expected"]["en"], v["predicted"]["en"]) for r in rows
                    for lv, v in r["attrs"].items() if v["mismatch"]]  # fmt: skip
            kinds.update(mism)
            bad_ayat, bad = bad_ayat + bool(mism), bad + len(mism)
    print(
        f"{ayat} ayat in {time.time() - t0:.0f}s: {lost_ayat} ayat lose {lost} rows; "
        f"{bad_ayat} ayat show {bad} made-up mismatches; top: {kinds.most_common(4)}"
    )


def idraj() -> None:
    """Reading through a sakt place without the sakt (idraj), against a sakt reference."""
    for sura, aya, attr in ((36, 52, "sakt_marqdena"), (75, 27, "sakt_man_raq"),
                            (83, 14, "sakt_bal_ran")):  # fmt: skip
        ref = ref_for(sura, aya, **{attr: "sakt"})
        m_i = moshaf_from_dict({attr: "sakt"}).model_copy(update={attr: "idraj"})
        print(f"{sura}:{aya} idraj:")
        for line in rows_of(ref, phonetize(ref.uthmani, m_i, sura).phonemes):
            print("   ", line)


def _with_madd(ref: Reference, kind: str, letters: int, only_first: bool = False) -> str:
    g, rules = groups_with_rules(ref)
    hits = [i for i, r in enumerate(rules) if kind in r]
    for i in hits[:1] if only_first else hits:
        g[i] = g[i][0] * letters
    return "".join(g)


def madd_pairs() -> None:
    """2:19 at the default 4/4: munfasil and muttasil heard at other lengths."""
    ref = ref_for(2, 19)
    cases = [
        ("munfasil 5 + muttasil 4 (ruled a mistake)", _with_madd(ref, "Monfasel Madd", 5)),
        ("munfasil 4 + muttasil 5 (ruled correct)", _with_madd(ref, "Mottasel Madd", 5)),
        ("munfasil 3 (ruled a mistake)", _with_madd(ref, "Monfasel Madd", 3)),
    ]
    for label, text in cases:
        print(label)
        for line in rows_of(ref, text):
            print("   ", line)


def leen_lengths() -> None:
    """106:4 leen at a stop heard at 1-6 letters (N harakat = N-1 letters)."""
    ref = ref_for(106, 4)
    for n in range(1, 7):
        print(
            f"leen as {n} letter(s) = {n + 1} harakat:",
            rows_of(ref, _with_madd(ref, "Leen Madd", n))[0],
        )


def _swap_group(ref: Reference, index: int, new: str) -> str:
    g, _ = groups_with_rules(ref)
    g[index] = new
    return "".join(g)


def ghunnah_states() -> None:
    """How ghunnah/izhar confusions are named (2:4 ikhfa at «أُنزِلَ», 1:7 voweled noon)."""
    r1, r4 = ref_for(1, 7), ref_for(2, 4)
    n, nm = P.noon, P.noon_mokhfah
    i_ikhfa = next(i for i, x in enumerate(groups_with_rules(r4)[0]) if x == nm * 3)
    i_noon = next(i for i, x in enumerate(groups_with_rules(r1)[0]) if x == n + P.fatha)
    for label, ref, i, new in (
        ("ikhfa heard as one clear noon", r4, i_ikhfa, n),
        ("ikhfa heard as a clear noon held", r4, i_ikhfa, n * 3),
        ("voweled noon heard doubled and held", r1, i_noon, n * 3 + P.fatha),
        ("voweled noon heard doubled", r1, i_noon, n * 2 + P.fatha),
    ):
        print(label + ":", rows_of(ref, _swap_group(ref, i, new))[0])


def hesitation() -> None:
    """A pause read as a stop, then the reciter carries on connected (1:7 after word 2)."""
    m = build_moshaf()
    st = default_structure(TextSelection(1, 7), m)
    stop = dataclasses.replace(st, segments=[(0, 2), (3, st.segments[-1][1])])
    connected = build_reference_from_structure(st, m).phonetic.phonemes
    for line in rows_of(build_reference_from_structure(stop, m), connected):
        print("   ", line)


def word_skip() -> None:
    """103:2 with «ٱلْإِنسَـٰنَ» skipped: does the comparison slide onto «لَفِى»?"""
    ref = ref_for(103, 2)
    m = build_moshaf()
    words = ayah_words(103, 2)
    skipped = phonetize(" ".join(w for i, w in enumerate(words) if i != 1), m, 102).phonemes
    print("words:", " ".join(words))
    for line in rows_of(ref, skipped):
        print("   ", line)


def phonetizer() -> None:
    """Phonetizer cases at the default settings (sifat of the letter in question)."""
    m = build_moshaf()

    def letter(text: str, sura: int, first: str) -> list[tuple[str, str, str]]:
        out = quran_phonetizer(text, m, remove_spaces=True, sura_idx=sura)
        return [(g.phonemes, g.tafkheem_or_taqeeq, g.qalqla) for g in out.sifat
                if g.phonemes.startswith(first)]  # fmt: skip

    for sura, aya in ((54, 2), (54, 3), (54, 19), (2, 177)):
        w = ayah_words(sura, aya)
        last = next(x for x in w if "رّ" in x or "رِّ" in x or "رَّ" in x)
        upto = " ".join(w[: w.index(last) + 1])
        print(f"doubled raa at a stop {sura}:{aya} «{last}»: {letter(upto, sura - 1, 'رر')}")
    for sura, aya, word in ((27, 22, "أَحَطتُ"), (5, 28, "بَسَطتَ"), (39, 56, "فَرَّطتُ")):
        print(f"ط in «{word}» {sura}:{aya}: {letter(word, sura - 1, 'ط')}")
    for word in ("أَوْ", "لَوْ"):
        out = quran_phonetizer(word, m, remove_spaces=True)
        print(f"stop on «{word}»: {out.phonemes!r} (a leen madd would be وو or more)")
    yas = moshaf_from_dict(None).model_copy(update={"noon_and_yaseen": "idgham"})
    text = " ".join(ayah_words(36, 1) + ayah_words(36, 2))
    print(
        "يس idgham option:", quran_phonetizer(text, yas, remove_spaces=True, sura_idx=35).phonemes
    )


CHECKS: dict[str, Callable[[], None]] = {
    "sifat_najm23": sifat_najm23, "idraj": idraj, "madd_pairs": madd_pairs,
    "leen_lengths": leen_lengths, "ghunnah_states": ghunnah_states, "hesitation": hesitation,
    "word_skip": word_skip, "phonetizer": phonetizer, "sifat_quran": sifat_quran,
}  # fmt: skip
SLOW = {"sifat_quran"}


def main(names: list[str]) -> None:
    for name in names or [n for n in CHECKS if n not in SLOW]:
        print(f"\n### {name}: {(CHECKS[name].__doc__ or '').strip()}")
        CHECKS[name]()


if __name__ == "__main__":
    main(sys.argv[1:])
