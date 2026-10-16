"""Decode the model's per-frame output into the heard script and one sifat value per heard letter.

Ported from tajweed_ai `muaalem_lab/decode.py`, which replaced quran-muaalem 0.2.2's own decode
(three faults, verified on its source): its CTC collapse drops a final one-frame letter after a
blank; it pairs each sifat output with the heard letters by position, so one merged or missed
value shifts every letter after it; and it takes the softmax in bfloat16.

Here the heard script is the greedy CTC decode (ctc.py) with the softmax in float32 (done where
the model runs). Each sifat output is decoded the same way, then lined up with the heard letters
by order (Needleman-Wunsch) against each letter's natural value (text/letter_sifat.py). Timing is
not used to place values (some sifat heads fire a letter early), only to check values that differ
from the letter's natural one.

A value's `sure` says whether it may become a question; a letter with no value of its own gets its
natural value, not sure.

Fixed in Mojawid (audit 2026-10-16, C6): a haraka or qalqalah mark with no letter before it (at
the start, or right after another mark) can't belong to any letter group, and raised a plain
ValueError (a 500). Such a mark is dropped before the letters are grouped.
"""

from collections.abc import Mapping

import numpy as np

from app.engine.pipeline.ctc import Token, ctc_greedy, group_frames
from app.engine.pipeline.errors import AnalysisError
from app.engine.pipeline.heard import Heard, HeardGroup, SifaValue
from app.engine.text.letter_sifat import SIFAT_LEVELS, natural_sifat
from app.engine.text.qt import alph, chunck_phonemes

DECODER_VERSION = 2
MARKS = frozenset(alph.phonetic_groups.residuals)  # harakat and the qalqalah mark
SURE_MIN_PROB = 0.5
GAP_REACH = 1  # letters either side of an alignment gap are not sure
SLIP_WINDOW = 3  # letters either side looked at when testing for a one-letter slip

Placed = tuple[int, float, bool]  # (value id, confidence, sure)


def align(values: list[int], natural: list[int]) -> list[int | None]:
    """Needleman-Wunsch (match 0, mismatch 1, gap 1) of a level's values against the letters'
    natural values. Per letter: the index of its value, or None. On ties a value stays paired with
    the letter in the same order position (no gap)."""
    n, m = len(values), len(natural)
    D = np.zeros((n + 1, m + 1), dtype=np.int32)
    D[:, 0] = np.arange(n + 1)
    D[0, :] = np.arange(m + 1)
    nat = np.array(natural)
    for i in range(1, n + 1):
        D[i, 1:] = np.minimum(D[i - 1, :-1] + (nat != values[i - 1]), D[i - 1, 1:] + 1)
        for j in range(1, m + 1):
            D[i, j] = min(D[i, j], D[i, j - 1] + 1)
    out: list[int | None] = [None] * m
    i, j = n, m
    while i > 0 and j > 0:
        if D[i, j] == D[i - 1, j - 1] + (values[i - 1] != natural[j - 1]):
            out[j - 1] = i - 1
            i, j = i - 1, j - 1
        elif D[i, j] == D[i, j - 1] + 1:
            j -= 1
        else:
            i -= 1
    return out


def _unsure_and_gaps(pair: list[int | None], n_values: int) -> tuple[set[int], int]:
    """Letters next to an alignment gap (not sure), and how many gaps there are."""
    m = len(pair)
    unsure: set[int] = set()
    gaps = 0
    for k, x in enumerate(pair):
        if x is None:
            gaps += 1
            unsure.update(range(k - GAP_REACH, k + GAP_REACH + 1))
    used = {x for x in pair if x is not None}
    for i in range(n_values):
        if i not in used:  # an extra value: the letters around where it was skipped
            gaps += 1
            after = next((k for k, x in enumerate(pair) if x is not None and x > i), m)
            unsure.update(range(after - GAP_REACH, after + GAP_REACH))
    return unsure, gaps


def _differing(seq: list[int | None], natural: list[int], a: int, b: int) -> int:
    return sum(1 for j in range(a, b) if seq[j] is not None and seq[j] != natural[j])


