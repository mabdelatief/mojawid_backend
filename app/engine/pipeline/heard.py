"""What the model heard: the heard script, one sifat value per heard letter group, each group's
frames, and the per-frame probabilities the uncertainty check needs.

Replaces quran-muaalem's MuaalemOutput and the lab's Decoded (tajweed_ai `muaalem_lab/decode.py`)
with one typed class, so the pipeline never needs quran-muaalem's types.
"""

import dataclasses

import numpy as np

from app.engine.pipeline.pauses import Pauses


@dataclasses.dataclass(frozen=True)
class SifaValue:
    """One sifat output's value for a heard letter group."""

    text: str  # the English value name, e.g. "mofakham"
    prob: float
    idx: int


@dataclasses.dataclass(frozen=True)
class HeardGroup:
    """A heard letter group and its sifat."""

    phonemes_group: str
    values: dict[str, SifaValue]  # sifat level -> value


@dataclasses.dataclass
class Heard:
    """The decoder's output for one recording."""

    text: str  # the heard phonetic script
    probs: list[float]  # per heard character
    ids: list[int]
    sifat: list[HeardGroup]
    group_frames: list[tuple[int, int]]  # per heard group: [start, end) frames
    sure: dict[str, list[bool]] | None  # per level, per heard group: may it become a question
    gaps: dict[str, int]  # per level: letters with no value of their own + extra values
    n_frames: int
    pauses: Pauses | None = None
    # the phonemes output per frame, (T, C) float32, as the greedy decode read it (for doubt.py)
    phoneme_probs: np.ndarray | None = None
    phoneme_vocab: list[str] | None = None  # its symbols in class order
