"""The decoder on hand-built frame probabilities (the CTC edge quran-muaalem gets wrong, one sifat
value per heard letter that can never shift), and how sure the model was at a flagged place.
Ported from tajweed_ai tests/test_decode.py and tests/test_doubt.py."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.engine.pipeline import doubt
from app.engine.pipeline.ctc import Token, ctc_greedy
from app.engine.pipeline.decode import align, place_level
from app.engine.text.phonetic_diff import phoneme_diff


def frames(path: list[int], n_classes: int = 3, p: float = 0.9) -> np.ndarray:
    """(T, C) probabilities whose best class per frame follows `path`."""
    rest = (1 - p) / (n_classes - 1)
    out = np.full((len(path), n_classes), rest, dtype=np.float32)
    for t, c in enumerate(path):
        out[t, c] = p
    return out


@pytest.mark.parametrize(
    ("path", "ids"),
    [
        ([0, 5], [5]),  # quran-muaalem drops this one
        ([7, 7, 0, 5], [7, 5]),  # and this final one-frame token
        ([5, 0, 5, 0], [5, 5]),  # a blank between equal labels keeps them apart
        ([5, 5, 5, 5], [5]),
        ([0, 0, 0], []),
        ([5], [5]),
        ([5, 6], [5, 6]),
    ],
)
def test_ctc_greedy(path: list[int], ids: list[int]) -> None:
    assert [t.id for t in ctc_greedy(frames(path, n_classes=8))] == ids


def test_ctc_greedy_frames_and_prob() -> None:
    toks = ctc_greedy(frames([0, 5, 5, 0, 0, 7], n_classes=8))
    assert [(t.start, t.end) for t in toks] == [(1, 3), (5, 6)]
    assert toks[0].prob == pytest.approx(0.9)


def toks(values: list[int], step: int = 4) -> list[Token]:
    """Tokens one per letter, each at its letter's frames."""
    return [Token(v, k * step, k * step + 1, 0.95) for k, v in enumerate(values)]


SPANS = [(k * 4, k * 4 + 1) for k in range(12)]


def test_align_in_order_when_counts_match() -> None:
    assert align([1, 2, 2, 1], [1, 2, 2, 1]) == [0, 1, 2, 3]
    # one real difference stays paired in order: no gap is invented for it
    assert align([1, 1, 2, 1], [1, 2, 2, 1]) == [0, 1, 2, 3]


def test_align_missing_value_does_not_shift_the_rest() -> None:
    natural = [1, 1, 2, 1, 2, 2, 1]
    got = align([1, 2, 1, 2, 2, 1], natural)  # letter 1's value is missing
    assert got.count(None) == 1
    assert [natural[k] for k, x in enumerate(got) if x is not None] == [1, 2, 1, 2, 2, 1]


def test_align_extra_value_is_skipped() -> None:
    assert align([1, 2, 2, 2, 1], [1, 2, 2, 1]).count(None) == 0


def test_isolated_difference_is_sure() -> None:
    natural = [1, 2, 1, 1, 2, 1, 2]
    placed, gaps = place_level(toks([1, 2, 1, 2, 2, 1, 2]), natural, SPANS)  # letter 3 heard as 2
    assert gaps == 0
    assert placed[3] == (2, 0.95, True)


def test_difference_next_to_a_gap_is_not_sure() -> None:
    natural = [1, 2, 1, 1, 2, 1, 2, 1]
    placed, gaps = place_level(toks([1, 2, 2, 2, 1, 2, 1]), natural, SPANS)
    assert gaps >= 1
    assert not any(sure and v != natural[k] for k, (v, _, sure) in enumerate(placed))


def test_letter_without_a_value_gets_its_natural_value_not_sure() -> None:
    natural = [1, 2, 1, 2]
    placed, _ = place_level(toks([1, 2, 2]), natural, SPANS)
    missing = [k for k, (_, p, _) in enumerate(placed) if p == 0.0]
    assert len(missing) == 1
    assert placed[missing[0]] == (natural[missing[0]], 0.0, False)


