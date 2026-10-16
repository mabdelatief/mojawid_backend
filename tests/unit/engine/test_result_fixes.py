"""Three places where Mojawid's result differs from the lab on purpose (user's decision,
2026-10-16), found on the user's recording of al-Najm 23: a sifat row tagged by what the phonemes
output heard, a ghunnah where none is due named as a tajweed mistake, and a leen madd written as a
madd rather than a ghunnah."""

from __future__ import annotations

from types import SimpleNamespace

import diff_match_patch as dmp

from app.engine.pipeline.analysis.rows import GHUNNAH_OPERATION, ghunnah_state
from app.engine.pipeline.analysis.sifat import _read_as_expected, heard_at
from app.engine.text.qt import alph
from app.engine.text.readable import SHADDA, describe

P = alph.phonetics


def _diffs(ref: str, heard: str) -> list[tuple[int, str]]:
    diffs: list[tuple[int, str]] = dmp.diff_match_patch().diff_main(ref, heard)
    return diffs


def test_heard_at_follows_the_diff() -> None:
    ref = "زَلَللَااهُ"
    assert heard_at(_diffs(ref, ref), 4, 7) == ref[4:7]
    # an insertion right after a span belongs to it, not to the next one
    ref, heard = "كُمسَ", "كُمممسَ"
    diffs = _diffs(ref, heard)
    assert heard_at(diffs, 2, 3) == "ممم"
    assert heard_at(diffs, 3, 5) == "سَ"


def test_a_row_read_exactly_as_expected_is_exact() -> None:
    # the doubled lam of «ٱللَّهُ»: the sifat outputs split it as one lam, the phonemes output heard
    # it as expected
    ref = "ءَںںںزَلَللَااهُ"
    starts = [0, 2, 5, 7, 9, 12, 14]  # ءَ ںںں زَ لَ للَ اا هُ
    row = SimpleNamespace(ref="للَ", out="لَ", ref_idx=4)
    assert _read_as_expected(row, "changed", _diffs(ref, ref), starts)
    # a meem heard held where a single one was due is still a difference
    ref, heard = "كُمسَ", "كُمممسَ"
    row = SimpleNamespace(ref="م", out="ممم", ref_idx=1)
    assert not _read_as_expected(row, "changed", _diffs(ref, heard), [0, 2, 3])
    # rows the heard side adds have no expected stretch to compare
    assert not _read_as_expected(SimpleNamespace(ref="", out="م", ref_idx=None), "insert", [], [0])


def _explained(exp: str, got: str) -> SimpleNamespace:
    return SimpleNamespace(expected_ph=exp, preditected_ph=got, ref_tajweed_rules=None)


def test_a_ghunnah_where_none_is_due_is_unexpected() -> None:
    assert ghunnah_state(_explained(P.meem, P.meem * 3), "م") == "unexpected"
    assert ghunnah_state(_explained(P.noon + P.fatha, P.noon * 3 + P.fatha), "نَ") == "unexpected"
    assert GHUNNAH_OPERATION["unexpected"] == "insert"
    # a meem doubled but not held is not a ghunnah
    assert ghunnah_state(_explained(P.meem, P.meem * 2), "م") is None
    # a held ghunnah heard short is still "short"
    assert ghunnah_state(_explained(P.noon * 3 + P.fatha, P.noon + P.fatha), "نَّ") == "short"


def test_leen_madd_is_written_as_a_madd() -> None:
    leen = P.qaf + P.dama + P.raa + P.fatha + P.yaa * 3 + P.sheen
    assert describe(leen) == "قُرَيْشْ (مد ٤ حركات)"
    assert "غنة" not in describe(P.waw * 5)
    # a ghunnah held into a yaa still reads as a ghunnah: it has a haraka after it
    assert describe(P.yaa * 3 + P.fatha) == P.yaa + SHADDA + P.fatha + " (غنة)"