def _slip_explains(got: list[int | None], natural: list[int], k: int) -> bool:
    """A one-letter slip explains the differences around letter k better than a real one."""
    m = len(natural)
    a, b = max(0, k - SLIP_WINDOW), min(m, k + SLIP_WINDOW + 1)
    here = _differing(got, natural, a, b)
    slid_left = got[1:] + [None]
    slid_right = [None, *got[:-1]]
    return min(_differing(slid_left, natural, a, b), _differing(slid_right, natural, a, b)) < here


def _is_sure(
    t: Token, k: int, ctx: tuple[list[int], list[tuple[int, int]], list[int | None]]
) -> bool:
    natural, spans, got = ctx
    m = len(natural)
    if t.id == natural[k]:
        return True
    lo = spans[k - 1][0] if k else 0
    hi = spans[k + 1][1] if k + 1 < m else 10**9
    if not lo <= t.start < hi:
        return False  # emitted away from this letter and its neighbours
    return not _slip_explains(got, natural, k)


def place_level(
    tokens: list[Token], natural: list[int], spans: list[tuple[int, int]]
) -> tuple[list[Placed], int]:
    """Per heard letter: (value id, confidence, sure); and the number of gaps."""
    values = [t.id for t in tokens]
    pair = align(values, natural)
    unsure, gaps = _unsure_and_gaps(pair, len(values))
    got = [values[x] if x is not None else None for x in pair]
    out: list[Placed] = []
    for k, x in enumerate(pair):
        if x is None:
            out.append((natural[k], 0.0, False))
            continue
        t = tokens[x]
        sure = t.prob >= SURE_MIN_PROB and k not in unsure
        if sure:
            sure = _is_sure(t, k, (natural, spans, got))
        out.append((t.id, t.prob, sure))
    return out, gaps


Vocab = Mapping[str, Mapping[int, str]]


def drop_stray_marks(tokens: list[Token], vocab: Mapping[int, str]) -> list[Token]:
    """The tokens without a mark that has no letter before it: a leading haraka, a second haraka
    in a row, a doubled qalqalah mark."""
    kept: list[Token] = []
    after_mark = True  # nothing before the first token
    for t in tokens:
        is_mark = vocab[t.id] in MARKS
        if not (is_mark and after_mark):
            kept.append(t)
            after_mark = is_mark
    return kept


def decode(probs: Mapping[str, np.ndarray], id_to_vocab: Vocab, sifat_to_en: Vocab) -> Heard:
    """The heard script and its sifat from the per-frame probabilities of every output."""
    tokens = drop_stray_marks(ctc_greedy(probs["phonemes"]), id_to_vocab["phonemes"])
    text = "".join(id_to_vocab["phonemes"][t.id] for t in tokens)
    groups = chunck_phonemes(text) if text else []
    if "".join(groups) != text:
        raise AnalysisError("The recording could not be analysed.")
    spans = group_frames(groups, tokens)
    natural_of = [natural_sifat(groups, k) for k in range(len(groups))]
    per_level: dict[str, list[SifaValue]] = {}
    sure: dict[str, list[bool]] = {}
    gaps: dict[str, int] = {}
    for level in SIFAT_LEVELS:
        to_id = {v: k for k, v in sifat_to_en[level].items()}
        natural = [to_id[n[level]] for n in natural_of]
        placed, gaps[level] = place_level(ctc_greedy(probs[level]), natural, spans)
        per_level[level] = [SifaValue(sifat_to_en[level][v], p, v) for v, p, _ in placed]
        sure[level] = [s for _, _, s in placed]
    sifat = [
        HeardGroup(g, {lv: per_level[lv][k] for lv in SIFAT_LEVELS}) for k, g in enumerate(groups)
    ]
    vocab = [id_to_vocab["phonemes"][i] for i in range(probs["phonemes"].shape[1])]
    return Heard(
        text=text,
        probs=[t.prob for t in tokens],
        ids=[t.id for t in tokens],
        sifat=sifat,
        group_frames=spans,
        sure=sure,
        gaps=gaps,
        n_frames=len(probs["phonemes"]),
        phoneme_probs=probs["phonemes"],
        phoneme_vocab=vocab,
    )