def test_difference_emitted_far_away_is_not_sure() -> None:
    t = toks([1, 1, 1, 2, 1, 1])
    t[3] = Token(2, 40, 41, 0.99)  # far outside letters 2..4
    placed, _ = place_level(t, [1] * 6, SPANS)
    assert placed[3][0] == 2
    assert placed[3][2] is False


def test_one_letter_slip_is_not_sure() -> None:
    natural = [1, 1, 2, 1, 1, 1, 2, 1, 1]
    placed, _ = place_level(toks([1, 2, 1, 1, 1, 2, 1, 1, 1]), natural, SPANS)
    assert not any(sure and v != natural[k] for k, (v, _, sure) in enumerate(placed))


def test_low_confidence_is_not_sure() -> None:
    t = toks([1, 2, 2, 1, 2])
    t[2] = Token(2, 8, 9, 0.4)
    placed, _ = place_level(t, [1, 2, 1, 1, 2], SPANS)
    assert placed[2] == (2, 0.4, False)


# ---------- doubt ----------

VOCAB = ["[PAD]", "ط", "ڇ", "ع", "ِ", "ف"]
ID = {s: i for i, s in enumerate(VOCAB)}


def probs(*rows: dict[str, float]) -> np.ndarray:
    """One frame per row: {symbol: probability}; what is left goes to the other symbols."""
    out = np.full((len(rows), len(VOCAB)), 1e-4, dtype=np.float32)
    for t, row in enumerate(rows):
        for sym, p in row.items():
            out[t, 0 if sym == "·" else ID[sym]] = p
        out[t] /= out[t].sum()
    return out


def ratio(p: np.ndarray, ref: str, heard: str) -> list[float]:
    diff = phoneme_diff(ref, heard)
    r = doubt.ratios(p, VOCAB, heard, diff)
    assert r is not None
    return [x for b, x in zip(diff, r, strict=True) if b["op"] != "equal"]


def test_a_qalqalah_mark_that_nearly_won_is_uncertain() -> None:
    # the ط of «نُطْعِمُكُمْ» on 2026-10-14: "nothing" 0.510 against the qalqalah mark 0.479
    p = probs({"ط": 1}, {"·": 0.51, "ڇ": 0.48}, {"·": 1}, {"ع": 1}, {"ِ": 1})
    [r] = ratio(p, "طڇعِ", "طعِ")
    assert 1 <= r < 1.2
    assert doubt.is_uncertain(r)


def test_a_clear_deletion_is_not_uncertain() -> None:
    p = probs({"ط": 1}, {"·": 0.999, "ڇ": 0.001}, {"·": 1}, {"ع": 1}, {"ِ": 1})
    [r] = ratio(p, "طڇعِ", "طعِ")
    assert r > 100
    assert not doubt.is_uncertain(r)


def test_a_clear_substitution_and_insertion() -> None:
    [r] = ratio(probs({"ف": 1}, {"ِ": 1}, {"·": 1}, {"ع": 1}, {"ِ": 1}), "طِعِ", "فِعِ")
    assert r > 100
    [r] = ratio(probs({"ط": 1}, {"ڇ": 0.99}, {"·": 1}, {"ع": 1}, {"ِ": 1}), "طعِ", "طڇعِ")
    assert r > 10


def test_an_expected_reading_too_long_for_the_frames() -> None:
    [r] = ratio(probs({"ط": 1}, {"ع": 1}, {"ِ": 1}), "طڇعِعِعِ", "طعِ")
    assert r == math.inf
    assert not doubt.is_uncertain(r)


def test_probabilities_from_another_run_claim_nothing() -> None:
    p = probs({"ط": 1}, {"·": 1}, {"ع": 1}, {"ِ": 1})
    assert doubt.ratios(p, VOCAB, "فعِ", phoneme_diff("طعِ", "فعِ")) is None
    assert not doubt.is_uncertain(None)
