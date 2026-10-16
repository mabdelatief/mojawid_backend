"""A haraka or qalqalah mark with no letter before it is dropped before the heard letters are
grouped, so it can't crash the analysis (audit 2026-10-16, C6)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.engine.pipeline.ctc import BLANK, Token
from app.engine.pipeline.decode import decode, drop_stray_marks
from app.engine.text.qt import alph

P = alph.phonetics
VOCAB_FILE = Path(__file__).resolve().parents[2] / "golden" / "pipeline" / "vocab.json"
RAW = json.loads(VOCAB_FILE.read_text())
ID_TO_VOCAB = {k: {int(i): v for i, v in m.items()} for k, m in RAW["id_to_vocab"].items()}
SIFAT_TO_EN = {k: {int(i): v for i, v in m.items()} for k, m in RAW["sifat_to_en_vocab"].items()}
ID_OF = {v: i for i, v in ID_TO_VOCAB["phonemes"].items()}


def tokens(script: str) -> list[Token]:
    return [Token(ID_OF[c], 2 * k, 2 * k + 1, 0.9) for k, c in enumerate(script)]


def text_of(ts: list[Token]) -> str:
    return "".join(ID_TO_VOCAB["phonemes"][t.id] for t in ts)


@pytest.mark.parametrize(
    ("heard", "kept"),
    [
        (P.fatha + P.baa + P.fatha, P.baa + P.fatha),  # a leading haraka
        (P.baa + P.fatha + P.dama + P.taa, P.baa + P.fatha + P.taa),  # two harakat in a row
        (P.baa + P.qlqla + P.qlqla, P.baa + P.qlqla),  # a doubled qalqalah mark
        (P.qaf + P.qlqla + P.baa + P.fatha, P.qaf + P.qlqla + P.baa + P.fatha),  # nothing stray
    ],
)
def test_stray_marks_are_dropped(heard: str, kept: str) -> None:
    assert text_of(drop_stray_marks(tokens(heard), ID_TO_VOCAB["phonemes"])) == kept


def one_hot_frames(script: str) -> np.ndarray:
    """Two frames per character, a blank between them."""
    n = len(ID_TO_VOCAB["phonemes"])
    out = np.zeros((2 * len(script) + 1, n), dtype=np.float32)
    out[:, BLANK] = 1.0
    for k, c in enumerate(script):
        out[2 * k + 1] = 0.0
        out[2 * k + 1, ID_OF[c]] = 1.0
    return out


def test_decode_no_longer_crashes_on_them() -> None:
    script = P.fatha + P.baa + P.fatha + P.dama + P.taa + P.qlqla + P.qlqla
    phonemes = one_hot_frames(script)
    probs = {"phonemes": phonemes}
    for level, vocab in SIFAT_TO_EN.items():
        level_probs = np.zeros((len(phonemes), len(vocab)), dtype=np.float32)
        level_probs[:, BLANK] = 1.0
        probs[level] = level_probs
    heard = decode(probs, ID_TO_VOCAB, SIFAT_TO_EN)
    assert heard.text == P.baa + P.fatha + P.taa + P.qlqla
    assert [g.phonemes_group for g in heard.sifat] == [P.baa + P.fatha, P.taa + P.qlqla]
