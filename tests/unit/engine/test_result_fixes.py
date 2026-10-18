"""Places where Mojawid's result differs from the lab on purpose (user's decisions, 2026-10-16),
found on the user's recording of al-Najm 23 and in the 2026-10-16 audit: the sifat table paired by
our own group alignment, a ghunnah where none is due named as a tajweed mistake, and a leen madd
written as a madd rather than a ghunnah."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.engine.pipeline.analysis.rows import GHUNNAH_OPERATION, ghunnah_state
from app.engine.pipeline.analysis.sifat import pair_groups, sifat_rows, tag_of
from app.engine.pipeline.heard import Heard, HeardGroup, SifaValue
from app.engine.text.letter_sifat import SIFAT_LEVELS
from app.engine.text.moshaf import build_moshaf
from app.engine.text.qt import alph
from app.engine.text.readable import SHADDA, describe
from app.engine.text.reference import build_reference_from_structure
from app.engine.text.structure import Structure, TextSelection, default_structure

P = alph.phonetics
M = build_moshaf()


def _perfect(
    sura: int,
    aya: int,
    st: Structure | None = None,
    heard_as: dict[int, dict[str, str]] | None = None,
) -> tuple[Any, list[dict[str, Any]]]:
    """The sifat table for a perfect recitation of an ayah (or of `st`): heard script and sifat
    as expected, except the values in `heard_as` (group index -> level -> value)."""
    ref = build_reference_from_structure(st or default_structure(TextSelection(sura, aya), M), M)
    heard_as = heard_as or {}
    sifat = [
        HeardGroup(
            s.phonemes,
            {
                lv: SifaValue(heard_as.get(i, {}).get(lv, getattr(s, lv)), 0.99, 1)
                for lv in SIFAT_LEVELS
            },
        )
        for i, s in enumerate(ref.phonetic.sifat)
    ]
    sure = {lv: [True] * len(sifat) for lv in SIFAT_LEVELS}
    heard = Heard(
        text=ref.phonetic.phonemes,
        probs=[],
        ids=[],
        sifat=sifat,
        group_frames=[],
        sure=sure,
        gaps={},
        n_frames=0,
    )
    return ref, sifat_rows(heard, ref)


@pytest.mark.parametrize(
    ("sura", "aya"), [(53, 23), (1, 1), (2, 255), (3, 18), (24, 35), (112, 2), (59, 23)]
)
def test_a_perfect_recitation_gives_a_clean_sifat_table(sura: int, aya: int) -> None:
    # the lam of «ٱللَّهُ» was paired with the lam before it (quran-muaalem segment_groups): a
    # row lost and a made-up tafkheem mismatch on a perfect reading of 53:23
    ref, rows = _perfect(sura, aya)
    assert len(rows) == len(ref.phonetic.sifat)
    assert all(r["tag"] == "exact" and r["ref"] == r["pred"] for r in rows)
    assert not [lv for r in rows for lv, v in r["attrs"].items() if v["mismatch"]]


@pytest.mark.parametrize(
    "st",
    [
        # stopped on «فِيهِ», then «هُدًى»: one «ه» group in the whole script, two word by word
        Structure(2, 1, 3, segments=[(0, 0), (1, 5), (6, 7), (8, 15)]),
        Structure(
            2, 1, 3, prefixes=("istiadha", "basmala"), segments=[(0, 0), (1, 5), (6, 7), (8, 15)]
        ),
        default_structure(TextSelection(1, 1, 7), M),  # «ٱلرَّحِيمِ» stopped on, then «مَٰلِكِ»
    ],
)
def test_a_letter_doubled_across_words_keeps_the_table_whole(st: Structure) -> None:
    # 2026-10-18: the worker crashed (IndexError) on the user's 2:1-3 stopped on «فيه»
    ref, rows = _perfect(st.sura, st.aya_start, st)
    assert len(rows) == len(ref.phonetic.sifat)
    assert all(r["tag"] == "exact" for r in rows)
    assert not [lv for r in rows for lv, v in r["attrs"].items() if v["mismatch"]]


def test_allowed_stays_on_its_letter_after_a_doubled_letter() -> None:
    # «قَوْمٌۭ» stopped on, then «مُّجْرِمُونَ»; «فَأَسْرِ» stopped on: its raa may be either
    st = Structure(44, 22, 23, segments=[(0, 4), (5, 6), (7, 10)])
    ref = build_reference_from_structure(st, M)
    raa = [i for i, s in enumerate(ref.phonetic.sifat) if s.phonemes[0] == P.raa][2]
    other = {"mofakham": "moraqaq", "moraqaq": "mofakham"}
    flipped = other[ref.phonetic.sifat[raa].tafkheem_or_taqeeq]
    _, rows = _perfect(44, 22, st, {raa: {"tafkheem_or_taqeeq": flipped}})
    row = next(r for r in rows if r["ref_idx"] == raa)
    assert row["attrs"]["tafkheem_or_taqeeq"] == row["attrs"]["tafkheem_or_taqeeq"] | {
        "mismatch": True,
        "allowed": True,
    }
    assert not [r for r in rows if r is not row and any(v["allowed"] for v in r["attrs"].values())]


def test_pair_groups() -> None:
    assert pair_groups(["لَ", "للَ", "اا"], ["لَ", "للَ", "اا"]) == [(0, 0), (1, 1), (2, 2)]
    assert pair_groups(["كُ", "م", "سَ"], ["كُ", "ممم", "سَ"]) == [(0, 0), (1, 1), (2, 2)]
    assert pair_groups(["ءِ", "ييَ", "كَ"], ["ءِ", "كَ"]) == [(0, 0), (1, None), (2, 1)]
    assert pair_groups(["بَ"], ["بَ", "هْ"]) == [(0, 0), (None, 1)]
    assert tag_of("اااا", "ااااا") == "exact"  # a madd length is judged by the error rows
    assert tag_of("للَ", "لَ") == "changed"


def _explained(exp: str, got: str) -> SimpleNamespace:
    return SimpleNamespace(expected_ph=exp, preditected_ph=got, ref_tajweed_rules=None)


def test_a_ghunnah_where_none_is_due_is_unexpected() -> None:
    assert ghunnah_state(_explained(P.meem, P.meem * 3), "م") == "unexpected"
    # a sakin noon or meem read hidden where izhar is due (audit C4)
    assert ghunnah_state(_explained(P.noon, P.noon_mokhfah * 3), "نْ") == "unexpected"
    assert ghunnah_state(_explained(P.meem, P.meem_mokhfah * 3), "مْ") == "unexpected"
    # a voweled noon read doubled is a haraka/letter matter, not a ghunnah where none is due (C3)
    assert ghunnah_state(_explained(P.noon + P.fatha, P.noon * 3 + P.fatha), "نَ") is None
    assert GHUNNAH_OPERATION["unexpected"] == "insert"
    # a meem doubled but not held is not a ghunnah
    assert ghunnah_state(_explained(P.meem, P.meem * 2), "م") is None
    # a held ghunnah heard short is still "short"
    assert ghunnah_state(_explained(P.noon * 3 + P.fatha, P.noon + P.fatha), "نَّ") == "short"


def test_ikhfa_heard_as_a_clear_noon_is_izhar_whatever_its_length() -> None:
    ikhfa = P.noon_mokhfah * 3
    assert ghunnah_state(_explained(ikhfa, P.noon), "ن") == "izhar"
    assert ghunnah_state(_explained(ikhfa, P.noon * 3), "ن") == "izhar"  # held: still izhar (C4)
    # the meem of iqlab / ikhfa shafawi: a clear meem held is the other correct form (ruling #6)
    assert ghunnah_state(_explained(P.meem_mokhfah * 3, P.meem * 3), "ۢ") is None


def test_leen_madd_is_written_as_a_madd() -> None:
    leen = P.qaf + P.dama + P.raa + P.fatha + P.yaa * 3 + P.sheen
    assert describe(leen) == "قُرَيْشْ (مد ٤ حركات)"
    assert "غنة" not in describe(P.waw * 5)
    # a ghunnah held into a yaa still reads as a ghunnah: it has a haraka after it
    assert describe(P.yaa * 3 + P.fatha) == P.yaa + SHADDA + P.fatha + " (غنة)"
