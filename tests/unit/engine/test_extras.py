"""The result fields new to Mojawid: the user's word spans, the mistake key and mark, the madd
count in harakat, and the allowed sifat at both-valid places."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.engine.pipeline.analysis.report import analyze
from app.engine.pipeline.extras.rows import add_row_fields
from app.engine.pipeline.extras.word_times import word_times
from app.engine.pipeline.heard import Heard, HeardGroup, SifaValue
from app.engine.text.letter_sifat import SIFAT_LEVELS
from app.engine.text.moshaf import build_moshaf
from app.engine.text.phonetic_diff import phoneme_diff
from app.engine.text.qt import chunck_phonemes
from app.engine.text.quran_text import ayah_words
from app.engine.text.reference import Reference, build_reference, build_reference_from_structure
from app.engine.text.structure import TextSelection, default_structure
from tests.unit.engine.test_pipeline_golden import GOLDEN, outcome_for

MOSHAF = build_moshaf()
HUSARY = json.loads(
    (Path(__file__).resolve().parents[2] / "golden" / "husary_timings.json").read_text()
)


def heard_as(text: str) -> Heard:
    return Heard(text, [], [], [], [], None, {}, 0)


def rows_for(ref: Reference, heard: str, raum: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = analyze(heard_as(heard), ref, raum)["errors"]
    add_row_fields(rows, ref)
    return rows


# ---------- word times in the user's recording ----------


@pytest.mark.parametrize("cid", ["001001", "001002", "001003", "001007", "067001", "112001"])
def test_word_times_match_the_reciters_own_timings(cid: str) -> None:
    # the "user's recording" here is Husary's own file, so our spans must agree with his timings
    golden = json.loads((GOLDEN / f"{cid}_manual.json").read_text())
    outcome = outcome_for(golden)
    t = golden["case"]["text"]
    spans = {
        w: (a / 1000, b / 1000)
        for f, last, a, b in HUSARY["ayat"][f"{t['sura']}:{t['aya_start']}"]
        for w in range(f, last + 1)
    }
    assert sorted(w["word"] for w in outcome.word_times) == sorted(spans)
    for w in outcome.word_times:
        start, end = spans[w["word"]]
        assert abs(w["start_s"] - start) <= 0.3, w
        assert abs(w["end_s"] - end) <= 0.3, w
        assert (w["sura"], w["aya"]) == (t["sura"], t["aya_start"])


def test_going_back_gives_each_recital_its_own_span() -> None:
    outcome = outcome_for(json.loads((GOLDEN / "001002_twice_manual.json").read_text()))
    words = [(w["segment"], w["word"]) for w in outcome.word_times]
    assert words == [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3)]
    starts = [w["start_s"] for w in outcome.word_times]
    assert starts == sorted(starts)
    # neighbouring words may share a joining letter group (a frame or two), never more
    ends = [w["end_s"] for w in outcome.word_times]
    assert all(e - s2 <= 0.08 + 1e-9 for e, s2 in zip(ends, starts[1:], strict=False))
    assert starts[4] - ends[3] > 1.0  # the pause before going back


def test_opening_has_no_word_times() -> None:
    outcome = outcome_for(json.loads((GOLDEN / "basmala+067001_manual.json").read_text()))
    assert outcome.word_times
    assert all(w["sura"] == 67 for w in outcome.word_times)


def test_skipped_word_has_no_span() -> None:
    ref = build_reference(TextSelection(1, 2), MOSHAF)
    last = ayah_words(1, 2)[-1]
    text = " ".join(ayah_words(1, 2)[:-1])  # the last word left out, then a stop
    heard_text = build_reference(TextSelection(1, 2, word_end=2), MOSHAF).phonetic.phonemes
    groups = chunck_phonemes(heard_text)
    frames = [(2 * k, 2 * k + 2) for k in range(len(groups))]
    heard = Heard(heard_text, [], [], [], frames, None, {}, 2 * len(groups))
    times = word_times(heard, ref, phoneme_diff(ref.phonetic.phonemes, heard_text), 5.0)
    assert [w["word"] for w in times] == [0, 1, 2], (text, last)


# ---------- the row fields ----------


def test_key_mark_and_place_of_a_letter_mistake() -> None:
    ref = build_reference(TextSelection(1, 2), MOSHAF)
    [row] = rows_for(ref, ref.phonetic.phonemes.replace("ح", "ه", 1))
    k = next(i for i, w in enumerate(ayah_words(1, 2)) if "ح" in w)
    assert (row["sura"], row["aya"], row["word"]) == (1, 2, k)
    assert row["key"] == f"1:2:{k}:{row['error_type']}"
    assert row["mark"] == "letter"
    assert row["counted"]


def test_allowed_madd_is_a_variant_and_not_counted() -> None:
    ref = build_reference(TextSelection(2, 4), MOSHAF)
    rows = rows_for(ref, ref.phonetic.phonemes.replace("ااااءُ", "ا" * 5 + "ءُ"))  # both: taswiya
    madd = [r for r in rows if any(x["en"] == "Monfasel Madd" for x in r["rules"])]
    assert madd
    assert madd[0]["mark"] == "variant"
    assert not madd[0]["counted"]
    assert (madd[0]["expected_harakat"], madd[0]["heard_harakat"]) == (4, 5)


def test_madd_counted_in_harakat_and_leen_adds_one() -> None:
    ref = build_reference(
        TextSelection(106, 4), MOSHAF
    )  # خَوْفٍۭ: leen at the stop, 4 harakat = 3 letters
    ph = ref.phonetic.phonemes
    m = list(re.finditer("ووو", ph))[-1]
    rows = rows_for(ref, ph[: m.start()] + "و" + ph[m.end() :])
    leen = [r for r in rows if any(x["en"] == "Leen Madd" for x in r["rules"])]
    assert leen
    assert (leen[0]["expected_harakat"], leen[0]["heard_harakat"]) == (4, 2)


def test_ghunnah_has_no_harakat() -> None:
    ref = build_reference(TextSelection(113, 2), MOSHAF)
    rows = [r for r in rows_for(ref, ref.phonetic.phonemes.replace("ںںں", "ں", 1)) if r["ghunnah"]]
    assert rows
    assert rows[0]["mark"] == "tajweed"
    assert (rows[0]["expected_harakat"], rows[0]["heard_harakat"]) == (None, None)


def test_opening_mistake_key() -> None:
    ref = build_reference(TextSelection(67, 1, prefixes=("istiaatha",)), MOSHAF)
    ph = ref.phonetic.phonemes
    i = ph.index("ع")  # in أَعُوذُ, the opening
    rows = rows_for(ref, ph[:i] + "ء" + ph[i + 1 :])
    assert rows
    assert rows[0]["sura"] is None
    assert rows[0]["key"].startswith("istiaatha:0:0:")


# ---------- allowed sifat at both-valid places ----------


def _heard_with_raa(ref: Reference, value: str) -> Heard:
    """The reference heard exactly, with every sifa natural except the raa's tafkheem."""
    groups = []
    for s in ref.phonetic.sifat:
        values = {lv: SifaValue(str(getattr(s, lv)), 0.99, 0) for lv in SIFAT_LEVELS}
        if s.phonemes.startswith("ر"):
            values["tafkheem_or_taqeeq"] = SifaValue(value, 0.99, 0)
        groups.append(HeardGroup(s.phonemes, values))
    sure = {lv: [True] * len(groups) for lv in SIFAT_LEVELS}
    return Heard(ref.phonetic.phonemes, [], [], groups, [], sure, {}, 0)


def test_raa_of_misr_at_a_stop_is_allowed_either_way() -> None:
    k = next(i for i, w in enumerate(ayah_words(12, 21)) if "مِّصْرَ" in w or "صْرَ" in w)
    ref = build_reference_from_structure(
        default_structure(TextSelection(12, 21, word_end=k), MOSHAF), MOSHAF
    )
    sifat = analyze(_heard_with_raa(ref, "moraqaq"), ref)["sifat"]
    raa = [r["attrs"]["tafkheem_or_taqeeq"] for r in sifat if r["ref"].startswith("ر")][-1]
    assert raa["mismatch"]
    assert raa["allowed"]


def test_a_raa_elsewhere_is_not_allowed() -> None:
    ref = build_reference(TextSelection(1, 2), MOSHAF)  # رَبِّ: tafkheem only
    sifat = analyze(_heard_with_raa(ref, "moraqaq"), ref)["sifat"]
    raa = [r["attrs"]["tafkheem_or_taqeeq"] for r in sifat if r["ref"].startswith("ر")][0]
    assert raa["mismatch"]
    assert not raa["allowed"]
