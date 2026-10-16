"""Tajweed colour classes (worked out from the reference phonetizer) and the plain-Arabic form of
the model's script. Ported from tajweed_ai tests/test_tajweed.py and test_readable.py (the
teacher review-card checks are teacher-only and stay in the lab). The Uthmani text writes madd as
alif + U+0653 and puts shadda before the haraka, hence the escapes."""

from __future__ import annotations

from typing import Any

import pytest

from app.engine.text.moshaf import build_moshaf
from app.engine.text.readable import describe
from app.engine.text.reference import Reference, build_reference
from app.engine.text.structure import TextSelection
from app.engine.text.tajweed import CLASSES, classes_present, tajweed_spans

MOSHAF = build_moshaf()


def coloured(sura: int, aya: int) -> tuple[Reference, list[tuple[str, Any]]]:
    ref = build_reference(TextSelection(sura, aya), MOSHAF)
    pairs = [(ref.uthmani[s:t], c) for s, t, c in tajweed_spans(ref.uthmani, ref.phonetic)]
    return ref, pairs


@pytest.mark.parametrize(
    ("sura", "aya", "piece", "cls"),
    [
        (113, 2, "ن", "ghunnah"),  # ikhfa: مِن شَرِّ
        (2, 27, "نۢ", "ghunnah"),  # iqlab: مِنۢ بَعْدِ
        (2, 8, "نَّ", "ghunnah"),  # noon mushaddad: ٱلنَّاسِ
        (2, 8, "يَ", "ghunnah"),  # idgham with ghunnah: مَن يَقُولُ
        (2, 5, "مِّ", "ghunnah"),  # tanween merged into meem: هُدًى مِّن
        (2, 8, "م", "ghunnah"),  # ikhfa shafawi: هُم بِمُؤْمِنِينَ
        (1, 7, "آ", "madd6"),  # ٱلضَّآلِّينَ
        (2, 13, "آ", "wajib"),  # ٱلسُّفَهَآءُ
        (2, 13, "وٓ", "jaiz"),  # munfasil: قَالُوٓا۟ أَنُؤْمِنُ
        (1, 1, "ي", "jaiz"),  # 'arid at the stop: ٱلرَّحِيمِ
        (112, 1, "دٌ", "qalqalah"),  # أَحَدٌ at the stop
        (2, 7, "بْ", "qalqalah"),  # أَبْصَـٰرِهِمْ
        (1, 2, "رَ", "tafkheem"),  # رَبِّ
        (2, 27, "رْ", "tafkheem"),  # ٱلْأَرْضِ
        (2, 8, "ٱل", "silent"),  # hamzat wasl and lam shamsiyya: ٱلنَّاسِ
        (2, 5, "ن", "silent"),  # idgham without ghunnah: مِّن رَّبِّهِمْ
        (2, 5, "و۟", "silent"),  # أُو۟لَـٰٓئِكَ
    ],
)
def test_known_places(sura: int, aya: int, piece: str, cls: str) -> None:
    assert (piece, cls) in coloured(sura, aya)[1]


def test_left_plain() -> None:
    _, pairs = coloured(1, 7)
    assert ("رِ", "tafkheem") not in pairs  # raa with kasra in غَيْرِ is thin
    ref, pairs = coloured(1, 2)
    assert tajweed_spans(ref.uthmani, ref.phonetic)[0][0] > 0  # the opening hamzat wasl is said
    assert not any(c == "jaiz" and p == "ا" for p, c in pairs)
    ref, _ = coloured(2, 8)
    spans = tajweed_spans(ref.uthmani, ref.phonetic)
    assert not any(ref.uthmani[s:t] == "ا" for s, t, c in spans if c != "silent")  # natural madd


@pytest.mark.parametrize(("sura", "aya"), [(1, 1), (2, 255), (19, 1), (36, 1), (113, 1)])
def test_spans_well_formed(sura: int, aya: int) -> None:
    ref = build_reference(TextSelection(sura, aya), MOSHAF)
    spans = tajweed_spans(ref.uthmani, ref.phonetic)
    assert spans
    assert all(c in CLASSES for _, _, c in spans)
    ends = [0] + [x for s, t, _ in spans for x in (s, t)] + [len(ref.uthmani)]
    assert ends == sorted(ends)
    assert all(s < t for s, t, _ in spans)


def test_classes_present_in_legend_order() -> None:
    spans = [[0, 1, "silent"], [2, 3, "madd6"], [4, 5, "silent"]]
    assert classes_present(spans) == ["madd6", "silent"]


@pytest.mark.parametrize(
    ("qps", "shown"),
    [
        ("ۦۦۦۦ", "ي (مد ٤ حركات)"),
        ("اا", "ا (مد حركتان)"),
        ("ںںں", "ن (إخفاء بغنة)"),
        ("۾۾۾", "م (إخفاء بغنة)"),
        ("دڇ", "دْ (قلقلة)"),
        ("ببِ", "\u0628\u0651\u0650"),  # shadda before the haraka, as the code writes it
        ("ش", "شْ"),
        ("شِ", "شِ"),
        ("ممممَ", "\u0645\u0651\u064e (غنة)"),
        ("يييُ", "\u064a\u0651\u064f (غنة)"),
    ],
)
def test_describe(qps: str, shown: str) -> None:
    assert describe(qps) == shown
