"""The report: ghunnah named at the wrong length, valid variants, raum, missed sakt, uncertain
places; and the letter groups the analysis stands on. Ported from tajweed_ai tests/test_analysis.py,
two tests of tests/test_labels.py, and the both-valid letter checks of tests/test_rules.py."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pytest

from app.engine.pipeline.analysis.report import analyze
from app.engine.pipeline.heard import Heard
from app.engine.text.groups import both_valid_for, ref_groups
from app.engine.text.letter_sifat import SIFAT_LEVELS, natural_sifat
from app.engine.text.moshaf import build_moshaf
from app.engine.text.qt import alph, chunck_phonemes
from app.engine.text.quran_text import ayah_words, surah_list
from app.engine.text.reference import Reference, build_reference, build_reference_from_structure
from app.engine.text.structure import TextSelection, default_structure

MOSHAF = build_moshaf()


def heard_as(text: str, probs: np.ndarray | None = None, vocab: list[str] | None = None) -> Heard:
    """A model output that heard `text` (no sifat, unless probs are given: no frames)."""
    return Heard(text, [], [], [], [], None, {}, 0, phoneme_probs=probs, phoneme_vocab=vocab)


def ref_of(sura: int, aya: int, **kw: Any) -> Reference:
    return build_reference(TextSelection(sura, aya, **kw), MOSHAF)


def errors(sura: int, aya: int, pattern: str, repl: str) -> list[dict[str, Any]]:
    """Report rows for the reference with the first match of `pattern` replaced."""
    ref = ref_of(sura, aya)
    ph = ref.phonetic.phonemes
    heard = re.sub(pattern, repl, ph, count=1)
    assert heard != ph, "the faked mistake did not change anything"
    rows: list[dict[str, Any]] = analyze(heard_as(heard), ref)["errors"]
    return rows


GhunnahCase = tuple[int, int, str, str, str, str, str]


@pytest.mark.parametrize(
    "case",
    [
        (113, 2, "ںںں", "ں", "ن", "short", "delete"),  # ikhfa cut short: مِن شَرِّ
        (113, 2, "ںںں", "ن", "ن", "izhar", "replace"),  # ikhfa read with a clear noon
        (2, 27, "۾۾۾", "م", "نۢ", "izhar", "replace"),  # iqlab with a clear meem, no ghunnah
        (2, 27, "۾۾۾", "اا", "نۢ", "missing", "replace"),  # another letter where the iqlab is
        (113, 2, "ںںں", "ںںںںں", "ن", "long", "insert"),  # ikhfa held too long
        (2, 27, "۾۾۾", "۾", "نۢ", "short", "delete"),  # iqlab: مِنۢ بَعْدِ
        (2, 8, "ننننَ", "نَ", "نّ", "short", "delete"),  # noon mushaddad: ٱلنَّاسِ
        (2, 8, "ييي", "يي", "ن يَ", "short", "delete"),  # idgham: مَن يَقُولُ
        (2, 7, "ووو", "و", "ٌ", "short", "delete"),  # idgham of a tanween
    ],
)
def test_ghunnah_heard_at_wrong_length(case: GhunnahCase) -> None:
    sura, aya, pattern, repl, where, state, operation = case
    rows = [r for r in errors(sura, aya, pattern, repl) if not r["likely_false_alarm"]]
    assert len(rows) == 1, rows
    r = rows[0]
    assert where in r["uthmani_text"]
    assert (r["ghunnah"], r["error_type"], r["operation"]) == (state, "tajweed", operation)
    assert [x["ar"] for x in r["rules"]] == ["الغنة"]


@pytest.mark.parametrize(
    ("sura", "aya", "pattern", "repl"),
    [
        (2, 8, "ننننَ", "ننننِ"),  # only the haraka after the ghunnah changed
        (2, 27, "۾۾۾", "ممم"),  # iqlab with a clear meem held full length: a letter row
        (1, 5, "ييَ", "يَ"),  # plain shadda yaa in إِيَّاكَ, no ghunnah
        (106, 1, "ييي", "ي"),  # leen madd at the stop in قُرَيْشٍ, written like an idgham yaa
    ],
)
def test_not_a_ghunnah(sura: int, aya: int, pattern: str, repl: str) -> None:
    rows = errors(sura, aya, pattern, repl)
    assert rows
    assert all(r["ghunnah"] is None for r in rows), rows
    assert all(r["rules"] == [] or r["rules"][0]["tag"] != "ghunnah" for r in rows)


def test_exact_match_has_no_rows() -> None:
    ref = ref_of(113, 2)
    report = analyze(heard_as(ref.phonetic.phonemes), ref)
    assert report["errors"] == []
    assert report["exact_match"]


def test_missed_sakt_is_reported() -> None:
    # explain_error skips groups ending in a sakt mark; the result must still show it
    ref = build_reference_from_structure(default_structure(TextSelection(75, 27), MOSHAF), MOSHAF)
    rows = analyze(heard_as(ref.phonetic.phonemes.replace("ۜ", "", 1)), ref)["errors"]
    assert rows
    assert any(r["word_index"] == 1 and r["expected_ph"] == "نۜ" for r in rows), rows


def test_meem_form_is_a_valid_variant() -> None:
    rows = errors(2, 27, "۾۾۾", "ممم")  # iqlab read with the lips closed, held
    assert rows
    assert all(r["valid_variant"] and r["valid_variant"]["reason"] == "meem_form" for r in rows)
    assert all(r["likely_false_alarm"] for r in rows)


@pytest.mark.parametrize(("heard_len", "ok"), [(5, True), (3, False), (2, False)])
def test_munfasil_at_another_allowed_length_is_a_valid_variant(heard_len: int, ok: bool) -> None:
    ref = ref_of(2, 4)  # «بِمَآ أُنزِلَ»: munfasil 4 by default
    ph = ref.phonetic.phonemes
    assert "ااااءُ" in ph
    heard = ph.replace("ااااءُ", "ا" * heard_len + "ءُ", 1)
    rows = [
        r
        for r in analyze(heard_as(heard), ref)["errors"]
        if any(x["en"] == "Monfasel Madd" for x in r["rules"])
    ]
    assert rows
    assert bool(rows[0]["valid_variant"]) == ok


@pytest.mark.parametrize(("practice", "raum"), [(False, False), (True, True)])
def test_haraka_at_a_stop_is_raum_only_with_practice_on(practice: bool, raum: bool) -> None:
    # teachers' ruling (2026-10-14): raum is correct only when the reciter means it
    st = default_structure(TextSelection(13, 2), MOSHAF)
    n = len(st.words())
    st.segments = [(0, 10), (11, n - 1)]  # a stop at ٱلْعَرْشِ
    ref = build_reference_from_structure(st, MOSHAF)
    last = [g for g in ref_groups(ref) if g.segment == 0][-1]
    ph = ref.phonetic.phonemes
    heard = ph[: last.end] + alph.phonetics.kasra + ph[last.end :]
    rows = analyze(heard_as(heard), ref, raum_practice=practice)["errors"]
    assert len(rows) == 1
    assert bool(rows[0]["valid_variant"]) == raum
    assert rows[0]["likely_false_alarm"] == raum
    if raum:
        assert rows[0]["valid_variant"]["reason"] == "raum"


def test_haraka_inside_a_stretch_is_never_raum() -> None:
    ref = ref_of(1, 2)
    ph = ref.phonetic.phonemes
    i = ph.index("ل")  # a letter mid-ayah, not at a stop
    rows = analyze(heard_as(ph[: i + 1] + "ُ" + ph[i + 1 :]), ref, raum_practice=True)["errors"]
    assert rows
    assert not any(r["valid_variant"] for r in rows)


def _probs_for(heard: str, vocab: list[str], ties: dict[int, str]) -> np.ndarray:
    """Frame probabilities whose greedy decode is `heard`: each symbol, then a blank frame; after
    the symbol at index k in `ties`, the blank only just beats that symbol (0.51 to 0.48)."""
    ids = {s: i for i, s in enumerate(vocab)}
    rows: list[dict[int, float]] = []
    for k, c in enumerate(heard):
        rows.append({ids[c]: 1.0})
        rows.append({0: 0.51, ids[ties[k]]: 0.48} if k in ties else {0: 1.0})
    p = np.full((len(rows), len(vocab)), 1e-4, dtype=np.float32)
    for t, row in enumerate(rows):
        for i, v in row.items():
            p[t, i] = v
    out: np.ndarray = p / p.sum(axis=1, keepdims=True)
    return out


def test_a_near_coin_flip_is_uncertain_not_a_mistake() -> None:
    # Al-Insan 9 with the qalqalah of «نُطْعِمُكُمْ» and of «لِوَجْهِ» both missing: the first
    # nearly heard (the model's own split, 2026-10-14), the second clearly not
    ref = ref_of(76, 9)
    ph = ref.phonetic.phonemes
    first, second = ph.index("طڇ"), ph.index("جڇ")
    heard = ph[: first + 1] + ph[first + 2 : second + 1] + ph[second + 2 :]
    vocab = ["[PAD]", *sorted(set(ph))]
    report = analyze(heard_as(heard, _probs_for(heard, vocab, {first: "ڇ"}), vocab), ref)
    rows = {r["expected_ph"]: r for r in report["errors"]}
    assert rows["طڇ"]["uncertain"]
    assert rows["طڇ"]["doubt_ratio"] < 2
    assert not rows["جڇ"]["uncertain"]
    assert rows["جڇ"]["doubt_ratio"] > 100
    # without the probabilities nothing is claimed: both are mistakes, as before
    report = analyze(heard_as(heard), ref)
    assert not any(r["uncertain"] for r in report["errors"])
    assert all(r["doubt_ratio"] is None for r in report["errors"])


def test_a_valid_variant_is_never_uncertain() -> None:
    ref = ref_of(2, 4)  # بِمَآ أُنزِلَ: munfasil, set to 4
    ph = ref.phonetic.phonemes
    heard = ph.replace("اااا", "ااااا", 1)  # read at 5: allowed
    vocab = ["[PAD]", *sorted(set(ph))]
    report = analyze(heard_as(heard, _probs_for(heard, vocab, {}), vocab), ref)
    variants = [r for r in report["errors"] if r["valid_variant"]]
    assert variants
    assert not any(r["uncertain"] for r in variants)


def test_silence_marks_every_letter_missing() -> None:
    ref = ref_of(112, 1)
    sifat = analyze(heard_as(""), ref)["sifat"]
    assert len(sifat) == len(ref.phonetic.sifat)
    assert all(row["tag"] == "delete" for row in sifat)


# ---------- the letter groups ----------


def test_leen_harakat_offset_and_voweled_yaa_is_not_madd() -> None:
    groups = ref_groups(ref_of(106, 4))  # مِّنْ خَوْفٍۭ: leen at the stop
    leen = [g for g in groups if "Leen Madd" in g.rules]
    assert leen
    assert all(g.kind == "madd" and g.harakat_offset == 1 and g.count + 1 == 4 for g in leen)
    groups = ref_groups(ref_of(19, 1))  # كٓهيعٓصٓ
    assert all(g.kind != "madd" for g in groups if g.core in "وي" and g.residual)


@pytest.mark.slow
def test_letter_rules_match_package_everywhere() -> None:
    mismatches: dict[tuple[str, str], int] = {}
    for s in surah_list():
        for a in range(1, s.ayat + 1):
            ref = ref_of(s.index, a)
            groups = chunck_phonemes(ref.phonetic.phonemes)
            for k, pkg in enumerate(x.model_dump() for x in ref.phonetic.sifat):
                ours = natural_sifat(groups, k)
                for level in SIFAT_LEVELS:
                    if ours[level] != pkg[level]:
                        key = (level, groups[k][0])
                        mismatches[key] = mismatches.get(key, 0) + 1
    # only the context rules the engine copies from the reference may differ
    ph = alph.phonetics
    allowed = {("tafkheem_or_taqeeq", c) for c in (ph.raa, ph.lam, ph.alif)}
    assert set(mismatches) <= allowed, {k: v for k, v in mismatches.items() if k not in allowed}


# ---------- both-valid letters (the raa of مصر / القطر / ونذر / فرق) ----------


def bare(w: str) -> str:
    return re.sub("[ً-ٰٟۖ-ۭٱ]", lambda m: "ا" if m.group() == "ٱ" else "", w)


def word_index(sura: int, aya: int, letters: str) -> int:
    return next(i for i, w in enumerate(ayah_words(sura, aya)) if bare(w).endswith(letters))


def both_valid_letters(
    sura: int, aya: int, word_end: int | None = None
) -> list[tuple[int | None, str]]:
    ref = build_reference_from_structure(
        default_structure(TextSelection(sura, aya, word_end=word_end), MOSHAF), MOSHAF
    )
    return [
        (g.word, g.uth_char)
        for g in ref_groups(ref)
        if both_valid_for(ref, g, "tafkheem_or_taqeeq")
    ]


@pytest.mark.parametrize(
    ("sura", "aya", "letters"),
    [(34, 12, "القطر"), (12, 21, "مصر"), (12, 99, "مصر"), (10, 87, "مصر"), (43, 51, "مصر"),
     (54, 16, "ونذر"), (54, 39, "ونذر")],
)  # fmt: skip
def test_both_valid_raa_covers_only_the_raa_and_only_at_a_stop(
    sura: int, aya: int, letters: str
) -> None:
    words = ayah_words(sura, aya)
    k = word_index(sura, aya, letters)
    assert both_valid_letters(sura, aya, word_end=k) == [(k, "ر")]
    if k + 1 < len(words):
        assert all(w != k for w, _ in both_valid_letters(sura, aya))  # connected: one way only


def test_firq_is_both_valid_connected_only() -> None:
    k = word_index(26, 63, "فرق")
    assert both_valid_letters(26, 63) == [(k, "ر")]
    assert both_valid_letters(26, 63, word_end=k) == []
