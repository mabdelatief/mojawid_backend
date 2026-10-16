"""Words read more than one correct way whatever the setting (rules.alternatives, audit R4 and
R9): whichever way was heard, the expected reading follows it and nothing is counted."""

from __future__ import annotations

from typing import Any

import pytest

from app.engine.pipeline.alternatives import closest_reading, word_present
from app.engine.pipeline.analysis.report import analyze
from app.engine.pipeline.heard import Heard
from app.engine.text import rules as R
from app.engine.text.moshaf import moshaf_from_dict
from app.engine.text.reference import Reference, build_reference_from_structure
from app.engine.text.structure import TextSelection, default_structure

MOSHAF = moshaf_from_dict(None)


def ref_for(text: TextSelection, **reading: Any) -> Reference:
    m = MOSHAF.model_copy(update=reading)
    return build_reference_from_structure(default_structure(text, m), m)


def counted(ref: Reference, heard_text: str) -> list[dict[str, Any]]:
    h = Heard(text=heard_text, probs=[], ids=[], sifat=[], group_frames=[], sure=None, gaps={},
              n_frames=0)  # fmt: skip
    return [r for r in analyze(h, ref)["errors"] if not r["likely_false_alarm"]]


CASES = [
    (TextSelection(30, 54), "harakat_daaf", ("fath", "dam")),
    (TextSelection(12, 11), "noon_tamnna", ("ishmam", "rawm")),
    (TextSelection(10, 59), "tasheel_or_madd", ("madd", "tasheel")),
    (TextSelection(6, 143), "tasheel_or_madd", ("madd", "tasheel")),
    (TextSelection(49, 11, word_start=29), "start_with_ism", ("alism", "lism")),
]


@pytest.mark.parametrize(("text", "field", "values"), CASES)
def test_either_way_is_correct(text: TextSelection, field: str, values: tuple[str, ...]) -> None:
    for setting in values:
        ref = ref_for(text, **{field: setting})
        for heard_way in values:
            heard = ref_for(text, **{field: heard_way}).phonetic.phonemes
            chosen = closest_reading(ref, ref.moshaf, heard)
            assert chosen.phonetic.phonemes == heard, (setting, heard_way)
            assert getattr(chosen.moshaf, field) == heard_way
            assert counted(chosen, heard) == []


def test_the_two_ways_really_differ() -> None:
    for text, field, (a, b) in CASES:
        assert ref_for(text, **{field: a}).phonetic.phonemes != (
            ref_for(text, **{field: b}).phonetic.phonemes
        ), (text, field)


def test_daaf_only_in_al_rum() -> None:
    # 8:66 «ضَعْفًۭا»: Hafs reads fath alone there
    daaf = next(a for a in R.DEFAULT.alternatives if a.field == "harakat_daaf")
    assert not word_present(daaf, ref_for(TextSelection(8, 66)))
    assert word_present(daaf, ref_for(TextSelection(30, 54)))


def test_a_tie_keeps_the_setting() -> None:
    # ٱلِٱسْمُ mid-ayah: both values give the same reading, so the setting stays
    ref = ref_for(TextSelection(49, 11))
    chosen = closest_reading(ref, ref.moshaf, ref.phonetic.phonemes)
    assert chosen is ref


def test_no_such_word_leaves_the_reference() -> None:
    ref = ref_for(TextSelection(1, 1))
    assert closest_reading(ref, ref.moshaf, "") is ref
