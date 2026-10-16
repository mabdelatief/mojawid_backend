"""Where the reciter paused, from the segmenter's per-frame speech/silence labels.

Ported from tajweed_ai `muaalem_lab/pauses.py` (Pauses, pauses_from_labels). The segmenter
(obadx/recitation-segmenter-v2) labels every 20 ms frame; running it is in `models/`. It treats a
sakt like a stop (a known flaw), so callers handle the four sakt places themselves.
"""

import dataclasses
from typing import Any

import numpy as np

SAMPLE_RATE = 16000
FRAME_SAMPLES = 320  # hop 160 × stride 2: one label per 20 ms
SPEECH = 1
# a silence shorter than this is not a pause (madd, ghunnah, a short catch of breath)
MIN_PAUSE_S = 0.35
# a burst of "speech" shorter than this is noise (a click, a lip smack)
MIN_SPEECH_S = 0.10

Interval = tuple[float, float]


@dataclasses.dataclass(frozen=True)
class Pauses:
    """Speech stretches; the pauses are the gaps between them."""

    speech: list[Interval]  # in seconds
    raw: list[Interval]  # before merging short silences and dropping short bursts
    ends_in_speech: bool  # the clip ends while the reciter is still speaking
    starts_in_speech: bool

    @property
    def gaps(self) -> list[Interval]:
        return [(a[1], b[0]) for a, b in zip(self.speech, self.speech[1:], strict=False)]

    def to_json(self) -> dict[str, Any]:
        return {
            "min_pause_s": MIN_PAUSE_S,
            "speech": [list(x) for x in self.speech],
            "raw": [list(x) for x in self.raw],
            "starts_in_speech": self.starts_in_speech,
            "ends_in_speech": self.ends_in_speech,
        }


def _raw_speech(labels: np.ndarray, dur: float) -> list[Interval]:
    sec = FRAME_SAMPLES / SAMPLE_RATE
    raw, t = [], 0
    while t < len(labels):
        u = t
        while u < len(labels) and labels[u] == labels[t]:
            u += 1
        if labels[t] == SPEECH:
            raw.append((round(t * sec, 3), round(min(u * sec, dur), 3)))
        t = u
    return raw


def pauses_from_labels(labels: np.ndarray, n_samples: int) -> Pauses:
    """Speech stretches from per-frame labels: silences shorter than MIN_PAUSE_S are merged into
    speech, then bursts shorter than MIN_SPEECH_S are dropped."""
    raw = _raw_speech(labels, n_samples / SAMPLE_RATE)
    merged: list[Interval] = []
    for a, b in raw:
        if merged and a - merged[-1][1] < MIN_PAUSE_S:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    speech = [(a, b) for a, b in merged if b - a >= MIN_SPEECH_S]
    return Pauses(
        speech,
        raw,
        starts_in_speech=bool(len(labels) and labels[0] == SPEECH),
        ends_in_speech=bool(len(labels) and labels[-1] == SPEECH),
    )
